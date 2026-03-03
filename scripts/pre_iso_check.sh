#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_ROOT="${REPO_ROOT}/archlive/airootfs/opt/ai-os"
INSTALLER_SERVICE="${REPO_ROOT}/archlive/airootfs/etc/systemd/system/ai-os-installer.service"
POSTINSTALL_SERVICE="${REPO_ROOT}/archlive/airootfs/etc/systemd/system/ai-os-postinstall-check.service"
DAEMON_SERVICE="${REPO_ROOT}/archlive/airootfs/etc/systemd/system/ai-os.service"
PACKAGES_FILE="${REPO_ROOT}/archlive/packages.x86_64"
DEFAULT_TARGET="${REPO_ROOT}/archlive/airootfs/etc/systemd/system/default.target"
TTY1_AUTOLOGIN="${REPO_ROOT}/archlive/airootfs/etc/systemd/system/getty@tty1.service.d/autologin.conf"

log() {
    printf '[pre-iso-check] %s\n' "$*"
}

fail() {
    log "ERROR: $*"
    exit 1
}

require_file() {
    local path="$1"
    [[ -e "${path}" ]] || fail "Missing required path: ${path}"
}

require_executable() {
    local path="$1"
    require_file "${path}"
    [[ -x "${path}" ]] || fail "Expected executable: ${path}"
}

check_runtime_sync() {
    log "Checking synced runtime content..."
    diff -qr -x '__pycache__' "${REPO_ROOT}/ai_core" "${RUNTIME_ROOT}/ai_core" >/dev/null \
        || fail "archlive runtime ai_core is out of sync. Run scripts/sync_runtime.sh."
    diff -q "${REPO_ROOT}/ai-os" "${RUNTIME_ROOT}/ai-os" >/dev/null \
        || fail "archlive runtime ai-os launcher is out of sync. Run scripts/sync_runtime.sh."
    diff -q "${REPO_ROOT}/ai-daemon" "${RUNTIME_ROOT}/ai-daemon" >/dev/null \
        || fail "archlive runtime ai-daemon launcher is out of sync. Run scripts/sync_runtime.sh."
    diff -q "${REPO_ROOT}/requirements.txt" "${RUNTIME_ROOT}/requirements.txt" >/dev/null \
        || fail "archlive runtime requirements are out of sync. Run scripts/sync_runtime.sh."
}

check_unit_file() {
    log "Checking systemd unit ordering..."
    grep -Eq '^WantedBy=multi-user\.target$' "${INSTALLER_SERVICE}" \
        || fail "ai-os-installer.service must be enabled for multi-user.target."
    grep -Eq '^Type=idle$' "${INSTALLER_SERVICE}" \
        || fail "ai-os-installer.service must use Type=idle."
    ! grep -Eq '^Standard(Input|Output|Error)=' "${INSTALLER_SERVICE}" \
        || fail "ai-os-installer.service must not bind directly to tty input/output."
    ! grep -Eq '^TTY(Path|Reset|VHangup|VTDisallocate)=' "${INSTALLER_SERVICE}" \
        || fail "ai-os-installer.service must not claim a tty directly."
    ! grep -Eq '^After=.*ai-os-installer\.service' "${DAEMON_SERVICE}" \
        || fail "ai-os.service must not wait on ai-os-installer.service."
    grep -Eq '^After=.*NetworkManager\.service' "${INSTALLER_SERVICE}" \
        || fail "ai-os-installer.service must start after NetworkManager.service."
    grep -Eq '^ConditionPathExists=/var/lib/ai-os/installer-complete$' "${POSTINSTALL_SERVICE}" \
        || fail "ai-os-postinstall-check.service must wait for installer completion."
}

