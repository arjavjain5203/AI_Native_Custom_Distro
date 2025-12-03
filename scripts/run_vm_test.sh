#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VM_NAME="${VM_NAME:-Aicustom}"
OUT_DIR="${AI_OS_VM_TEST_OUT_DIR:-${REPO_ROOT}/out}"
STORAGE_CTL="${VBOX_STORAGE_CTL:-IDE}"
DVD_PORT="${VBOX_DVD_PORT:-1}"
DVD_DEVICE="${VBOX_DVD_DEVICE:-0}"
BOOT_TIMEOUT_SECONDS="${VM_BOOT_TIMEOUT_SECONDS:-${VM_BOOT_WAIT_SECONDS:-900}}"
VBOXMANAGE="${VBOXMANAGE:-VBoxManage}"
ARTIFACT_ROOT="${AI_OS_VM_TEST_ARTIFACT_ROOT:-/tmp/ai-os-vm-tests}"
ARTIFACT_DIR="${ARTIFACT_ROOT}/${VM_NAME}"
WORK_DIR_ROOT="${AI_OS_VM_TEST_WORK_ROOT:-${REPO_ROOT}/.vm-test-work}"
WORK_DIR_DEFAULT="${WORK_DIR_ROOT}/${VM_NAME}-$(date +%Y%m%d-%H%M%S)"
WORK_DIR="${AI_OS_VM_TEST_WORK_DIR:-${WORK_DIR_DEFAULT}}"
SERIAL_LOG="${VM_SERIAL_LOG:-${ARTIFACT_DIR}/serial.log}"
VM_INFO_LOG="${VM_INFO_LOG:-${ARTIFACT_DIR}/showvminfo.txt}"
UART1_IOBASE="${VBOX_UART1_IOBASE:-0x3F8}"
UART1_IRQ="${VBOX_UART1_IRQ:-4}"
KEEP_VM_RUNNING_ON_FAILURE="${VM_KEEP_RUNNING_ON_FAILURE:-0}"
RESULT_STATUS="UNKNOWN"
ORIGINAL_UART1_STATE=""
VM_STARTED=0

log() {
    printf '[run_vm_test] %s\n' "$*"
}

fail() {
    log "ERROR: $*"
    exit 1
}

require_command() {
    local cmd="$1"
    command -v "${cmd}" >/dev/null 2>&1 || fail "Required command not found: ${cmd}"
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
    find "${OUT_DIR}" -maxdepth 1 -type f -name '*.iso' -printf '%T@ %p\n' 2>/dev/null \
        | sort -nr \
        | head -n 1 \
        | cut -d' ' -f2-
}

check_virtualbox_host() {
    require_command "${VBOXMANAGE}"

    if ! "${VBOXMANAGE}" showvminfo "${VM_NAME}" >/dev/null 2>&1; then
        fail "VirtualBox cannot access VM '${VM_NAME}'. If you still see /dev/vboxdrv errors, fix the VirtualBox host first."
    fi
}

prepare_artifacts() {
    mkdir -p "${OUT_DIR}" "${WORK_DIR}" "${ARTIFACT_DIR}"
    : > "${SERIAL_LOG}"
    : > "${VM_INFO_LOG}"
}

capture_vm_info() {
    "${VBOXMANAGE}" showvminfo "${VM_NAME}" > "${VM_INFO_LOG}" 2>&1 || true
}

remember_uart1_state() {
    ORIGINAL_UART1_STATE="$("${VBOXMANAGE}" showvminfo "${VM_NAME}" | awk -F: '/^UART 1:/ {sub(/^ +/, "", $2); print $2; exit}')"
}

configure_serial_console() {
    log "Configuring UART1 serial log at ${SERIAL_LOG}..."
    remember_uart1_state
    "${VBOXMANAGE}" modifyvm "${VM_NAME}" --uart1 "${UART1_IOBASE}" "${UART1_IRQ}"
    "${VBOXMANAGE}" modifyvm "${VM_NAME}" --uartmode1 file "${SERIAL_LOG}"
}

