#!/usr/bin/env bash
# Snapshot, generate, render and pair a list of sites.
#   scripts/run.sh <out-root> <url>...
# Each site goes to <out-root>/<host>/. Needs ~/.config/ui-rl/judge.env for the model.
set -euo pipefail
cd "$(dirname "$0")/.."
root=$1; shift
. ~/.config/ui-rl/judge.env
for url in "$@"; do
  host=$(node -e 'console.log(new URL(process.argv[1]).hostname.replace(/^www\./, ""))' "$url")
  dir=$root/$host
  echo "=== $url → $dir"
  rm -rf "$dir"
  node scripts/snapshot.mjs "$url" "$dir"
  NODE_USE_ENV_PROXY=1 node --no-warnings scripts/generate.mjs "$dir" "${COUNT:-2}"
  node scripts/render.mjs "$dir"
  python3 -I scripts/pairs.py "$dir"
done
