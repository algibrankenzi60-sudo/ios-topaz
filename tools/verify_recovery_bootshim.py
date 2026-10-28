#!/usr/bin/env python3
"""Offline checks for the Samsung recovery-context J2 XNU boot image."""
import hashlib
import struct
import sys
from pathlib import Path

image_path = Path(sys.argv[1])
image = image_path.read_bytes()
page = 2048
if len(image) != 16 * 1024 * 1024 or image[:8] != b"ANDROID!":
    raise SystemExit("not a 16 MiB Android boot image")
kernel_size, kernel_addr, ramdisk_size, _, second_size, _, _, page_size, dt_size = struct.unpack_from(
    "<9I", image, 8
)
if (kernel_addr, page_size) != (0x40004000, page):
    raise SystemExit("unexpected Samsung kernel load address/page size")
if ramdisk_size or second_size or dt_size:
    raise SystemExit("kernel-only image still declares a ramdisk/second-stage/DTB")
kernel = image[page : page + kernel_size]
if len(kernel) != kernel_size:
    raise SystemExit("truncated kernel")
shim = Path("/mnt/d/J2-iOS-audit-20261027/bootshim-build/bootshim-padded.bin").read_bytes()
if len(shim) != 0x4000 or kernel[: len(shim)] != shim:
    raise SystemExit("bootshim bytes/length do not match the tested 16 KiB shim")
loader = Path(sys.argv[2]).read_bytes()
if len(loader) != 0x2000 or kernel[0x4000:0x6000] != loader:
    raise SystemExit("loader is not at the audited AArch64 shim entry window")
payload_at = 0x6000
payload = kernel[payload_at:]
if payload[:8] != b"J2PRIME\0":
    raise SystemExit("J2PRIME package magic missing at 0x4000a000")
total_size = struct.unpack_from("<Q", payload, 0x48)[0]
if total_size != len(payload):
    raise SystemExit("J2PRIME package length does not match embedded payload")
src_end = 0x40004000 + kernel_size
stack_top = 0x41000000
if src_end > stack_top - 0x10000:
    raise SystemExit("loader stack reserve overlaps the loaded kernel/payload")
if src_end > 0x41000000:
    raise SystemExit("loaded image exceeds its checked low-memory source window")
print(f"image_sha256={hashlib.sha256(image).hexdigest()}")
print(f"kernel_sha256={hashlib.sha256(kernel).hexdigest()}")
print(f"kernel_bytes={kernel_size} loader=0x40008000 package=0x4000a000")
print(f"loaded_source=[0x40004000,{src_end:#x}) stack_top={stack_top:#x}")
print("XNU destination=[0x80000000,0x84000000) verified by payload audit")
print("status=OFFLINE STRUCTURAL CHECKS PASS; runtime/XNU boot not proven")