check_enabled_units() {
    log "Checking enabled unit symlinks..."
    [[ -L "${REPO_ROOT}/archlive/airootfs/etc/systemd/system/multi-user.target.wants/ai-os-postinstall-check.service" ]] \
        || fail "ai-os-postinstall-check.service is not enabled in multi-user.target.wants."
    [[ -L "${REPO_ROOT}/archlive/airootfs/etc/systemd/system/multi-user.target.wants/NetworkManager.service" ]] \
        || fail "NetworkManager.service is not enabled in multi-user.target.wants."
    [[ -L "${REPO_ROOT}/archlive/airootfs/etc/systemd/system/multi-user.target.wants/getty.target" ]] \
        || fail "getty.target must be enabled in multi-user.target.wants."
    [[ -L "${REPO_ROOT}/archlive/airootfs/etc/systemd/system/getty.target.wants/getty@tty1.service" ]] \
        || fail "getty@tty1.service must be enabled."
    [[ -L "${REPO_ROOT}/archlive/airootfs/etc/systemd/system/getty.target.wants/getty@tty2.service" ]] \
        || fail "getty@tty2.service must be enabled."
    [[ -L "${REPO_ROOT}/archlive/airootfs/etc/systemd/system/getty.target.wants/getty@tty3.service" ]] \
        || fail "getty@tty3.service must be enabled."
    [[ ! -L "${REPO_ROOT}/archlive/airootfs/etc/systemd/system/multi-user.target.wants/systemd-networkd.service" ]] \
        || fail "systemd-networkd.service must not be enabled when NetworkManager owns networking."
    [[ ! -L "${REPO_ROOT}/archlive/airootfs/etc/systemd/system/multi-user.target.wants/iwd.service" ]] \
        || fail "iwd.service must not be enabled when NetworkManager owns WiFi."
}

check_packages() {
    log "Checking package prerequisites..."
    grep -Fxq 'ollama' "${PACKAGES_FILE}" || fail "archlive/packages.x86_64 must include ollama."
    grep -Fxq 'curl' "${PACKAGES_FILE}" || fail "archlive/packages.x86_64 must include curl."
    grep -Fxq 'networkmanager' "${PACKAGES_FILE}" || fail "archlive/packages.x86_64 must include networkmanager."
    grep -Fxq 'iputils' "${PACKAGES_FILE}" || fail "archlive/packages.x86_64 must include iputils."
}

check_shell_syntax() {
    log "Checking shell script syntax..."
    bash -n "${REPO_ROOT}/scripts/sync_runtime.sh"
    bash -n "${REPO_ROOT}/scripts/pre_iso_check.sh"
    bash -n "${REPO_ROOT}/scripts/build_and_test_iso.sh"
    bash -n "${REPO_ROOT}/scripts/run_vm_e2e_test.sh"
    bash -n "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-installer"
    bash -n "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-postinstall-check"
}

check_installers() {
    log "Checking installer assets..."
    require_executable "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-installer"
    require_executable "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-postinstall-check"
    require_executable "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os"
    require_executable "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-daemon"
    require_executable "${REPO_ROOT}/scripts/build_and_test_iso.sh"
    require_executable "${REPO_ROOT}/scripts/run_vm_e2e_test.sh"
}

check_model_config_path() {
    log "Checking system models.json path..."
    grep -Fq '/etc/ai-os/models.json' "${REPO_ROOT}/ai_core/core/config.py" \
        || fail "repo config must reference /etc/ai-os/models.json."
    grep -Fq '/etc/ai-os/models.json' "${RUNTIME_ROOT}/ai_core/core/config.py" \
        || fail "live runtime config must reference /etc/ai-os/models.json."
}

check_network_setup_flow() {
    log "Checking installer network setup flow..."
    grep -Fq 'Setting up internet connection...' "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-installer" \
        || fail "Installer must announce the internet setup stage."
    grep -Fq 'nmtui' "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-installer" \
        || fail "Installer must provide an nmtui WiFi setup path."
    grep -Fq 'ping -c 1 "${NETWORK_CHECK_HOST}"' "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-installer" \
        || fail "Installer must verify internet with ping."
}

