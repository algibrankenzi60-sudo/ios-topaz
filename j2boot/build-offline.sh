#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NDK_BIN="${ANDROID_NDK_BIN:-/mnt/c/Users/awan/AppData/Local/Android/Sdk/ndk/30.0.16248370/toolchains/llvm/prebuilt/windows-x86_64/bin}"
CC="$NDK_BIN/clang.exe"
BUILD="${1:-$ROOT/j2boot/out}"
SHIM="/mnt/d/J2-iOS-audit-20261027/bootshim-build/bootshim-padded.bin"
KERNEL="${J2_XNU_KERNEL:-/tmp/xnu-kernel-782ea05/kernel.development.j2prime}"
if [[ ! -f "$KERNEL" ]]; then
  echo "XNU kernel not found: $KERNEL" >&2
  echo "Set J2_XNU_KERNEL to the audited kernel.development.j2prime artifact." >&2
  exit 1
fi
STACK_TOP=0x41000000
mkdir -p "$BUILD"
to_win() { wslpath -w "$1"; }
ROOT_W="$(to_win "$ROOT")"; BUILD_W="$(to_win "$BUILD")"
"$CC" --target=aarch64-none-elf -fuse-ld=lld -ffreestanding -fno-builtin -fno-stack-protector \
  -mgeneral-regs-only -mstrict-align -O2 -Wall -Wextra -Werror -nostdlib \
  -DJ2_STACK_TOP="$STACK_TOP" \
  -Wl,-T,"$ROOT_W\\j2boot\\loader-recovery.ld" \
  -Wl,--build-id=none "$ROOT_W\\j2boot\\start.S" "$ROOT_W\\j2boot\\loader.c" \
  "$ROOT_W\\j2boot\\ramoops_marker.c" "$ROOT_W\\j2boot\\framebuffer_mark.c" \
  "$ROOT_W\\j2boot\\lz4_block.c" -o "$BUILD_W\\loader.elf"
python3 - "$BUILD/loader.elf" "$BUILD/loader.bin" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read()
if b[:6] != b'\x7fELF\x02\x01': raise SystemExit('expected little-endian ELF64')
phoff=struct.unpack_from('<Q',b,32)[0]; entsz,n=struct.unpack_from('<HH',b,54)
segs=[]
for i in range(n):
    typ,flags,off,va,pa,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',b,phoff+i*entsz)
    if typ==1 and filesz and pa>=0x40008000: segs.append((pa,off,filesz))
if not segs: raise SystemExit('ELF has no loadable bytes')
lo=min(x[0] for x in segs); hi=max(pa+size for pa,_,size in segs); out=bytearray(hi-lo)
for pa,off,size in segs: out[pa-lo:pa-lo+size]=b[off:off+size]
if lo != 0x40008000: raise SystemExit(f'unexpected loader link address: {lo:#x}')
open(sys.argv[2],'wb').write(out)
print('loader_elf_load_bytes:',len(out),'link_address:',hex(lo))
PY
python3 - "$BUILD/loader.bin" "$BUILD/loader-padded.bin" <<'PY'
import sys
b=open(sys.argv[1],'rb').read()
if len(b)>8192: raise SystemExit(f'loader exceeds fixed 8 KiB window: {len(b)}')
b += bytes(8192-len(b)); open(sys.argv[2],'wb').write(b)
print('loader_bytes:',len(b),'payload symbol: 0x4000a000')
PY
IOMEM_ARGS=()
if [[ -n "${J2_IOMEM:-}" ]]; then IOMEM_ARGS=(--iomem "$J2_IOMEM"); fi
python3 "$ROOT/tools/mkadt_j2.py" "$BUILD/j2prime.adt" --audit-json "$BUILD/ram-audit.json" "${IOMEM_ARGS[@]}"
python3 "$ROOT/tools/test_mkadt_j2.py"
python3 "$ROOT/tools/mkpayload_j2.py" "$KERNEL" "$BUILD/j2prime.adt" "$BUILD/j2prime.payload" \
  --source-window 0x80000000 0x81000000 --report "$BUILD/payload-report.json"
python3 - "$SHIM" "$BUILD/loader-padded.bin" "$BUILD/j2prime-recovery-kernel.bin" <<'PY'
import sys
shim,loader=(open(x,'rb').read() for x in sys.argv[1:3])
out=sys.argv[3]
if len(shim)!=16384: raise SystemExit('unexpected MT6737 shim size')
if len(loader)!=8192: raise SystemExit(f'loader must occupy fixed 8 KiB window, got {len(loader)}')
image=shim+loader
open(out,'wb').write(image)
check=open(out,'rb').read()
if check[:len(shim)]!=shim or check[len(shim):len(shim)+len(loader)]!=loader:
    raise SystemExit('combined image component verification failed')
import hashlib
print('recovery_kernel_bytes:',len(image),'sha256:',hashlib.sha256(check).hexdigest(),
      'kernel_load_address: 0x40004000','loader_entry: 0x40008000',
      'ramdisk_container_address: 0x44000000','staging_address: 0x80000000',
      'stack_top: 0x41000000','status: OFFLINE ONLY; NOT FOR FLASH')
PY
