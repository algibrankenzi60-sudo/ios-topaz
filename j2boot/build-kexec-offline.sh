#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AUDIT=/mnt/d/J2-iOS-audit-20261027
NDK_BIN="${ANDROID_NDK_BIN:-/mnt/c/Users/awan/AppData/Local/Android/Sdk/ndk/30.0.16248370/toolchains/llvm/prebuilt/windows-x86_64/bin}"
CC="$NDK_BIN/clang.exe"
IOMEM="${J2_IOMEM:-$AUDIT/runtime-iomem-20261028.txt}"
MEMBLOCK="${J2_MEMBLOCK_RESERVED:-$AUDIT/runtime-memblock-reserved-20261028.txt}"
BUILD="${1:-$AUDIT/j2prime-kexec-offline-20261028}"
LIMIT=0x85000000
TRAMPOLINE=0x84000000
LOADER=0x84004000
PACKAGE=0x84006000
KERNEL="${J2_KERNEL:-/tmp/xnu-kernel-782ea05/kernel.development.j2prime}"
DIAGNOSTIC_HALT="${J2_DIAGNOSTIC_HALT:-0}"
if [[ "$DIAGNOSTIC_HALT" != 0 && "$DIAGNOSTIC_HALT" != 1 ]]; then
  echo 'J2_DIAGNOSTIC_HALT must be 0 or 1' >&2
  exit 2
fi
mkdir -p "$BUILD"
if [[ ! -f "$KERNEL" ]]; then
  echo "missing ARM64 J2PRIME kernel: $KERNEL (set J2_KERNEL to the verified artifact)" >&2
  exit 2
fi
to_win() { wslpath -w "$1"; }
ROOT_W="$(to_win "$ROOT")"
BUILD_W="$(to_win "$BUILD")"
python3 - "$IOMEM" "$MEMBLOCK" <<'PY'
import re,sys
lo,hi=0x84000000,0x85000000
ram=[]
for line in open(sys.argv[1],encoding='ascii',errors='replace'):
    m=re.match(r'^\s*([0-9a-fA-F]+)-([0-9a-fA-F]+)\s*:\s*System RAM\s*$',line)
    if m: ram.append((int(m[1],16),int(m[2],16)+1))
if not any(lo>=a and hi<=b for a,b in ram): raise SystemExit('kexec source window is not contained in live System RAM')
reserved=[]
for line in open(sys.argv[2],encoding='ascii',errors='replace'):
    m=re.search(r'0x([0-9a-fA-F]+)\.\.0x([0-9a-fA-F]+)',line)
    if m: reserved.append((int(m[1],16),int(m[2],16)+1,line.strip()))
over=[x for x in reserved if lo<x[1] and x[0]<hi]
if over: raise SystemExit('kexec source window overlaps live memblock reservation: '+repr(over))
print(f'live runtime audit: source [{lo:#x},{hi:#x}) inside System RAM; no memblock reservation overlap')
PY

"$CC" --target=arm-none-eabi -fuse-ld=lld -mcpu=cortex-a53 -ffreestanding -fno-builtin -fno-unwind-tables -fno-asynchronous-unwind-tables -nostdlib \
  -Wl,-Ttext="$TRAMPOLINE" -Wl,-e,_start -Wl,--oformat=binary \
  "$ROOT_W\\j2boot\\kexec_trampoline.S" "$ROOT_W\\j2boot\\ramoops_marker.c" -O2 -fno-stack-protector -o "$BUILD_W\\trampoline.bin"
python3 - "$BUILD/trampoline.bin" "$BUILD/trampoline-padded.bin" <<'PY'
import sys
b=open(sys.argv[1],'rb').read()
if len(b)>0x4000 or b[4:12]!=b'J2KEX001': raise SystemExit('bad/oversized ARM32 kexec trampoline')
b+=bytes(0x4000-len(b)); open(sys.argv[2],'wb').write(b)
print('AArch32 kexec trampoline:',len(b),'entry=0x84000000')
PY

"$CC" --target=aarch64-none-elf -fuse-ld=lld -ffreestanding -fno-builtin -fno-stack-protector \
  -mgeneral-regs-only -mstrict-align -O2 -Wall -Wextra -Werror -nostdlib -DJ2_DIAGNOSTIC_HALT="$DIAGNOSTIC_HALT" -DJ2_PAYLOAD_BASE=0x84006000ULL -DJ2_PAYLOAD_LIMIT=0x85000000ULL \
  -Wl,-T,"$ROOT_W\\j2boot\\loader-kexec.ld" -Wl,--build-id=none \
  "$ROOT_W\\j2boot\\start.S" "$ROOT_W\\j2boot\\loader.c" "$ROOT_W\\j2boot\\ramoops_marker.c" -o "$BUILD_W\\loader.elf"
python3 - "$BUILD/loader.elf" "$BUILD/loader.bin" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read()
if b[:6]!=b'\x7fELF\x02\x01': raise SystemExit('expected little-endian ELF64')
phoff=struct.unpack_from('<Q',b,32)[0]; entsz,n=struct.unpack_from('<HH',b,54); base=0x84004000
segs=[]
for i in range(n):
    typ,flags,off,va,pa,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',b,phoff+i*entsz)
    if typ==1 and filesz and pa>=base: segs.append((pa,off,filesz))
