#!/usr/bin/env python3
"""Offline byte/layout verifier for the composed J2 kexec experiment."""
import hashlib
import json
import pathlib
import struct
import sys

if len(sys.argv) != 7:
    raise SystemExit("usage: verify_j2_experiment.py IMAGE MANIFEST TRAMPOLINE LOADER PACKAGE PAYLOAD_REPORT")
image_path, manifest_path, tramp_path, loader_path, package_path, report_path = map(pathlib.Path, sys.argv[1:])
image, manifest = image_path.read_bytes(), json.loads(manifest_path.read_text())
tramp, loader, package = tramp_path.read_bytes(), loader_path.read_bytes(), package_path.read_bytes()
report = json.loads(report_path.read_text())
fail = lambda msg: (_ for _ in ()).throw(SystemExit("VERIFY FAILED: " + msg))
if manifest.get("sha256") != hashlib.sha256(image).hexdigest(): fail("whole image SHA-256")
if len(image) != manifest.get("bytes"): fail("image byte count")
if len(tramp) != 0x4000 or len(loader) != 0x2000: fail("fixed component lengths")
if image[:0x4000] != tramp: fail("trampoline bytes")
if image[0x4000:0x6000] != loader: fail("loader bytes")
if image[0x6000:0x6000 + len(package)] != package: fail("package bytes")
if set(image[0x6000 + len(package):]) - {0}: fail("nonzero tail padding")
if struct.unpack_from("<I", image, 0)[0] != 0xEA000006: fail("ARM branch opcode")
branch = struct.unpack_from("<i", image, 0)[0]
imm24 = branch & 0x00ffffff
if imm24 & 0x00800000: imm24 -= 0x01000000
if 8 + (imm24 << 2) != 0x20:
    fail("ARM branch does not skip metadata to offset 0x20")
if image[4:12] != b"J2KEX001": fail("trampoline marker")
header = struct.unpack_from("<5I", image, 12)
if header != (0x84000000, 0x84000000, 0x84004000, 0x84006000, 0x85000000): fail("entry metadata addresses")
if package[:8] != b"J2PRIME\0": fail("package magic")
if struct.unpack_from("<Q", package, 0x48)[0] != len(package): fail("package declared size")
if hashlib.sha256(package).hexdigest() != manifest.get("package_sha256"): fail("package hash")
if hashlib.sha256(tramp).hexdigest() != manifest.get("trampoline_sha256"): fail("trampoline hash")
if hashlib.sha256(loader).hexdigest() != manifest.get("loader_sha256"): fail("loader hash")
if report.get("entry_va") != "0xfffffff00740c488": fail("expected verified XNU entry VA")
if report.get("candidate_ram_pa") != "0x80000000" or report.get("candidate_ram_size") != "0x4000000": fail("candidate RAM layout")
if report.get("bootstrap_tables_physical_range") != ["0x81feb000", "0x81fef000"]: fail("page-table reservation")
if manifest.get("diagnostic_halt_before_xnu") is not False: fail("final image does not branch to XNU")
if len(image) > 0x1000000: fail("16 MiB audited kexec source window")
print("offline package checks passed:")
print("  image_sha256=" + manifest["sha256"])
print("  bytes=" + str(len(image)))
print("  ARM32 entry=0x84000000 -> SMC target=0x84004000")
print("  package=0x84006000; XNU entry VA=" + report["entry_va"])
print("  final branch mode=" + manifest["mode"])
