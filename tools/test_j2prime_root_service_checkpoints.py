#!/usr/bin/env python3
"""Guard J2-only root IOKit checkpoints against file-scope patch placement."""

from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
patch = (root / "xnu/patches/0968-j2prime-root-service-matching-checkpoints.patch").read_text()
workflow = (root / ".github/workflows/xnu.yml").read_text()

assert 'extern "C" void sweet_early_mark(unsigned int stage, const char *label);' in patch
for stage, label in (
    (16, "J2 root workloop create entered"),
    (17, "J2 root workloop create returned"),
    (18, "J2 root service register entered"),
    (19, "J2 root service register returned"),
):
    assert f'sweet_early_mark({stage}, "{label}")' in patch

# The previous zero-context hunks silently landed at file scope after source
# offsets drifted. Require contextual hunks that identify the actual function.
hunks = re.findall(r"^@@ .* @@.*(?:\n(?:[^@].*)?)*", patch, re.MULTILINE)
assert len(hunks) == 2, f"expected declaration and function hunks, got {len(hunks)}"
assert "@@ -48," in hunks[0] and "#include <sys/csr.h>" in hunks[0]
assert "IOPlatformExpertDevice::startIOServiceMatching(void)" in hunks[1]
assert "workLoop = IOWorkLoop::workLoop();" in hunks[1]
assert "registerService();" in hunks[1]
for stage in (16, 17, 18, 19):
    assert f"sweet_early_mark({stage}," in hunks[1]
assert "@@ -2058,0" not in patch and "@@ -2063,0" not in patch

assert "test_j2prime_root_service_checkpoints.py" in workflow
assert "096[0-8]-j2prime-*" in workflow
print("J2 root checkpoints are context-anchored inside startIOServiceMatching")
