#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AUDIT=/mnt/d/J2-iOS-audit-20261027
BUILD="${1:-$AUDIT/j2prime-recovery-bootshim-offline-20261028}"
BACKUP="$AUDIT/live-recovery.img"
mkdir -p "$BUILD"

bash "$ROOT/j2boot/build-offline.sh" "$BUILD"
python3 "$ROOT/tools/lz4_block.py" "$BUILD/j2prime.payload" "$BUILD/j2prime.payload.lz4"
cc -std=c11 -O2 -Wall -Wextra -Werror -I"$ROOT/j2boot" \
  "$ROOT/j2boot/lz4_block.c" "$ROOT/j2boot/test_lz4_block.c" -o "$BUILD/test-lz4-block"
"$BUILD/test-lz4-block" "$BUILD/j2prime.payload.lz4" "$BUILD/j2prime.payload"
python3 "$ROOT/tools/pack_recovery_kernel_only.py" \
  "$BACKUP" "$BUILD/j2prime-recovery-kernel.bin" "$BUILD/j2prime.payload" \
  "$BUILD/j2prime.payload.lz4" \
  "$BUILD/J2PRIME-RECOVERY-DO-NOT-FLASH.img"
python3 "$ROOT/tools/verify_recovery_bootshim.py" \
  "$BUILD/J2PRIME-RECOVERY-DO-NOT-FLASH.img" "$BUILD/loader-padded.bin" \
  "$BACKUP" "$BUILD/j2prime.payload"
cc -std=c11 -Wall -Wextra -Werror -I"$ROOT/j2boot" \
  "$ROOT/j2boot/test_framebuffer_mark.c" -o "$BUILD/test-framebuffer-mark"
"$BUILD/test-framebuffer-mark"
cc -std=c11 -Wall -Wextra -Werror -DJ2_RAMOOPS_TEST -I"$ROOT/j2boot" \
  "$ROOT/j2boot/ramoops_marker.c" "$ROOT/j2boot/test_ramoops_marker.c" \
  -o "$BUILD/test-ramoops-marker"
"$BUILD/test-ramoops-marker"