check_serial_install_markers() {
    log "Checking installer serial markers..."
    grep -Fq 'emit_stage "INSTALLER_STARTED"' "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-installer" \
        || fail "Installer must emit an INSTALLER_STARTED marker."
    grep -Fq 'emit_stage "MODEL_DOWNLOADS_BACKGROUND"' "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-installer" \
        || fail "Installer must emit a MODEL_DOWNLOADS_BACKGROUND marker."
    grep -Fq 'emit_stage "MODELS_CONFIG_WRITTEN"' "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-installer" \
        || fail "Installer must emit a MODELS_CONFIG_WRITTEN marker."
    grep -Fq 'emit_stage "ORCHESTRATOR_READY"' "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-postinstall-check" \
        || fail "Post-install check must emit an ORCHESTRATOR_READY marker."
    grep -Fq 'emit_stage "READY_WITH_BACKGROUND_DOWNLOADS"' "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-postinstall-check" \
        || fail "Post-install check must emit a READY_WITH_BACKGROUND_DOWNLOADS marker."
    grep -Fq 'emit_stage "RUNTIME_OLLAMA_STORAGE_OK:${source}"' "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-postinstall-check" \
        || fail "Post-install check must emit a RUNTIME_OLLAMA_STORAGE_OK marker."
    grep -Fq 'emit_stage "CLI_HEALTH_OK"' "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-postinstall-check" \
        || fail "Post-install check must emit a CLI_HEALTH_OK marker."
    grep -Fq 'emit_stage "CLI_RUNTIME_OK:${configured_runtime}"' "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-postinstall-check" \
        || fail "Post-install check must emit a CLI_RUNTIME_OK marker."
    grep -Fq 'emit_stage "CLI_SIMPLE_TASK_OK"' "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-postinstall-check" \
        || fail "Post-install check must emit a CLI_SIMPLE_TASK_OK marker."
    grep -Fq 'emit_stage "CLI_PLANNING_TASK_OK"' "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-postinstall-check" \
        || fail "Post-install check must emit a CLI_PLANNING_TASK_OK marker."
    grep -Fq 'emit_stage "CLI_CODING_BLOCK_OK"' "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-postinstall-check" \
        || fail "Post-install check must emit a CLI_CODING_BLOCK_OK marker."
    grep -Fq 'emit_stage "CLI_CODING_TASK_OK"' "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-postinstall-check" \
        || fail "Post-install check must emit a CLI_CODING_TASK_OK marker."
    grep -Fq 'emit_stage "CLI_MODELS_OK:${ORCHESTRATOR_MODEL}"' "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-postinstall-check" \
        || fail "Post-install check must emit a CLI_MODELS_OK marker."
    grep -Fq 'emit_stage "DAEMON_RUNTIME_OK:${configured_runtime}"' "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-postinstall-check" \
        || fail "Post-install check must emit a DAEMON_RUNTIME_OK marker."
    grep -Fq 'emit_stage "DAEMON_MODELS_OK:${ORCHESTRATOR_MODEL}"' "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-postinstall-check" \
        || fail "Post-install check must emit a DAEMON_MODELS_OK marker."
    grep -Fq 'emit_stage "HEALTHCHECK_OK"' "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-postinstall-check" \
        || fail "Post-install health check must emit a HEALTHCHECK_OK marker."
}

check_installer_tty_handling() {
    log "Checking installer tty handling..."
    grep -Fq 'if [ -t 1 ]; then' "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-installer" \
        || fail "Installer must detect interactivity from stdout."
    grep -Fq 'Warning: non-interactive shell detected, using defaults.' "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-installer" \
        || fail "Installer must warn instead of exiting in non-interactive mode."
    ! grep -Fq 'Interactive console is not available.' "${REPO_ROOT}/archlive/airootfs/usr/local/bin/ai-os-installer" \
        || fail "Installer must not hard-fail on tty detection."
}

check_console_boot_flow() {
    log "Checking console-safe boot flow..."
    [[ -L "${DEFAULT_TARGET}" ]] || fail "default.target must be a symlink to multi-user.target."
    [[ "$(readlink "${DEFAULT_TARGET}")" == "/usr/lib/systemd/system/multi-user.target" ]] \
        || fail "default.target must point to multi-user.target."
    grep -Fq -- '--autologin root' "${TTY1_AUTOLOGIN}" \
        || fail "tty1 autologin override must be present."
    grep -Fq '/usr/local/bin/ai-os-installer' "${REPO_ROOT}/archlive/airootfs/root/.zlogin" \
        || fail "tty1 login must launch ai-os-installer when setup is incomplete."
}

check_boot_params() {
    log "Checking boot parameters..."
    ! rg -n "\\bquiet\\b" "${REPO_ROOT}/archlive/grub" "${REPO_ROOT}/archlive/syslinux" "${REPO_ROOT}/archlive/efiboot" >/dev/null \
        || fail "Bootloader config must not hide logs with the quiet kernel parameter."
    rg -n "console=tty0 console=ttyS0,115200" "${REPO_ROOT}/archlive/grub" "${REPO_ROOT}/archlive/syslinux" "${REPO_ROOT}/archlive/efiboot" >/dev/null \
        || fail "Bootloader config must expose a serial console for headless VM verification."
}

main() {
    require_file "${INSTALLER_SERVICE}"
    require_file "${POSTINSTALL_SERVICE}"
    require_file "${DAEMON_SERVICE}"
    require_file "${PACKAGES_FILE}"
    require_file "${RUNTIME_ROOT}/ai_core"

    check_runtime_sync
    check_unit_file
    check_enabled_units
    check_packages
    check_shell_syntax
    check_installers
    check_model_config_path
    check_network_setup_flow
    check_serial_install_markers
    check_installer_tty_handling
    check_console_boot_flow
    check_boot_params

    log "All pre-ISO checks passed."
}

main "$@"
