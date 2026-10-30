#!/usr/bin/env python3
"""Guard the J2 platform-expert caller markers and patch application policy."""

from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
patch = (root / "xnu/patches/0969-j2prime-platform-expert-caller-checkpoints.patch").read_text()
workflow = (root / ".github/workflows/xnu.yml").read_text()

assert 'extern "C" void sweet_early_mark(unsigned int stage, const char *label);' in patch
for stage, label in (
    (21, "J2 expert startCandidate start returned"),
    (21, "J2 expert startCandidate start failed"),
    (22, "J2 expert sleep actions installed"),
    (23, "J2 expert startCandidate returning"),
    (24, "J2 probeCandidates resumed after expert"),
    (24, "J2 expert candidate start failed"),
):
    assert f'sweet_early_mark({stage}, "{label}")' in patch

# Every call-site marker is guarded by an exact metaclass-name check, so this
# instrumentation cannot print once per ordinary IOKit driver candidate.
assert patch.count('strcmp(service->getMetaClass()->getClassName(), "J2PrimePlatformExpert") == 0') == 1
assert patch.count('strcmp(inst->getMetaClass()->getClassName(), "J2PrimePlatformExpert") == 0') == 1
assert patch.count("#if defined(J2PRIME)") == 5

# Require contextual hunks at the service start result, success bookkeeping,
# function return, and caller continuation—not just marker strings anywhere.
hunks = re.findall(r"^@@ .* @@.*(?:\n(?:[^@].*)?)*", patch, re.MULTILINE)
assert len(hunks) == 5, f"expected declaration and four call-site hunks, got {len(hunks)}"
for context in (
    "started = startCandidate( inst );",
    "ok = service->start(this);",
    "IOInstallServiceSleepPlatformActions(service);",
    "return ok;",
):
    assert context in patch, f"missing patch context: {context}"

assert "096[0-9]-j2prime-*" in workflow
assert "test_j2prime_expert_caller_checkpoints.py" in workflow
print("J2 expert caller checkpoints are tightly gated and included in required patch validation")
