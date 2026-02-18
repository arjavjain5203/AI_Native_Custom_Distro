#!/usr/bin/env bash
# shellcheck disable=SC2034

iso_name="ai-native-dev-os"
iso_label="AI_NATIVE_DEV_OS_$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y%m)"
iso_publisher="AI Native Dev OS <https://github.com/arjavjain5203/AI_Native_Custom_Distro>"
iso_application="AI Native Dev OS Live/Rescue DVD"
iso_version="$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y.%m.%d)"
install_dir="arch"
buildmodes=('iso')
bootmodes=('bios.syslinux'
           'uefi.systemd-boot')
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'xz' '-Xbcj' 'x86' '-b' '1M' '-Xdict-size' '1M')
bootstrap_tarball_compression=('zstd' '-c' '-T0' '--auto-threads=logical' '--long' '-19')
file_permissions=(
  ["/etc/shadow"]="0:0:400"
  ["/root"]="0:0:750"
  ["/root/.automated_script.sh"]="0:0:755"
  ["/root/.gnupg"]="0:0:700"
  ["/usr/local/bin/choose-mirror"]="0:0:755"
  ["/usr/local/bin/Installation_guide"]="0:0:755"
  ["/usr/local/bin/ai-daemon"]="0:0:755"
  ["/usr/local/bin/ai-os-installer"]="0:0:755"
  ["/usr/local/bin/ai-os-prepare-ollama-storage"]="0:0:755"
  ["/usr/local/bin/ai-os-postinstall-check"]="0:0:755"
  ["/usr/local/bin/ai-os"]="0:0:755"
  ["/usr/local/bin/livecd-sound"]="0:0:755"
)
