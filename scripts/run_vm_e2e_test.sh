#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VM_NAME="${VM_NAME:-Aicustom}"
OUT_DIR="${AI_OS_VM_TEST_OUT_DIR:-${REPO_ROOT}/out}"
ARTIFACT_ROOT="${AI_OS_VM_TEST_ARTIFACT_ROOT:-/tmp/ai-os-vm-tests}"
ARTIFACT_DIR="${ARTIFACT_ROOT}/${VM_NAME}"
SERIAL_LOG="${VM_SERIAL_LOG:-${ARTIFACT_DIR}/serial.log}"
QEMU_LOG="${VM_QEMU_LOG:-${ARTIFACT_DIR}/qemu.log}"
FEATURE_REPORT="${VM_FEATURE_REPORT:-${ARTIFACT_ROOT}/feature-report.txt}"
DISK_IMAGE="${VM_DISK_IMAGE:-${ARTIFACT_DIR}/test_disk.qcow2}"
QEMU_BIN="${QEMU_BIN:-qemu-system-x86_64}"
QEMU_IMG="${QEMU_IMG:-qemu-img}"
VM_RAM_MB="${VM_RAM_MB:-4096}"
VM_CPUS="${VM_CPUS:-4}"
VM_TIMEOUT_SECONDS="${VM_TIMEOUT_SECONDS:-900}"
ORCHESTRATOR_TIMEOUT_SECONDS="${VM_ORCHESTRATOR_TIMEOUT_SECONDS:-480}"
RESULT_STATUS="UNKNOWN"
QEMU_PID=""
VM_START_SECONDS=0

declare -A MARKER_TIMES=()

log() {
    printf '[run_vm_e2e_test] %s\n' "$*"
}

fail() {
    log "ERROR: $*"
    exit 1
}

require_command() {
    local cmd="$1"
    command -v "${cmd}" >/dev/null 2>&1 || fail "Required command not found: ${cmd}"
}

resolve_iso_path() {
    local iso_path="${1:-}"
    if [[ -n "${iso_path}" ]]; then
        printf '%s\n' "${iso_path}"
        return 0
    fi

    find "${OUT_DIR}" -maxdepth 1 -type f -name 'ai-native-dev-os-*.iso' -printf '%T@ %p\n' 2>/dev/null \
        | sort -nr \
        | head -n 1 \
        | cut -d' ' -f2-
}

prepare_artifacts() {
    mkdir -p "${ARTIFACT_DIR}" "${ARTIFACT_ROOT}"
    : > "${SERIAL_LOG}"
    : > "${QEMU_LOG}"
    : > "${FEATURE_REPORT}"
    rm -f "${DISK_IMAGE}"
}

check_qemu_host() {
    require_command "${QEMU_BIN}"
    require_command "${QEMU_IMG}"
    [[ -e /dev/kvm ]] || fail "KVM is required for the VM test, but /dev/kvm is not present."
    [[ -r /dev/kvm && -w /dev/kvm ]] || fail "KVM is present, but the current user cannot access /dev/kvm."
}

create_disk_image() {
    "${QEMU_IMG}" create -f qcow2 "${DISK_IMAGE}" 20G >/dev/null
}

start_qemu() {
    local iso_path="$1"

    create_disk_image
    log "Booting ISO in QEMU: ${iso_path}"
    "${QEMU_BIN}" \
        -enable-kvm \
        -m "${VM_RAM_MB}" \
        -smp "${VM_CPUS}" \
        -cpu host \
        -boot d \
        -drive "file=${DISK_IMAGE},format=qcow2,if=virtio" \
        -cdrom "${iso_path}" \
        -nic user,model=virtio-net-pci \
        -device virtio-rng-pci \
        -display none \
        -serial "file:${SERIAL_LOG}" \
        -monitor none \
        -no-reboot \
        >"${QEMU_LOG}" 2>&1 &
    QEMU_PID="$!"
    VM_START_SECONDS="${SECONDS}"
}

stop_qemu() {
    if [[ -n "${QEMU_PID}" ]] && kill -0 "${QEMU_PID}" 2>/dev/null; then
        kill "${QEMU_PID}" >/dev/null 2>&1 || true
        wait "${QEMU_PID}" >/dev/null 2>&1 || true
    fi
}

serial_log_contains() {
    local needle="$1"
    [[ -f "${SERIAL_LOG}" ]] && grep -Fq "${needle}" "${SERIAL_LOG}"
}

record_marker_time() {
    local key="$1"
    local marker="$2"
    if [[ -n "${MARKER_TIMES[${key}]:-}" ]]; then
        return 0
    fi
    if serial_log_contains "${marker}"; then
        MARKER_TIMES["${key}"]="$((SECONDS - VM_START_SECONDS))"
    fi
}

coding_task_validated() {
    serial_log_contains "AIOS_STAGE:CLI_CODING_BLOCK_OK" || serial_log_contains "AIOS_STAGE:CLI_CODING_TASK_OK"
}

