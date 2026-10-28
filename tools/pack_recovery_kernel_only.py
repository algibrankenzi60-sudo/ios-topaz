#!/usr/bin/env python3
"""Create a kernel-only Android boot image from the preserved J2 recovery header.

This is an offline packaging helper. It never accesses a device or writes a
partition. The supplied recovery image must be the verified 16 MiB backup.
"""
import argparse
import hashlib
import struct
from pathlib import Path

PAGE = 2048
PARTITION_BYTES = 16 * 1024 * 1024
EXPECTED_BACKUP_SHA256 = "fc8d45d70da23798b9e02e8b059774ca2f07bbd583801bfe813458910d993a23"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("recovery_backup", type=Path)
    ap.add_argument("kernel_payload", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()

    original = args.recovery_backup.read_bytes()
    kernel = args.kernel_payload.read_bytes()
    if len(original) != PARTITION_BYTES or original[:8] != b"ANDROID!":
        raise SystemExit("input is not the expected 16 MiB Android recovery backup")
    if hashlib.sha256(original).hexdigest() != EXPECTED_BACKUP_SHA256:
        raise SystemExit("recovery backup hash differs from the previously verified original")
    ksize, kaddr, rsize, raddr, ssize, saddr, tags, page, dt_size = struct.unpack_from(
        "<9I", original, 8
    )
    if (kaddr, raddr, page) != (0x40004000, 0x44000000, PAGE):
        raise SystemExit("recovery header addresses/page size differ from audited G532G image")
    if ssize:
        raise SystemExit("unexpected second-stage data; refusing to discard it")
    # Confirm the shim's first two literal loads and SMC exactly match the
    # component used by the already-observed four-colour recovery probe.
    shim_prefix = bytes.fromhex("04009fe504109fe5700060e1")
    if not kernel.startswith(shim_prefix):
        raise SystemExit("kernel payload does not begin with the audited MT6737 bootshim")
    total = PAGE + ((len(kernel) + PAGE - 1) // PAGE) * PAGE
    if total > PARTITION_BYTES:
        raise SystemExit(f"kernel-only image exceeds recovery partition: {total} bytes")

    image = bytearray(original[:PAGE])
    struct.pack_into("<I", image, 8, len(kernel))
    struct.pack_into("<I", image, 16, 0)  # no Android ramdisk: payload never returns to recovery
    struct.pack_into("<I", image, 40, 0)  # omit original appended recovery DTB
    image.extend(kernel)
    image.extend(bytes((-len(kernel)) % PAGE))
    image.extend(bytes(PARTITION_BYTES - len(image)))
    if len(image) != PARTITION_BYTES:
        raise SystemExit("internal image-size error")
    args.output.write_bytes(image)

    # Read back fields and payload before declaring the artifact complete.
    saved = args.output.read_bytes()
    if struct.unpack_from("<I", saved, 8)[0] != len(kernel):
        raise SystemExit("read-back kernel size mismatch")
    if struct.unpack_from("<I", saved, 16)[0] != 0:
        raise SystemExit("read-back ramdisk size is not zero")
    if saved[PAGE : PAGE + len(kernel)] != kernel:
        raise SystemExit("read-back kernel bytes differ")
    print(f"image_bytes={len(saved)} kernel_bytes={len(kernel)} ramdisk_bytes=0")
    print(f"recovery_backup_sha256={hashlib.sha256(original).hexdigest()}")
    print(f"kernel_sha256={hashlib.sha256(kernel).hexdigest()}")
    print(f"image_sha256={hashlib.sha256(saved).hexdigest()}")
    print("status=OFFLINE ARTIFACT ONLY; NOT FLASHED")


if __name__ == "__main__":
    main()
