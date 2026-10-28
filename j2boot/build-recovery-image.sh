#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AUDIT=/mnt/d/J2-iOS-audit-20261027
BUILD="${1:-$AUDIT/j2prime-recovery-bootshim-offline-20261028}"
BACKUP="$AUDIT/live-recovery.img"
mkdir -p "$BUILD"

bash "$ROOT/j2boot/build-offline.sh" "$BUILD"
python3 "$ROOT/tools/pack_recovery_kernel_only.py" \
  "$BACKUP" "$BUILD/j2prime-recovery-kernel.bin" \
  "$BUILD/J2PRIME-RECOVERY-DO-NOT-FLASH.img"
python3 "$ROOT/tools/verify_recovery_bootshim.py" \
  "$BUILD/J2PRIME-RECOVERY-DO-NOT-FLASH.img" "$BUILD/loader-padded.bin"