restore_serial_console() {
    if [[ "${ORIGINAL_UART1_STATE}" == disabled* ]]; then
        log "Restoring UART1 to disabled state..."
        "${VBOXMANAGE}" modifyvm "${VM_NAME}" --uart1 off >/dev/null 2>&1 || true
    fi
}

serial_log_contains() {
    local needle="$1"
    [[ -f "${SERIAL_LOG}" ]] && grep -Fq "${needle}" "${SERIAL_LOG}"
}

wait_for_install_result() {
    local deadline=$((SECONDS + BOOT_TIMEOUT_SECONDS))

    log "Waiting up to ${BOOT_TIMEOUT_SECONDS}s for installer markers..."
    while (( SECONDS < deadline )); do
        if serial_log_contains "AIOS_STAGE:INSTALL_FAILED:"; then
            RESULT_STATUS="INSTALL_FAILED"
            return 1
        fi

        if serial_log_contains "AIOS_STAGE:INSTALL_COMPLETE" \
            && serial_log_contains "AIOS_STAGE:HEALTHCHECK_OK" \
            && (serial_log_contains "AIOS_STAGE:MODEL_PULL_OK:" || serial_log_contains "AIOS_STAGE:MODELS_ALREADY_PRESENT"); then
            RESULT_STATUS="INSTALL_COMPLETE"
            return 0
        fi

        sleep 5
    done

    RESULT_STATUS="TIMEOUT"
    return 1
}

main() {
    local iso_path=""
    trap 'capture_vm_info; restore_serial_console; if [[ ${VM_STARTED} -eq 1 && "${KEEP_VM_RUNNING_ON_FAILURE}" != "1" ]]; then "${VBOXMANAGE}" controlvm "${VM_NAME}" poweroff >/dev/null 2>&1 || true; fi' EXIT

    check_virtualbox_host
    prepare_artifacts

    log "Syncing runtime..."
    "${REPO_ROOT}/scripts/sync_runtime.sh"

    log "Running pre-ISO checks..."
    "${REPO_ROOT}/scripts/pre_iso_check.sh"

    log "Building ISO..."
    run_mkarchiso

    iso_path="$(latest_iso_path)"
    [[ -n "${iso_path}" ]] || fail "No ISO was produced in ${OUT_DIR}."
    log "Latest ISO: ${iso_path}"

    log "Powering off VM if it is already running..."
    "${VBOXMANAGE}" controlvm "${VM_NAME}" poweroff >/dev/null 2>&1 || true

    configure_serial_console

    log "Detaching old ISO from ${STORAGE_CTL} port ${DVD_PORT} device ${DVD_DEVICE}..."
    "${VBOXMANAGE}" storageattach "${VM_NAME}" \
        --storagectl "${STORAGE_CTL}" \
        --port "${DVD_PORT}" \
        --device "${DVD_DEVICE}" \
        --medium none >/dev/null 2>&1 || true

    log "Attaching new ISO..."
    "${VBOXMANAGE}" storageattach "${VM_NAME}" \
        --storagectl "${STORAGE_CTL}" \
        --port "${DVD_PORT}" \
        --device "${DVD_DEVICE}" \
        --type dvddrive \
        --medium "${iso_path}"

    log "Starting VM headless..."
    "${VBOXMANAGE}" startvm "${VM_NAME}" --type headless
    VM_STARTED=1

    if ! wait_for_install_result; then
        log "Installer verification failed with status: ${RESULT_STATUS}"
        log "Artifacts:"
        log "  serial log: ${SERIAL_LOG}"
        log "  vm info: ${VM_INFO_LOG}"
        if [[ -f "${SERIAL_LOG}" ]]; then
            log "Last serial log lines:"
            tail -n 80 "${SERIAL_LOG}" || true
        fi
        fail "VirtualBox install verification failed."
    fi

    log "Stopping VM..."
    "${VBOXMANAGE}" controlvm "${VM_NAME}" poweroff
    VM_STARTED=0

    log "VM ISO install verification complete."
    log "Status: ${RESULT_STATUS}"
    log "Artifacts:"
    log "  serial log: ${SERIAL_LOG}"
    log "  vm info: ${VM_INFO_LOG}"
}

main "$@"
