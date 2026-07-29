#!/usr/bin/env bash
# Run the Groq audio lane, cooling down only when the Groq API rate-limits it.

set -u

script_dir="$(cd "$(dirname "$0")" && pwd)"
keychain_service="${GROQ_KEYCHAIN_SERVICE:-com.siso.groq-api}"
cooldown_seconds="${FOUNDRY_GROQ_COOLDOWN_SECONDS:-3600}"
account_name="$(id -un)"

while true; do
  task_secret="$(security find-generic-password -a "$account_name" -s "$keychain_service" -w 2>/dev/null || true)"
  if [[ -z "$task_secret" ]]; then
    echo "Groq credential is missing from Keychain service: $keychain_service" >&2
    exit 64
  fi

  export GROQ_API_KEY="$task_secret"
  unset task_secret
  python3 "$script_dir/transcribe_channel_groq.py" "$@"
  run_status=$?
  unset GROQ_API_KEY

  if [[ $run_status -ne 75 ]]; then
    exit "$run_status"
  fi

  echo "Groq lane rate-limited; cooling down for ${cooldown_seconds}s."
  sleep "$cooldown_seconds"
done
