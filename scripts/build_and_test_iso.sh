#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${AI_OS_VM_TEST_OUT_DIR:-${REPO_ROOT}/out}"
WORK_DIR="${AI_OS_ARCHISO_WORK_DIR:-${REPO_ROOT}/archiso-work}"

log() {
    printf '[build_and_test_iso] %s\n' "$*"
}

fail() {
    log "ERROR: $*"
    exit 1
}

run_mkarchiso() {
    if [[ "${EUID}" -eq 0 ]]; then
        mkarchiso -v -w "${WORK_DIR}" -o "${OUT_DIR}" "${REPO_ROOT}/archlive"
        return 0
    fi

    if ! sudo -n mkarchiso --version >/dev/null 2>&1; then
        fail "mkarchiso needs root. Configure passwordless sudo for mkarchiso or run this script as root."
    fi

    sudo -n mkarchiso -v -w "${WORK_DIR}" -o "${OUT_DIR}" "${REPO_ROOT}/archlive"
}

latest_iso_path() {
    find "${OUT_DIR}" -maxdepth 1 -type f -name 'ai-native-dev-os-*.iso' -printf '%T@ %p\n' 2>/dev/null \
        | sort -nr \
        | head -n 1 \
        | cut -d' ' -f2-
}

main() {
    local iso_path=""

    mkdir -p "${OUT_DIR}"

    log "Syncing runtime..."
    "${REPO_ROOT}/scripts/sync_runtime.sh"

    log "Running pre-ISO checks..."
    "${REPO_ROOT}/scripts/pre_iso_check.sh"

    log "Building ISO..."
    run_mkarchiso

    iso_path="$(latest_iso_path)"
    [[ -n "${iso_path}" ]] || fail "No ISO was produced in ${OUT_DIR}."
    [[ -f "${iso_path}" ]] || fail "Latest ISO path does not exist: ${iso_path}"
    log "Latest ISO: ${iso_path}"

    log "Running QEMU end-to-end test..."
    "${REPO_ROOT}/scripts/run_vm_e2e_test.sh" "${iso_path}"
}

main "$@"
