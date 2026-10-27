#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NDK_BIN="${ANDROID_NDK_BIN:-/mnt/c/Users/awan/AppData/Local/Android/Sdk/ndk/30.0.16248370/toolchains/llvm/prebuilt/windows-x86_64/bin}"
CC="$NDK_BIN/clang.exe"
BUILD="${1:-$ROOT/j2boot/out}"
SHIM="/mnt/d/J2-iOS-audit-20261027/bootshim-build/bootshim-padded.bin"
KERNEL="/tmp/xnu-kernel-782ea05/kernel.development.j2prime"
mkdir -p "$BUILD"
to_win() { wslpath -w "$1"; }
ROOT_W="$(to_win "$ROOT")"; BUILD_W="$(to_win "$BUILD")"
"$CC" --target=aarch64-none-elf -fuse-ld=lld -ffreestanding -fno-builtin -fno-stack-protector \
  -mgeneral-regs-only -mstrict-align -O2 -Wall -Wextra -nostdlib -Wl,-T,"$ROOT_W\\j2boot\\loader.ld" \
  -Wl,--build-id=none "$ROOT_W\\j2boot\\start.S" "$ROOT_W\\j2boot\\loader.c" -o "$BUILD_W\\loader.elf"
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
b=open(sys.argv[1],'rb').read(); b += bytes((-len(b)) & 4095); open(sys.argv[2],'wb').write(b)
print('loader_bytes:',len(b))
PY
python3 "$ROOT/tools/mkadt_j2.py" "$BUILD/j2prime.adt" --audit-json "$BUILD/ram-audit.json"
python3 "$ROOT/tools/mkpayload_j2.py" "$KERNEL" "$BUILD/j2prime.adt" "$BUILD/j2prime.payload" --report "$BUILD/payload-report.json"
python3 - "$SHIM" "$BUILD/loader-padded.bin" "$BUILD/j2prime.payload" "$BUILD/j2prime-diagnostic-kernel.bin" <<'PY'
import sys
shim,loader,payload=(open(x,'rb').read() for x in sys.argv[1:4])
out=sys.argv[4]
if len(shim)!=16384: raise SystemExit('unexpected MT6737 shim size')
if (len(shim)+len(loader))%4096: raise SystemExit('loader placement alignment error')
image=shim+loader+payload
limit=16*1024*1024
if len(image)>limit: raise SystemExit(f'combined image exceeds recovery partition: {len(image)} > {limit}')
open(out,'wb').write(image)
check=open(out,'rb').read()
if check[:len(shim)]!=shim or check[len(shim):len(shim)+len(loader)]!=loader:
    raise SystemExit('combined image component verification failed')
at=len(shim)+len(loader)
if check[at:at+8]!=b'J2PRIME\0': raise SystemExit('payload magic missing at loader-declared boundary')
total=int.from_bytes(check[at+0x48:at+0x50],'little')
if total!=len(payload) or check[at:at+total]!=payload: raise SystemExit('embedded payload size/content mismatch')
import hashlib
print('diagnostic_kernel_bytes:',len(image),'sha256:',hashlib.sha256(check).hexdigest(),
      'partition_limit:',limit,'status: NOT FOR FLASH')
PY
