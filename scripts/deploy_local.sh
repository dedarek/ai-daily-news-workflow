#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="${REPO_ROOT}/skill"
TARGET_ROOT="${CODEX_HOME:-${HOME}/.codex}/skills"
TARGET="${TARGET_ROOT}/ai-daily-news"

mkdir -p "${TARGET_ROOT}"

if [ -e "${TARGET}" ] && [ ! -L "${TARGET}" ]; then
  echo "Refusing to replace non-symlink deployment: ${TARGET}" >&2
  exit 1
fi

ln -sfn "${SOURCE}" "${TARGET}"
echo "Deployed ai-daily-news -> ${TARGET}"
