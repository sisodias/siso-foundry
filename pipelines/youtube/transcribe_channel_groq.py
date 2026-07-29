#!/usr/bin/env python3
"""Fill a Foundry YouTube corpus by temporarily downloading audio for Groq Whisper.

Only one video's media exists locally at a time. Supported source audio is
uploaded directly or split into stream-copied chunks without re-encoding. The
source and any chunks live in a TemporaryDirectory and are removed after the
video succeeds or fails.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from openai import AuthenticationError, OpenAI, RateLimitError

from scrape_channel_transcripts import (
    build_corpus_exports,
    default_output_root,
    utc_now,
    write_json,
    write_text,
)


DEFAULT_MODEL = "whisper-large-v3-turbo"
DEFAULT_MAX_UPLOAD_MB = 24
DEFAULT_CHUNK_SECONDS = 1_200
DEFAULT_WORKERS = 2
CHUNK_TARGET_RATIO = 0.80
SUPPORTED_CONTENT_TYPES = {
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".mp4": "audio/mp4",
    ".mpeg": "audio/mpeg",
    ".mpga": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
    ".webm": "audio/webm",
}

# Some repo-wide logging configurations enable HTTP client debug output. Keep
# request internals (including transient headers) out of long-running logs.
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def require_command(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"Required command is missing: {name}")
    return path


def run(command: list[str]) -> None:
    result = subprocess.run(command)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(command[:4])}")


def media_duration(path: Path, ffprobe: str) -> float:
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def download_audio(
    video_id: str,
    work_dir: Path,
    yt_dlp: str,
    cookies_from_browser: str | None,
    force_ipv4: bool,
) -> Path:
    output_template = str(work_dir / "source.%(ext)s")
    command = [
        yt_dlp,
        "--no-playlist",
        "--no-warnings",
        "--format",
        "bestaudio/best",
        "--output",
        output_template,
    ]
    if cookies_from_browser:
        command.extend(["--cookies-from-browser", cookies_from_browser])
    if force_ipv4:
        command.append("--force-ipv4")
    if shutil.which("deno"):
        command.extend(["--js-runtimes", "deno"])
    command.append(f"https://www.youtube.com/watch?v={video_id}")
    run(command)

    candidates = [
        path
        for path in work_dir.glob("source.*")
        if not path.name.endswith((".part", ".ytdl"))
    ]
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one downloaded audio file, found {len(candidates)}")
    return candidates[0]


def compress_audio(source: Path, work_dir: Path, ffmpeg: str) -> Path:
    output = work_dir / "audio.opus"
    run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-vn",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "libopus",
            "-b:a",
            "16k",
            "-vbr",
            "off",
            str(output),
        ]
    )
    source.unlink(missing_ok=True)
    return output


def prepare_chunks(
    audio: Path,
    work_dir: Path,
    ffmpeg: str,
    ffprobe: str,
    max_upload_bytes: int,
    chunk_seconds: int,
) -> list[tuple[Path, float]]:
    if audio.stat().st_size <= max_upload_bytes:
        return [(audio, 0.0)]

    duration = media_duration(audio, ffprobe)
    average_bytes_per_second = audio.stat().st_size / duration
    size_safe_seconds = max(
        60,
        math.floor(
            max_upload_bytes * CHUNK_TARGET_RATIO / average_bytes_per_second
        ),
    )
    effective_chunk_seconds = min(chunk_seconds, size_safe_seconds)
    chunks: list[tuple[Path, float]] = []
    for index, start in enumerate(
        range(0, math.ceil(duration), effective_chunk_seconds)
    ):
        output = work_dir / f"chunk-{index:03d}{audio.suffix.lower()}"
        run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(audio),
                "-ss",
                str(start),
                "-t",
                str(effective_chunk_seconds),
                "-map",
                "0:a:0",
                "-vn",
                "-c:a",
                "copy",
                str(output),
            ]
        )
        if output.stat().st_size > max_upload_bytes:
            raise RuntimeError(
                f"Chunk {output.name} is still over the upload limit: {output.stat().st_size} bytes"
            )
        chunks.append((output, float(start)))
    audio.unlink(missing_ok=True)
    return chunks


def response_to_dict(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump()
    if isinstance(response, dict):
        return response
    return json.loads(response.json())


def transcribe_chunk(client: OpenAI, path: Path, model: str) -> dict[str, Any]:
    content_type = SUPPORTED_CONTENT_TYPES.get(path.suffix.lower())
    if not content_type:
        raise RuntimeError(f"Unsupported Groq audio type: {path.suffix}")
    with path.open("rb") as audio_file:
        response = client.audio.transcriptions.create(
            file=(path.name, audio_file, content_type),
            model=model,
            language="en",
            response_format="verbose_json",
            timestamp_granularities=["segment"],
            temperature=0,
        )
    return response_to_dict(response)


def combine_transcriptions(
    video: dict[str, Any],
    model: str,
    chunk_results: list[tuple[dict[str, Any], float]],
) -> tuple[dict[str, Any], str]:
    text_parts: list[str] = []
    segments: list[dict[str, Any]] = []
    detected_languages: list[str] = []

    for result, offset in chunk_results:
        chunk_text = str(result.get("text") or "").strip()
        if chunk_text:
            text_parts.append(chunk_text)
        language = str(result.get("language") or "")
        if language and language not in detected_languages:
            detected_languages.append(language)
        for segment in result.get("segments") or []:
            raw = segment.model_dump() if hasattr(segment, "model_dump") else dict(segment)
            start = float(raw.get("start") or 0) + offset
            end = float(raw.get("end") or start) + offset
            segments.append(
                {
                    "start": round(start, 3),
                    "duration": round(max(end - start, 0), 3),
                    "text": str(raw.get("text") or "").strip(),
                }
            )

    text = "\n".join(text_parts)
    if not text:
        raise RuntimeError("Groq returned an empty transcript")
    payload = {
        "schema_version": "foundry.youtube-corpus.v1",
        "video_id": video["video_id"],
        "title": video["title"],
        "url": video["url"],
        "source": "groq-whisper",
        "model": model,
        "language": ",".join(detected_languages) or "en",
        "language_code": "en",
        "is_generated": True,
        "fetched_at": utc_now(),
        "segment_count": len(segments),
        "character_count": len(text),
        "transcript_duration_seconds": round(
            max((item["start"] + item["duration"] for item in segments), default=0),
            3,
        ),
        "segments": segments,
    }
    return payload, text


def transcribe_video(
    client: OpenAI,
    video: dict[str, Any],
    model: str,
    max_upload_bytes: int,
    chunk_seconds: int,
    yt_dlp: str,
    ffmpeg: str,
    ffprobe: str,
    workers: int,
    cookies_from_browser: str | None,
    force_ipv4: bool,
) -> tuple[dict[str, Any], str]:
    with tempfile.TemporaryDirectory(prefix=f"foundry-groq-{video['video_id']}-") as temp:
        work_dir = Path(temp)
        download_started = time.monotonic()
        source = download_audio(
            video["video_id"],
            work_dir,
            yt_dlp,
            cookies_from_browser,
            force_ipv4,
        )
        print(
            f"  downloaded {source.stat().st_size / 1_000_000:.1f} MB in "
            f"{time.monotonic() - download_started:.1f}s",
            flush=True,
        )
        if source.suffix.lower() in SUPPORTED_CONTENT_TYPES:
            audio = source
        else:
            audio = compress_audio(source, work_dir, ffmpeg)
            print(
                f"  converted unsupported source to {audio.stat().st_size / 1_000_000:.1f} MB Opus",
                flush=True,
            )
        prepare_started = time.monotonic()
        chunks = prepare_chunks(
            audio,
            work_dir,
            ffmpeg,
            ffprobe,
            max_upload_bytes,
            chunk_seconds,
        )
        print(
            f"  prepared {len(chunks)} chunk(s) in "
            f"{time.monotonic() - prepare_started:.1f}s without source re-encoding",
            flush=True,
        )
        transcribe_started = time.monotonic()
        with ThreadPoolExecutor(max_workers=min(workers, len(chunks))) as executor:
            futures = [
                (executor.submit(transcribe_chunk, client, path, model), offset)
                for path, offset in chunks
            ]
            results = [(future.result(), offset) for future, offset in futures]
        print(
            f"  transcribed {len(chunks)} Groq request(s) in "
            f"{time.monotonic() - transcribe_started:.1f}s",
            flush=True,
        )
        return combine_transcriptions(video, model, results)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download one video's audio at a time and transcribe it with Groq Whisper"
    )
    parser.add_argument("--slug", required=True)
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-upload-mb", type=int, default=DEFAULT_MAX_UPLOAD_MB)
    parser.add_argument("--chunk-seconds", type=int, default=DEFAULT_CHUNK_SECONDS)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--cookies-from-browser")
    parser.add_argument("--force-ipv4", action="store_true")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    return args


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        print("GROQ_API_KEY is not set; refusing to download audio.", file=sys.stderr)
        return 64

    yt_dlp = require_command("yt-dlp")
    ffmpeg = require_command("ffmpeg")
    ffprobe = require_command("ffprobe")

    corpus_dir = args.output_root.expanduser() / args.slug
    manifest_path = corpus_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pending = [
        video
        for video in manifest["videos"]
        if video.get("transcript_status") != "complete"
    ]
    if args.limit is not None:
        pending = pending[: args.limit]

    client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1", timeout=600)
    try:
        client.models.list()
    except AuthenticationError as exc:
        print(f"Groq credential rejected: {exc}", file=sys.stderr)
        return 65
    except RateLimitError as exc:
        print(f"Groq account is rate-limited before the run: {exc}", file=sys.stderr)
        return 75

    print(
        f"Corpus: {corpus_dir} | remaining={len(pending)} | model={args.model}",
        flush=True,
    )
    failures = 0
    for index, video in enumerate(pending, start=1):
        print(
            f"[{index}/{len(pending)}] {video['video_id']} {video['title'][:90]}",
            flush=True,
        )
        video["groq_attempts"] = int(video.get("groq_attempts", 0)) + 1
        try:
            payload, text = transcribe_video(
                client,
                video,
                args.model,
                args.max_upload_mb * 1_000_000,
                args.chunk_seconds,
                yt_dlp,
                ffmpeg,
                ffprobe,
                args.workers,
                args.cookies_from_browser,
                args.force_ipv4,
            )
            video_dir = corpus_dir / "videos" / video["video_id"]
            transcript_json = video_dir / "transcript.json"
            transcript_text = video_dir / "transcript.txt"
            write_json(transcript_json, payload)
            write_text(transcript_text, text)
            video.update(
                {
                    "transcript_status": "complete",
                    "transcript_source": f"groq:{args.model}",
                    "transcript_path": str(transcript_text),
                    "segment_count": payload["segment_count"],
                    "character_count": payload["character_count"],
                    "language": payload["language"],
                    "is_generated": True,
                    "fetched_at": payload["fetched_at"],
                    "last_error": "",
                }
            )
            print(
                f"  saved {payload['character_count']:,} chars / {payload['segment_count']:,} segments; temporary audio deleted",
                flush=True,
            )
        except (AuthenticationError, RateLimitError) as exc:
            video.update(
                {
                    "transcript_status": "groq_blocked",
                    "last_error": f"{type(exc).__name__}: {exc}",
                    "blocked_at": utc_now(),
                }
            )
            write_json(manifest_path, manifest)
            print(f"  Groq lane blocked; stopping cleanly: {exc}", file=sys.stderr)
            return 75
        except Exception as exc:
            failures += 1
            video.update(
                {
                    "transcript_status": "groq_failed",
                    "last_error": f"{type(exc).__name__}: {exc}",
                    "failed_at": utc_now(),
                }
            )
            print(f"  failed; temporary audio deleted: {type(exc).__name__}: {exc}", flush=True)
        write_json(manifest_path, manifest)

    completed = sum(
        1 for video in manifest["videos"] if video.get("transcript_status") == "complete"
    )
    if completed == manifest["video_count"]:
        build_corpus_exports(corpus_dir, manifest)
        print("Corpus complete: built corpus.txt and index.jsonl", flush=True)
        return 0
    print(f"Pass finished: complete={completed}/{manifest['video_count']} failures={failures}")
    return 2 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
