#!/usr/bin/env python3
"""Offline structural and content validation of the J2 recovery boot image."""
import hashlib
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lz4_block import decompress

PAGE = 2048
PARTITION = 16 * 1024 * 1024
RAMDISK_MAGIC = b"J2LZ4\0\0\0"


def align(n, a=PAGE):
    return (n + a - 1) // a * a


if len(sys.argv) != 5:
    raise SystemExit("usage: verify_recovery_bootshim.py IMAGE LOADER BACKUP PAYLOAD")
image_path, loader_path, backup_path, payload_path = map(Path, sys.argv[1:])
image, loader, backup, expected_payload = (p.read_bytes() for p in (image_path, loader_path, backup_path, payload_path))
if len(image) != PARTITION or image[:8] != b"ANDROID!":
    raise SystemExit("not a 16 MiB Android recovery boot image")
kernel_size, kernel_addr, ramdisk_size, ramdisk_addr, second_size, _, _, page_size, dt_size = struct.unpack_from("<9I", image, 8)
if (kernel_addr, ramdisk_addr, page_size) != (0x40004000, 0x44000000, PAGE) or second_size:
    raise SystemExit("unexpected Samsung recovery load contract")
kernel_off = PAGE
ramdisk_off = kernel_off + align(kernel_size)
dtb_off = ramdisk_off + align(ramdisk_size)
kernel = image[kernel_off : kernel_off + kernel_size]
ramdisk = image[ramdisk_off : ramdisk_off + ramdisk_size]
shim = Path("/mnt/d/J2-iOS-audit-20261027/bootshim-build/bootshim-padded.bin").read_bytes()
if len(shim) != 0x4000 or kernel_size != 0x6000 or kernel[:len(shim)] != shim:
    raise SystemExit("bootshim bytes/length mismatch")
if len(loader) != 0x2000 or kernel[0x4000:0x6000] != loader:
    raise SystemExit("AArch64 loader is not at shim entry 0x40008000")
if len(ramdisk) < 32 or ramdisk[:8] != RAMDISK_MAGIC:
    raise SystemExit("ramdisk lacks J2LZ4 container")
version, reserved = struct.unpack_from("<II", ramdisk, 8)
expanded, compressed = struct.unpack_from("<QQ", ramdisk, 16)
if version != 1 or reserved or compressed != len(ramdisk) - 32 or expanded != len(expected_payload):
    raise SystemExit("ramdisk container header/bounds mismatch")
if decompress(ramdisk[32:], expanded) != expected_payload:
    raise SystemExit("decompressed ramdisk does not equal audited payload file")
if expected_payload[:8] != b"J2PRIME\0" or struct.unpack_from("<Q", expected_payload, 0x48)[0] != expanded:
    raise SystemExit("embedded package header/size mismatch")
if expanded > 0x01000000:
    raise SystemExit("expanded package exceeds loader staging capacity")
payload_phys, payload_size = struct.unpack_from("<QQ", expected_payload, 0x38)
nsegs = struct.unpack_from("<I", expected_payload, 0x0c)[0]
virt_base = struct.unpack_from("<Q", expected_payload, 0x10)[0]
adt_off, adt_size = struct.unpack_from("<QQ", expected_payload, 0x20)
kernel_end_va = struct.unpack_from("<Q", expected_payload, 0x30)[0]
if not 0 < nsegs <= 32 or 0x2a8 + nsegs * 32 > expanded:
    raise SystemExit("invalid package segment table bounds")
stage_lo, stage_hi = 0x80000000, 0x80000000 + expanded
for i in range(nsegs):
    va, vsize = struct.unpack_from("<QQ", expected_payload, 0x2a8 + i * 32)
    dst_lo, dst_hi = payload_phys + va - virt_base, payload_phys + va - virt_base + vsize
    if stage_lo < dst_hi and dst_lo < stage_hi:
        raise SystemExit(f"decompression stage overlaps XNU segment {i}")
kernel_end_pa = payload_phys + kernel_end_va - virt_base
adt_start = align(kernel_end_pa, 4096)
adt_end = adt_start + adt_size
boot_args_start = align(adt_end, 4096)
tables_start = boot_args_start + 4096
tables_end = tables_start + 5 * 4096
if adt_off > expanded or adt_size > expanded - adt_off or tables_end > payload_phys + payload_size:
    raise SystemExit("kernel/ADT/boot_args/page-table placement exceeds candidate RAM")
if stage_lo < tables_end and kernel_end_pa < stage_hi:
    raise SystemExit("decompression stage overlaps kernel-end ADT/boot_args/table allocation")

if len(backup) != PARTITION or backup[:8] != b"ANDROID!":
    raise SystemExit("backup is not the verified original recovery image")
orig_fields = struct.unpack_from("<9I", backup, 8)
orig_dtb_off = PAGE + align(orig_fields[0]) + align(orig_fields[2]) + align(orig_fields[4])
original_dtb = backup[orig_dtb_off : orig_dtb_off + orig_fields[8]]
dtb = image[dtb_off : dtb_off + dt_size]
if dt_size != orig_fields[8] or dtb != original_dtb or hashlib.sha256(dtb).digest() != hashlib.sha256(original_dtb).digest():
    raise SystemExit("candidate does not preserve exact original appended DTB")
if dtb[:4] != b"DTBH":
    raise SystemExit("unexpected appended DTB format")
used_end = dtb_off + dt_size
if used_end > PARTITION:
    raise SystemExit("boot image components exceed recovery partition")
print(f"image_sha256={hashlib.sha256(image).hexdigest()}")
print(f"kernel_bytes={kernel_size} loader=0x40008000 ramdisk=0x44000000 compressed={compressed} expanded={expanded}")
print(f"staging=[0x{stage_lo:08x},0x{stage_hi:08x}) XNU_RAM=[0x{payload_phys:08x},0x{payload_phys+payload_size:08x})")
print(f"dtb_offset={dtb_off:#x} dtb_bytes={dt_size} dtb_sha256={hashlib.sha256(dtb).hexdigest()}")
print(f"partition_used_end={used_end:#x} partition_limit={PARTITION:#x}")
print("status=OFFLINE STRUCTURAL AND CONTENT CHECKS PASS; runtime/XNU boot not proven")
