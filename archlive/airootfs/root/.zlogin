# fix for screen readers
if grep -Fqa 'accessibility=' /proc/cmdline &> /dev/null; then
    setopt SINGLE_LINE_ZLE
fi

~/.automated_script.sh

if [[ $(tty) == "/dev/tty1" && ! -f /var/lib/ai-os/installer-complete ]]; then
    printf '\nLaunching AI OS first-boot installer...\n\n'
    /usr/local/bin/ai-os-installer || printf 'AI OS installer exited before completion. Run ai-os-installer manually.\n'
fi
