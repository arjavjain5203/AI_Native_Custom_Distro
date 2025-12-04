#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${AI_OS_SYNC_SOURCE_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
RUNTIME_TARGET="${AI_OS_SYNC_RUNTIME_TARGET:-${REPO_ROOT}/archlive/airootfs/opt/ai-os}"

printf 'Syncing runtime into %s\n' "${RUNTIME_TARGET}"

mkdir -p "${RUNTIME_TARGET}"
rm -rf \
  "${RUNTIME_TARGET}/ai_core" \
  "${RUNTIME_TARGET}/ai-os" \
  "${RUNTIME_TARGET}/ai-daemon" \
  "${RUNTIME_TARGET}/requirements.txt"

cp -a "${REPO_ROOT}/ai_core" "${RUNTIME_TARGET}/ai_core"
cp -a "${REPO_ROOT}/ai-os" "${RUNTIME_TARGET}/ai-os"
cp -a "${REPO_ROOT}/ai-daemon" "${RUNTIME_TARGET}/ai-daemon"
cp -a "${REPO_ROOT}/requirements.txt" "${RUNTIME_TARGET}/requirements.txt"

find "${RUNTIME_TARGET}/ai_core" -type d -name '__pycache__' -exec rm -rf {} +
find "${RUNTIME_TARGET}/ai_core" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

printf 'Runtime sync complete.\n'
