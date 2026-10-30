#!/usr/bin/env python3
"""Guard the run-43 IOKit stage markers and their ordering."""

from pathlib import Path

root = Path(__file__).resolve().parents[1]
patch = (root / "xnu/patches/0967-j2prime-iokit-startup-checkpoints.patch").read_text()
workflow = (root / ".github/workflows/xnu.yml").read_text()

markers = (
    'sweet_early_mark(16, "ConfigureIOKit entered")',
    'sweet_early_mark(17, "ConfigureIOKit returned")',
    'sweet_early_mark(18, "StartIOKitMatching entered")',
    'sweet_early_mark(19, "StartIOKitMatching returned")',
)
for marker in markers:
    assert marker in patch, f"missing marker: {marker}"

assert patch.index(markers[0]) < patch.index("gRootNub->configureDefaults()") < patch.index(markers[1])
assert patch.index(markers[2]) < patch.index("gRootNub->startIOServiceMatching()") < patch.index(markers[3])
assert "096[0-7]-j2prime-*" in workflow
assert "test_j2prime_iokit_checkpoints.py" in workflow
print("J2 IOKit checkpoints and workflow guards are consistent")
