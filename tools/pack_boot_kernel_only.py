#!/usr/bin/env python3
"""Build an offline normal-boot Android image for J2 XNU bring-up."""
import argparse
import hashlib
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lz4_block import decompress

PAGE = 2048
PARTITION_BYTES = 16 * 1024 * 1024
EXPECTED_BOOT_SHA256 = "40e1e206af7a483a356329c196c230fc0996664c2a802cf2f0e040a86ac5cf44"
EXPECTED_DTB_SHA256 = "191771931d78f83a6d67bf4100958625a48eb96506dd98cd7ee108869538be48"
RAMDISK_ADDR = 0x44000000
STAGE_BASE, STAGE_LIMIT = 0x80000000, 0x81000000


def align(value, unit=PAGE):
    return (value + unit - 1) // unit * unit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("boot_backup", type=Path)
    ap.add_argument("kernel_loader", type=Path)
    ap.add_argument("payload", type=Path)
    ap.add_argument("compressed_payload", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()

    original = args.boot_backup.read_bytes()
    kernel = args.kernel_loader.read_bytes()
    payload = args.payload.read_bytes()
    compressed = args.compressed_payload.read_bytes()
    if len(original) != PARTITION_BYTES or original[:8] != b"ANDROID!":
        raise SystemExit("input is not the 16 MiB Android boot backup")
    if hashlib.sha256(original).hexdigest() != EXPECTED_BOOT_SHA256:
        raise SystemExit("boot backup hash differs from the captured original")
    ksize, kaddr, rsize, raddr, ssize, _, _, page, dt_size = struct.unpack_from("<9I", original, 8)
    if (kaddr, raddr, page) != (0x40004000, RAMDISK_ADDR, PAGE) or ssize:
        raise SystemExit("boot header addresses/page size/second stage differ from audit")
    if len(kernel) != 0x6000 or kernel[:12] != bytes.fromhex("04009fe504109fe5700060e1"):
        raise SystemExit("kernel must be the audited 16 KiB shim plus 8 KiB AArch64 loader")
    if len(payload) < 0x2A8 or payload[:8] != b"J2PRIME\0" or struct.unpack_from("<Q", payload, 0x48)[0] != len(payload):
        raise SystemExit("input is not a complete J2PRIME package")
    if len(payload) > STAGE_LIMIT - STAGE_BASE:
        raise SystemExit("uncompressed package exceeds the checked staging window")

    dt_off = PAGE + align(ksize) + align(rsize) + align(ssize)
    dtb = original[dt_off : dt_off + dt_size]
    if len(dtb) != dt_size or hashlib.sha256(dtb).hexdigest() != EXPECTED_DTB_SHA256:
        raise SystemExit("original appended DTB is truncated or differs from the audit")
    if dtb[:4] != b"DTBH":
        raise SystemExit("unexpected Samsung appended-DTB container")
    if decompress(compressed, len(payload)) != payload:
        raise SystemExit("compressed payload does not decode to the supplied package")

    ramdisk = struct.pack("<8sIIQQ", b"J2LZ4\0\0\0", 1, 0, len(payload), len(compressed)) + compressed
    image = bytearray(original[:PAGE])
    struct.pack_into("<I", image, 8, len(kernel))
    struct.pack_into("<I", image, 16, len(ramdisk))
    struct.pack_into("<I", image, 40, len(dtb))
    image.extend(kernel)
    image.extend(bytes(align(len(kernel)) - len(kernel)))
    image.extend(ramdisk)
    image.extend(bytes(align(len(ramdisk)) - len(ramdisk)))
    image.extend(dtb)
    if len(image) > PARTITION_BYTES:
        raise SystemExit(f"kernel+ramdisk+DTB exceed the boot partition: {len(image)} bytes")
    image.extend(bytes(PARTITION_BYTES - len(image)))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(image)
    saved = args.output.read_bytes()
    if len(saved) != PARTITION_BYTES:
        raise SystemExit("read-back image size mismatch")
    out_dt_off = PAGE + align(len(kernel)) + align(len(ramdisk))
    if saved[PAGE : PAGE + len(kernel)] != kernel:
        raise SystemExit("read-back shim/loader mismatch")
    if saved[PAGE + align(len(kernel)) : PAGE + align(len(kernel)) + len(ramdisk)] != ramdisk:
        raise SystemExit("read-back compressed payload container mismatch")
    if saved[out_dt_off : out_dt_off + dt_size] != dtb:
        raise SystemExit("read-back appended DTB mismatch")
    print(f"image_bytes={len(saved)} kernel_bytes={len(kernel)} ramdisk_bytes={len(ramdisk)} dtb_bytes={dt_size}")
    print(f"payload_bytes={len(payload)} compressed_bytes={len(compressed)} ramdisk_load={RAMDISK_ADDR:#x}")
    print(f"staging=[{STAGE_BASE:#x},{STAGE_BASE+len(payload):#x}) DTB_sha256={hashlib.sha256(dtb).hexdigest()}")
    print(f"image_sha256={hashlib.sha256(saved).hexdigest()}")
    print("status=OFFLINE ONLY; boot partition not written")


if __name__ == "__main__":
    main()
