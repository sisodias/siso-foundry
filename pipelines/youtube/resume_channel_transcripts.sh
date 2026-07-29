#!/usr/bin/env bash
# Run the channel transcript scraper until it completes, cooling down on blocks.

set -u

if [[ $# -lt 2 ]]; then
  echo "usage: $0 CHANNEL_URL SLUG [extra scraper args...]" >&2
  exit 64
fi

channel_url="$1"
channel_slug="$2"
shift 2

script_dir="$(cd "$(dirname "$0")" && pwd)"
cooldown_seconds="${FOUNDRY_YOUTUBE_COOLDOWN_SECONDS:-7200}"
initial_cooldown_seconds="${FOUNDRY_YOUTUBE_INITIAL_COOLDOWN_SECONDS:-0}"

if (( initial_cooldown_seconds > 0 )); then
  echo "Initial cooldown for ${initial_cooldown_seconds}s."
  sleep "$initial_cooldown_seconds"
fi

while true; do
  python3 "$script_dir/scrape_channel_transcripts.py" \
    "$channel_url" \
    --slug "$channel_slug" \
    --no-refresh \
    "$@"
  run_status=$?

  if [[ $run_status -eq 0 ]]; then
    echo "Transcript corpus complete."
    exit 0
  fi

  echo "Scraper exited with status $run_status; cooling down for ${cooldown_seconds}s."
  sleep "$cooldown_seconds"
done
