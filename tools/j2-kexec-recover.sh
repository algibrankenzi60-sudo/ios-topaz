#!/usr/bin/env bash
# Cancel a pending RAM-only kexec or request Android reboot if Linux still answers.
set -euo pipefail
ADB=${ADB:-adb}
SERIAL=${ANDROID_SERIAL:-}
REBOOT_ANDROID=0
for arg in "$@"; do
  case "$arg" in
    --reboot-android) REBOOT_ANDROID=1 ;;
    *) echo "usage: $0 [--reboot-android]" >&2; exit 2 ;;
  esac
done
adb_cmd() { if [[ -n "$SERIAL" ]]; then "$ADB" -s "$SERIAL" "$@"; else "$ADB" "$@"; fi; }
remote() { adb_cmd shell -T su -c "$1"; }
if [[ "$(adb_cmd get-state 2>/dev/null || true)" != device ]]; then
  cat >&2 <<'MSG'
ADB is not responding, so the RAM-only controller cannot send a command.
Force-restart the handset with its hardware buttons, then boot Android normally.
This experiment changes no boot/recovery partition; do not use Odin/Heimdall to recover it.
MSG
  exit 5
fi
if remote 'test -x /dev/j2-kexec-ctl' >/dev/null 2>&1; then
  remote '/dev/j2-kexec-ctl unload' || true
else
  echo 'No controller in /dev; checking whether a kexec image is pending.'
  remote 'cat /sys/kernel/kexec_loaded'
fi
if (( REBOOT_ANDROID )); then
  adb_cmd reboot
  echo 'Requested an ordinary Android reboot; no partition was written.'
else
  echo 'Pending image cancelled if present. Use --reboot-android for a normal Android reboot.'
fi
