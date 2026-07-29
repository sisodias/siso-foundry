#!/usr/bin/env python3
"""Build a resumable transcript corpus from a YouTube channel's Videos tab.

The Videos tab is used deliberately: YouTube keeps Shorts in a separate tab, so
the discovery boundary does not depend on a fragile duration heuristic.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig


SCHEMA_VERSION = "foundry.youtube-corpus.v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, payload: Any) -> None:
    """Atomically write JSON so an interrupted run cannot corrupt its state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_text(path: Path, value: str) -> None:
    """Atomically write UTF-8 text."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(value.rstrip() + "\n", encoding="utf-8")
    temporary.replace(path)


def videos_tab_url(channel_url: str) -> str:
    base = channel_url.rstrip("/")
    for suffix in ("/videos", "/shorts", "/streams", "/featured"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return f"{base}/videos"


def discover_videos(channel_url: str) -> dict[str, Any]:
    """Use yt-dlp's flat channel extractor to enumerate long-form uploads."""
    source_url = videos_tab_url(channel_url)
    command = [
        "yt-dlp",
        "--flat-playlist",
        "--ignore-errors",
        "--no-warnings",
        "--dump-single-json",
        source_url,
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "yt-dlp channel discovery failed")

    payload = json.loads(result.stdout)
    videos: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in payload.get("entries") or []:
        video_id = str(entry.get("id") or "").strip()
        if len(video_id) != 11 or video_id in seen:
            continue
        seen.add(video_id)
        videos.append(
            {
                "video_id": video_id,
                "title": entry.get("title") or "Untitled",
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "transcript_status": "pending",
                "attempts": 0,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "channel": {
            "name": payload.get("channel") or payload.get("uploader") or "",
            "channel_id": payload.get("channel_id") or payload.get("id") or "",
            "channel_url": channel_url.rstrip("/"),
            "discovery_url": source_url,
            "source_tab": "videos",
            "shorts_included": False,
        },
        "discovered_at": utc_now(),
        "video_count": len(videos),
        "videos": videos,
    }


def merge_manifest(existing: dict[str, Any], discovered: dict[str, Any]) -> dict[str, Any]:
    """Refresh discovery metadata without losing transcript progress."""
    previous = {item["video_id"]: item for item in existing.get("videos", [])}
    for item in discovered["videos"]:
        old = previous.get(item["video_id"], {})
        for key in (
            "transcript_status",
            "transcript_source",
            "transcript_path",
            "segment_count",
            "character_count",
            "language",
            "is_generated",
            "fetched_at",
            "attempts",
            "last_error",
        ):
            if key in old:
                item[key] = old[key]
    return discovered


def fetch_transcript(
    video: dict[str, Any], proxy_url: str | None = None
) -> tuple[dict[str, Any], str]:
    proxy_config = None
    if proxy_url:
        proxy_config = GenericProxyConfig(http_url=proxy_url, https_url=proxy_url)
    transcript = YouTubeTranscriptApi(proxy_config=proxy_config).fetch(
        video["video_id"], languages=["en"]
    )
    segments = [
        {
            "start": round(segment.start, 3),
            "duration": round(segment.duration, 3),
            "text": segment.text,
        }
        for segment in transcript
    ]
    text = "\n".join(
        segment["text"].strip() for segment in segments if segment["text"].strip()
    )
    transcript_duration = max(
        (segment["start"] + segment["duration"] for segment in segments),
        default=0,
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "video_id": video["video_id"],
        "title": video["title"],
        "url": video["url"],
        "source": "youtube-transcript-api",
        "language": transcript.language,
        "language_code": transcript.language_code,
        "is_generated": transcript.is_generated,
        "fetched_at": utc_now(),
        "segment_count": len(segments),
        "character_count": len(text),
        "transcript_duration_seconds": round(transcript_duration, 3),
        "segments": segments,
    }
    return payload, text


def default_output_root() -> Path:
    foundry_data = os.environ.get("FOUNDRY_DATA")
    root = Path(foundry_data).expanduser() if foundry_data else Path.home() / "SISO_Foundry_Data"
    return root / "domains" / "youtube" / "channels"


def build_corpus_exports(corpus_dir: Path, manifest: dict[str, Any]) -> None:
    """Build convenient whole-corpus exports after every video is complete."""
    text_parts: list[str] = []
    index_lines: list[str] = []
    for video in manifest["videos"]:
        transcript_path = Path(video["transcript_path"])
        text_parts.extend(
            [
                f"# {video['title']}",
                video["url"],
                "",
                transcript_path.read_text(encoding="utf-8").strip(),
                "",
                "---",
                "",
            ]
        )
        index_lines.append(json.dumps(video, ensure_ascii=False))
    write_text(corpus_dir / "corpus.txt", "\n".join(text_parts))
    write_text(corpus_dir / "index.jsonl", "\n".join(index_lines))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape a channel's non-Short videos and fetch their public transcripts"
    )
    parser.add_argument("channel_url")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    parser.add_argument(
        "--delay",
        type=float,
        default=8.0,
        help="Seconds between videos (default: 8; keep conservative to avoid IP throttling)",
    )
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument(
        "--proxy",
        help="Optional requests proxy URL, for example socks5h://127.0.0.1:9050",
    )
    parser.add_argument("--limit", type=int, help="Process only N pending videos")
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Reuse the saved manifest instead of refreshing the Videos tab",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    corpus_dir = args.output_root.expanduser() / args.slug
    manifest_path = corpus_dir / "manifest.json"

    if args.no_refresh and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        print(f"Discovering {videos_tab_url(args.channel_url)}", flush=True)
        discovered = discover_videos(args.channel_url)
        if manifest_path.exists():
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = merge_manifest(existing, discovered)
        else:
            manifest = discovered
        write_json(manifest_path, manifest)

    pending = [
        video
        for video in manifest["videos"]
        if video.get("transcript_status") != "complete"
    ]
    if args.limit is not None:
        pending = pending[: args.limit]

    print(
        f"Corpus: {corpus_dir} | discovered={manifest['video_count']} | pending={len(pending)}",
        flush=True,
    )
    failures = 0
    for index, video in enumerate(pending, start=1):
        video_dir = corpus_dir / "videos" / video["video_id"]
        transcript_json = video_dir / "transcript.json"
        transcript_text = video_dir / "transcript.txt"

        if transcript_json.exists() and transcript_text.exists():
            saved = json.loads(transcript_json.read_text(encoding="utf-8"))
            video.update(
                {
                    "transcript_status": "complete",
                    "transcript_source": saved.get("source"),
                    "transcript_path": str(transcript_text),
                    "segment_count": saved.get("segment_count", 0),
                    "character_count": saved.get("character_count", 0),
                    "language": saved.get("language", ""),
                    "is_generated": saved.get("is_generated"),
                    "fetched_at": saved.get("fetched_at", ""),
                    "last_error": "",
                }
            )
            write_json(manifest_path, manifest)
            continue

        print(
            f"[{index}/{len(pending)}] {video['video_id']} {video['title'][:90]}",
            flush=True,
        )
        last_error = ""
        for attempt in range(1, args.retries + 1):
            video["attempts"] = int(video.get("attempts", 0)) + 1
            try:
                payload, text = fetch_transcript(video, proxy_url=args.proxy)
                write_json(transcript_json, payload)
                write_text(transcript_text, text)
                video.update(
                    {
                        "transcript_status": "complete",
                        "transcript_source": payload["source"],
                        "transcript_path": str(transcript_text),
                        "segment_count": payload["segment_count"],
                        "character_count": payload["character_count"],
                        "language": payload["language"],
                        "is_generated": payload["is_generated"],
                        "fetched_at": payload["fetched_at"],
                        "last_error": "",
                    }
                )
                print(
                    f"  saved {payload['character_count']:,} chars / {payload['segment_count']:,} segments",
                    flush=True,
                )
                break
            except Exception as exc:  # API exposes many version-specific error subclasses.
                last_error = f"{type(exc).__name__}: {exc}"
                print(f"  attempt {attempt}/{args.retries} failed: {last_error[:300]}", flush=True)
                if type(exc).__name__ in {"IpBlocked", "RequestBlocked", "TooManyRequests"}:
                    video.update(
                        {
                            "transcript_status": "blocked",
                            "last_error": last_error,
                            "blocked_at": utc_now(),
                        }
                    )
                    write_json(manifest_path, manifest)
                    print(
                        "  source IP is throttled; stopping cleanly for a later resume",
                        flush=True,
                    )
                    return 3
                if attempt < args.retries:
                    time.sleep(max(args.delay, 1.0) * attempt)
        else:
            failures += 1
            video.update(
                {
                    "transcript_status": "failed",
                    "last_error": last_error,
                    "failed_at": utc_now(),
                }
            )

        write_json(manifest_path, manifest)
        if index < len(pending):
            minimum_delay = max(args.delay, 0)
            time.sleep(random.uniform(minimum_delay, minimum_delay * 1.5))

    counts: dict[str, int] = {}
    for video in manifest["videos"]:
        status = video.get("transcript_status", "pending")
        counts[status] = counts.get(status, 0) + 1
    if counts.get("complete", 0) == manifest["video_count"]:
        build_corpus_exports(corpus_dir, manifest)
        print("Built corpus.txt and index.jsonl", flush=True)
    print(f"Finished: {counts}", flush=True)
    return 2 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