if not segs: raise SystemExit('ELF has no loadable bytes')
lo=min(x[0] for x in segs); hi=max(pa+size for pa,_,size in segs); out=bytearray(hi-lo)
for pa,off,size in segs: out[pa-lo:pa-lo+size]=b[off:off+size]
if lo!=base: raise SystemExit(f'unexpected loader address {lo:#x}')
open(sys.argv[2],'wb').write(out); print('AArch64 loader:',len(out),'bytes at',hex(lo))
PY
python3 - "$BUILD/loader.bin" "$BUILD/loader-padded.bin" <<'PY'
import sys
b=open(sys.argv[1],'rb').read()
if len(b)>0x2000: raise SystemExit(f'loader exceeds reserved 8 KiB region: {len(b)}')
b+=bytes(0x2000-len(b)); open(sys.argv[2],'wb').write(b)
print('loader padded:',len(b),'bytes; package address=0x84006000')
PY

ADT_ARGS=()
if [[ -n "$IOMEM" ]]; then ADT_ARGS=(--iomem "$IOMEM"); fi
python3 "$ROOT/tools/mkadt_j2.py" "$BUILD/j2prime.adt" --audit-json "$BUILD/ram-audit.json" "${ADT_ARGS[@]}"
python3 "$ROOT/tools/mkpayload_j2.py" "$KERNEL" "$BUILD/j2prime.adt" "$BUILD/j2prime.payload" \
  --source-window "$PACKAGE" "$LIMIT" --report "$BUILD/payload-report.json"
python3 - "$BUILD/trampoline-padded.bin" "$BUILD/loader-padded.bin" "$BUILD/j2prime.payload" "$BUILD/J2PRIME-KEXEC-DO-NOT-FLASH.bin" "$BUILD/manifest.json" "$DIAGNOSTIC_HALT" "$BUILD/payload-report.json" <<'PY'
import hashlib,json,sys
tramp,loader,payload=(open(x,'rb').read() for x in sys.argv[1:4]); outpath,manifest=sys.argv[4:6]
if len(tramp)!=0x4000 or len(loader)!=0x2000: raise SystemExit('unexpected fixed component size')
blob=tramp+loader+payload
if blob[4:12]!=b'J2KEX001' or blob[0x6000:0x6008]!=b'J2PRIME\0': raise SystemExit('image component boundaries invalid')
if len(blob)>0x1000000: raise SystemExit('image exceeds audited 16 MiB live-RAM source window')
blob+=bytes((-len(blob))&4095); open(outpath,'wb').write(blob)
m={'format':'J2KEX001 + Samsung ARM32 kexec trampoline + MT6737 SMC + AArch64 XNU MMU loader + J2PRIME package',
   'load_address':'0x84000000','entry_address':'0x84000000','aarch64_loader':'0x84004000','loader_reserved_bytes':0x2000,'package':'0x84006000',
   'source_window':['0x84000000','0x85000000'],'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest(),
   'trampoline_sha256':hashlib.sha256(tramp).hexdigest(),'loader_sha256':hashlib.sha256(loader).hexdigest(),
   'package_sha256':hashlib.sha256(payload).hexdigest(),
   'status':'RAM-ONLY EXPERIMENT; NEVER FLASH; DO NOT EXECUTE WITHOUT APPROVAL'}
m['diagnostic_halt_before_xnu']=bool(int(sys.argv[6]))
report=json.load(open(sys.argv[7]))
m['kernel_sha256']=report['kernel_sha256']
m['entry_va']=report['entry_va']
m['candidate_ram_pa']=report['candidate_ram_pa']
m['candidate_ram_size']=report['candidate_ram_size']
if m['diagnostic_halt_before_xnu']:
    m['mode']='diagnostic halt before XNU branch'
else:
    m['mode']='experimental branch to mapped XNU entry VA'
open(manifest,'w').write(json.dumps(m,indent=2)+'\n'); print(json.dumps(m,indent=2))
PY
python3 "$ROOT/tools/verify_j2_experiment.py" \
  "$BUILD/J2PRIME-KEXEC-DO-NOT-FLASH.bin" "$BUILD/manifest.json" \
  "$BUILD/trampoline-padded.bin" "$BUILD/loader-padded.bin" \
  "$BUILD/j2prime.payload" "$BUILD/payload-report.json"
"$CC" --target=armv7a-linux-androideabi21 -O2 -Wall -Wextra \
  "$ROOT_W\\j2boot\\kexec_ctl.c" -o "$BUILD_W\\j2-kexec-ctl"
file "$BUILD/j2-kexec-ctl" "$BUILD/J2PRIME-KEXEC-DO-NOT-FLASH.bin"
cc -std=c11 -Wall -Wextra -Werror -I"$ROOT/j2boot" "$ROOT/j2boot/test_boot_mmu.c" -o "$BUILD/test-boot-mmu"
"$BUILD/test-boot-mmu"
cc -std=c11 -Wall -Wextra -Werror -DJ2_RAMOOPS_TEST -I"$ROOT/j2boot" \
  "$ROOT/j2boot/ramoops_marker.c" "$ROOT/j2boot/test_ramoops_marker.c" -o "$BUILD/test-ramoops-marker"
"$BUILD/test-ramoops-marker"
