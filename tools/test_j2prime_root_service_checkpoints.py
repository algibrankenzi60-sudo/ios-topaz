#!/usr/bin/env python3
"""Guard the J2-only root IOKit registration checkpoints."""

from pathlib import Path

root = Path(__file__).resolve().parents[1]
patch = (root / "xnu/patches/0968-j2prime-root-service-matching-checkpoints.patch").read_text()
workflow = (root / ".github/workflows/xnu.yml").read_text()

assert 'extern "C" void sweet_early_mark(unsigned int stage, const char *label);' in patch
assert patch.count("#if defined(J2PRIME)") == 3
assert 'sweet_early_mark(16, "J2 root workloop create entered")' in patch
assert 'sweet_early_mark(17, "J2 root workloop create returned")' in patch
assert 'sweet_early_mark(18, "J2 root service register entered")' in patch
assert 'sweet_early_mark(19, "J2 root service register returned")' in patch

assert patch.index("@@ -2058,0 +2059,3 @@") < patch.index('sweet_early_mark(16, "J2 root workloop create entered")')
assert patch.index("@@ -2063,0 +2067,4 @@") < patch.index('sweet_early_mark(17, "J2 root workloop create returned")')
assert patch.index('sweet_early_mark(17, "J2 root workloop create returned")') < patch.index('sweet_early_mark(18, "J2 root service register entered")')
assert patch.index("@@ -2064,0 +2072,3 @@") < patch.index('sweet_early_mark(19, "J2 root service register returned")')
assert "test_j2prime_root_service_checkpoints.py" in workflow
assert "096[0-8]-j2prime-*" in workflow
print("J2 root IOKit matching checkpoints and CI guard are consistent")
