# Foundry YouTube Corpus

`scrape_channel_transcripts.py` builds a resumable text corpus from the
channel's YouTube **Videos** tab. The Videos-tab boundary deliberately excludes
the separate Shorts feed.

Data is written outside the repository:

```text
~/SISO_Foundry_Data/domains/youtube/channels/{slug}/
  manifest.json
  corpus.txt                  # built when all videos are complete
  index.jsonl                 # one machine-readable record per video
  videos/{video_id}/transcript.txt
  videos/{video_id}/transcript.json
```

The plain-text file is optimized for search and ingestion. The JSON copy keeps
the source title, URL, language, auto-generation flag, and timestamped caption
segments. Writes are atomic, and completed videos are skipped on the next run.

## Downstream podcast intelligence

This directory is the YouTube **acquisition adapter**. Podcast-specific
reconnaissance, evidence packets, contradiction analysis, theses, and decision
briefs belong under ../podcasts/. Raw corpus files remain outside git under
~/SISO_Foundry_Data; the podcast domain stores only project routers,
machine-readable state, schemas, and derived intelligence artifacts with exact
source pointers.

Run one pass:

```bash
python3 scrape_channel_transcripts.py \
  'https://www.youtube.com/@jackneel' \
  --slug jack-neel
```

Run until complete, with a two-hour cooldown after YouTube throttles the source
IP. The per-video delay is jittered from 8–12 seconds:

```bash
./resume_channel_transcripts.sh \
  'https://www.youtube.com/@jackneel' \
  jack-neel \
  --delay 8
```

Set `FOUNDRY_YOUTUBE_COOLDOWN_SECONDS` to change the retry cooldown, or
`FOUNDRY_YOUTUBE_INITIAL_COOLDOWN_SECONDS` to delay the first pass. An optional
requests-compatible proxy can be supplied with `--proxy`.

## Groq audio fallback

When the public caption endpoint is blocked or a video has no captions, the
Groq worker downloads one audio stream at a time. Groq-supported source formats
are uploaded directly or split into size-safe chunks with stream copy, avoiding
a slow local re-encode. Unsupported formats fall back to 16 kHz mono Opus. The
worker transcribes up to two chunks concurrently with
`whisper-large-v3-turbo`; all temporary media is deleted after each video,
leaving only transcript text and timestamp JSON.

The worker validates the credential before downloading any media:

```bash
export GROQ_API_KEY='...'
python3 transcribe_channel_groq.py --slug jack-neel
```

If YouTube requires a signed-in session, use an existing browser cookie store
without exporting cookie values to disk:

```bash
python3 transcribe_channel_groq.py \
  --slug jack-neel \
  --cookies-from-browser chrome
```

On dual-stack networks where one public address family is temporarily blocked,
prefer the still-public address over authenticated cookies:

```bash
python3 transcribe_channel_groq.py --slug jack-neel --force-ipv4
```

The key is read only from the environment and is never written to the corpus or
passed as a command-line argument.

For unattended runs, store it in the macOS Keychain service
`com.siso.groq-api`, then use `resume_channel_groq.sh`. The wrapper exports the
secret only to the worker process and sleeps for one hour only when Groq returns
a rate limit.
