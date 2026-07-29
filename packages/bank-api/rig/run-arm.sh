#!/usr/bin/env bash
# run-arm.sh <ARM>  — builds the arm's sandbox, installs its declared deps,
# copies its webhook.mjs + the grader, runs the grader, captures the verdict.
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
ARM="$1"
HERE="$(cd "$(dirname "$0")" && pwd)"
ARMDIR="$HERE/arms/$ARM"
RUNDIR="$HERE/run/$ARM"

[ -f "$ARMDIR/webhook.mjs" ] || { echo "no webhook.mjs in $ARMDIR"; exit 1; }
[ -f "$ARMDIR/deps.json" ]   || { echo "no deps.json in $ARMDIR"; exit 1; }

rm -rf "$RUNDIR"; mkdir -p "$RUNDIR"
# package.json from the arm's declared deps
DEPS=$(cat "$ARMDIR/deps.json")
cat > "$RUNDIR/package.json" <<EOF
{ "name": "arm-$ARM", "private": true, "type": "module", "dependencies": $DEPS }
EOF
cp "$ARMDIR/webhook.mjs" "$RUNDIR/webhook.mjs"
cp "$HERE/grade.mjs" "$RUNDIR/grade.mjs"

echo "[$ARM] installing: $DEPS"
( cd "$RUNDIR" && npm install --no-audit --no-fund --loglevel=error >/dev/null 2>&1 ) \
  || { echo "[$ARM] npm install FAILED"; echo '{"working":false,"where":"npm_install_failed"}' > "$RUNDIR/_verdict.json"; exit 0; }

echo "[$ARM] grading..."
( cd "$RUNDIR" && node grade.mjs "./webhook.mjs" ) | tee "$RUNDIR/_verdict.json"
