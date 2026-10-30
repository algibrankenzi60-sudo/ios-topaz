#!/usr/bin/env python3
"""Verify the final J2 expert start path is instrumented without IOLog."""

from pathlib import Path

root = Path(__file__).resolve().parents[1]
patch = (root / "xnu/patches/0970-j2prime-expert-exit-checkpoint.patch").read_text()
expert = (root / "xnu/patches/0965-j2prime-register-platform-expert.patch").read_text()
workflow = (root / ".github/workflows/xnu.yml").read_text()

assert "iokit/Kernel/arm/J2PrimePlatformExpert.cpp" in patch
assert "J2PrimePlatformExpert::start(IOService *provider)" in expert
assert '-\tIOLog("J2PRIME: platform expert registered\\n");' in patch
assert '+\tsweet_early_mark(30, "J2 expert start exit path reached");' in patch
assert 'sweet_early_mark(18, "J2 expert registered");' in patch
assert patch.index('sweet_early_mark(18, "J2 expert registered");') < patch.index(
    'sweet_early_mark(30, "J2 expert start exit path reached");') < patch.index("return true;")
assert 'IOLog("J2PRIME: platform expert registered\\n");' in expert
assert "097[0-9]-j2prime-*" in workflow
assert "test_j2prime_expert_exit_checkpoints.py" in workflow
print("J2 expert exit path marker replaces the final IOLog and is required by CI")
