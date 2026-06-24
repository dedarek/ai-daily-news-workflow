#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

find . -path './.venv' -prune -o -type f -name '*.py' -print0 |
  while IFS= read -r -d '' file; do
    python3 -m py_compile "${file}"
  done

python3 skill/scripts/validate_html_quality.py \
  --date 2026-06-24 \
  --path skill/samples/2026-06-24.html

test -x "$(command -v ffmpeg)"
test -x "$(command -v ffprobe)"

echo "Smoke test passed."
