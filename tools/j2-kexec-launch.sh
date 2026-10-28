#!/usr/bin/env bash
# Stage and control a RAM-only J2 kexec image. Never writes Android/recovery partitions.
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: j2-kexec-launch.sh IMAGE CONTROL MANIFEST {load|execute|unload|status}

load     Copies verified bytes only to /dev (tmpfs), checks SHA-256, then kexec_loads.
execute  Runs an already-loaded image; requires the explicit confirmation token below.
unload   Unloads a pending image without executing it.
status   Shows whether Linux currently has a kexec image loaded.

To execute later, use:
  j2-kexec-launch.sh IMAGE CONTROL MANIFEST execute I-UNDERSTAND-RAM-ONLY-KEXEC
USAGE
  exit 2
}
[[ $# -ge 4 ]] || usage
IMAGE=$1 CONTROL=$2 MANIFEST=$3 ACTION=$4
ADB=${ADB:-adb}
SERIAL=${ANDROID_SERIAL:-}
REMOTE_IMAGE=/dev/j2prime-kexec.bin
REMOTE_CTL=/dev/j2-kexec-ctl

adb_cmd() {
  if [[ -n "$SERIAL" ]]; then "$ADB" -s "$SERIAL" "$@"; else "$ADB" "$@"; fi
}
remote() { adb_cmd shell -T su -c "$1"; }

case "$ACTION" in load|execute|unload|status) ;; *) usage ;; esac
if [[ "$ACTION" == execute && "${5:-}" != I-UNDERSTAND-RAM-ONLY-KEXEC ]]; then
  echo 'refusing: execute requires the explicit confirmation token' >&2
  exit 3
fi

if [[ "$ACTION" == load ]]; then
  [[ -f "$IMAGE" && -f "$CONTROL" && -f "$MANIFEST" ]] || { echo 'image/control/manifest file missing' >&2; exit 2; }
  EXPECTED=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sha256"])' "$MANIFEST")
  ACTUAL=$(sha256sum "$IMAGE" | awk '{print $1}')
  [[ "$EXPECTED" == "$ACTUAL" ]] || { echo "host image SHA-256 mismatch: $ACTUAL" >&2; exit 4; }
  SIZE=$(stat -c %s "$IMAGE")
  (( SIZE <= 16777216 )) || { echo "refusing image larger than the audited 16 MiB kexec window: $SIZE" >&2; exit 4; }
  [[ "$(adb_cmd get-state 2>/dev/null || true)" == device ]] || { echo 'ADB device unavailable' >&2; exit 5; }
  remote 'id -u | grep -qx 0' >/dev/null || { echo 'root su access is required' >&2; exit 5; }
  remote 'cat >/dev/j2prime-kexec.bin' < "$IMAGE"
  remote 'cat >/dev/j2-kexec-ctl' < "$CONTROL"
  remote 'chmod 700 /dev/j2-kexec-ctl && chmod 600 /dev/j2prime-kexec.bin'
  DEVICE_SHA=$(remote 'toybox sha256sum /dev/j2prime-kexec.bin' | tr -d '\r' | awk '{print $1}')
  CONTROL_SHA=$(sha256sum "$CONTROL" | awk '{print $1}')
  DEVICE_CTL_SHA=$(remote 'toybox sha256sum /dev/j2-kexec-ctl' | tr -d '\r' | awk '{print $1}')
  [[ "$DEVICE_SHA" == "$EXPECTED" ]] || { echo "device tmpfs image SHA-256 mismatch: $DEVICE_SHA" >&2; exit 6; }
  [[ "$DEVICE_CTL_SHA" == "$CONTROL_SHA" ]] || { echo 'device tmpfs controller SHA-256 mismatch' >&2; exit 6; }
  remote '/dev/j2-kexec-ctl load /dev/j2prime-kexec.bin'
  echo "Loaded $SIZE verified bytes into Linux kexec RAM. It has NOT been executed."
  echo 'Temporary files are under /dev tmpfs; no Android/recovery partition was written.'
  exit 0
fi

[[ "$(adb_cmd get-state 2>/dev/null || true)" == device ]] || { echo 'ADB device unavailable; no command sent' >&2; exit 5; }
if [[ "$ACTION" == unload ]]; then
  remote 'test -x /dev/j2-kexec-ctl' || { echo 'controller absent from /dev; nothing unloaded' >&2; exit 5; }
  remote '/dev/j2-kexec-ctl unload'
elif [[ "$ACTION" == status ]]; then
  remote 'test -x /dev/j2-kexec-ctl' || { echo 'controller absent from /dev' >&2; exit 5; }
  remote '/dev/j2-kexec-ctl status'
else
  remote 'test -x /dev/j2-kexec-ctl' || { echo 'controller absent from /dev' >&2; exit 5; }
  remote '/dev/j2-kexec-ctl execute'
fi