wait_for_vm_result() {
    local deadline=$((SECONDS + VM_TIMEOUT_SECONDS))

    log "Waiting up to ${VM_TIMEOUT_SECONDS}s for QEMU installer and runtime markers..."
    while (( SECONDS < deadline )); do
        if serial_log_contains "AIOS_STAGE:INSTALL_FAILED:"; then
            RESULT_STATUS="INSTALL_FAILED"
            return 1
        fi

        record_marker_time "model_downloads_background" "AIOS_STAGE:MODEL_DOWNLOADS_BACKGROUND"
        record_marker_time "install_complete" "AIOS_STAGE:INSTALL_COMPLETE"
        record_marker_time "orchestrator_ready" "AIOS_STAGE:ORCHESTRATOR_READY"
        record_marker_time "simple_task" "AIOS_STAGE:CLI_SIMPLE_TASK_OK"
        record_marker_time "planning_task" "AIOS_STAGE:CLI_PLANNING_TASK_OK"
        record_marker_time "models_ok" "AIOS_STAGE:CLI_MODELS_OK:"
        record_marker_time "ready_with_background_downloads" "AIOS_STAGE:READY_WITH_BACKGROUND_DOWNLOADS"
        record_marker_time "healthcheck_ok" "AIOS_STAGE:HEALTHCHECK_OK"

        if [[ -z "${MARKER_TIMES[orchestrator_ready]:-}" ]] \
            && (( SECONDS - VM_START_SECONDS >= ORCHESTRATOR_TIMEOUT_SECONDS )); then
            RESULT_STATUS="ORCHESTRATOR_TIMEOUT"
            return 1
        fi

        if serial_log_contains "AIOS_STAGE:INSTALL_COMPLETE" \
            && serial_log_contains "AIOS_STAGE:MODEL_DOWNLOADS_BACKGROUND" \
            && serial_log_contains "AIOS_STAGE:ORCHESTRATOR_READY" \
            && serial_log_contains "AIOS_STAGE:CLI_SIMPLE_TASK_OK" \
            && serial_log_contains "AIOS_STAGE:CLI_PLANNING_TASK_OK" \
            && serial_log_contains "AIOS_STAGE:CLI_MODELS_OK:" \
            && serial_log_contains "AIOS_STAGE:READY_WITH_BACKGROUND_DOWNLOADS" \
            && serial_log_contains "AIOS_STAGE:HEALTHCHECK_OK" \
            && coding_task_validated; then
            RESULT_STATUS="PASS"
            return 0
        fi

        if [[ -n "${QEMU_PID}" ]] && ! kill -0 "${QEMU_PID}" 2>/dev/null; then
            wait "${QEMU_PID}" >/dev/null 2>&1 || true
            RESULT_STATUS="QEMU_EXITED"
            return 1
        fi

        sleep 2
    done

    RESULT_STATUS="TIMEOUT"
    return 1
}

marker_status() {
    local key="$1"
    if [[ -n "${MARKER_TIMES[${key}]:-}" ]]; then
        printf 'PASS (%ss)\n' "${MARKER_TIMES[${key}]}"
    else
        printf 'FAIL\n'
    fi
}

latest_serial_value() {
    local prefix="$1"
    if [[ ! -f "${SERIAL_LOG}" ]]; then
        return 0
    fi
    grep -F "${prefix}" "${SERIAL_LOG}" | tail -n 1 | sed "s/^.*${prefix}//" || true
}

generate_feature_report() {
    local iso_path="$1"
    local overall="FAIL"
    local coding_status="FAIL"
    local coding_message
    local model_snapshot

    if [[ "${RESULT_STATUS}" == "PASS" ]]; then
        overall="PASS"
    fi

    if serial_log_contains "AIOS_STAGE:CLI_CODING_BLOCK_OK"; then
        coding_status="PASS (blocked while coding model unavailable)"
    elif serial_log_contains "AIOS_STAGE:CLI_CODING_TASK_OK"; then
        coding_status="PASS (coding model already ready and task executed)"
    fi

    coding_message="$(latest_serial_value "AIOS_CLI_CODING_TASK_MESSAGE:")"
    model_snapshot="$(latest_serial_value "AIOS_MODELS_SNAPSHOT:")"

    mkdir -p "$(dirname "${FEATURE_REPORT}")"
    {
        printf 'ISO build status: PASS\n'
        printf 'ISO path: %s\n' "${iso_path}"
        printf 'Install success: %s\n' "$(marker_status install_complete)"
        printf 'Background downloads started: %s\n' "$(marker_status model_downloads_background)"
        printf 'Orchestrator readiness: %s\n' "$(marker_status orchestrator_ready)"
        printf 'Ready with background downloads: %s\n' "$(marker_status ready_with_background_downloads)"
        printf 'Simple task result: %s\n' "$(marker_status simple_task)"
        printf 'Planning task result: %s\n' "$(marker_status planning_task)"
        printf 'Model status command: %s\n' "$(marker_status models_ok)"
        printf 'Coding task behavior: %s\n' "${coding_status}"
        if [[ -n "${coding_message}" ]]; then
            printf 'Coding task message: %s\n' "${coding_message}"
        fi
        if [[ -n "${model_snapshot}" ]]; then
            printf 'Model states: %s\n' "${model_snapshot}"
        else
            printf 'Model states: unavailable\n'
        fi
        printf 'Overall: %s\n' "${overall}"
        printf 'Result status: %s\n' "${RESULT_STATUS}"
        printf 'Serial log: %s\n' "${SERIAL_LOG}"
        printf 'QEMU log: %s\n' "${QEMU_LOG}"
        printf 'Disk image: %s\n' "${DISK_IMAGE}"
    } > "${FEATURE_REPORT}"
}

main() {
    local iso_path=""

    trap 'generate_feature_report "${iso_path:-}"; stop_qemu' EXIT

    iso_path="$(resolve_iso_path "${1:-}")"
    [[ -n "${iso_path}" ]] || fail "No ISO path was provided and no built ISO was found in ${OUT_DIR}."
    [[ -f "${iso_path}" ]] || fail "ISO path does not exist: ${iso_path}"

    check_qemu_host
    prepare_artifacts
    start_qemu "${iso_path}"

    if ! wait_for_vm_result; then
        if [[ -f "${SERIAL_LOG}" ]]; then
            log "Last serial log lines:"
            tail -n 80 "${SERIAL_LOG}" || true
        fi
        fail "QEMU end-to-end verification failed."
    fi

    log "QEMU end-to-end verification passed."
}

main "$@"
