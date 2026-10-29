#!/usr/bin/env python3
"""Guard the J2-only thread-call deadline panic diagnostic patch."""

from pathlib import Path


patch = Path("xnu/patches/0961-j2prime-report-thread-call-deadline-panic.patch").read_text()
required = (
    "#if defined(J2PRIME)",
    "J2 thread_call deadline invariant:",
    "call->tc_soft_deadline == 0",
    "call->tc_soft_deadline > call->tc_pqlink.deadline",
    "call->tc_func",
    "call->tc_soft_deadline",
    "call->tc_pqlink.deadline",
    "call->tc_flags",
    "(unsigned int)flavor",
    "#else",
    "assert((call->tc_soft_deadline != 0)",
    "#endif",
)
missing = [needle for needle in required if needle not in patch]
if missing:
    raise SystemExit("J2 thread-call diagnostic patch is incomplete: " + ", ".join(missing))

print("J2 thread-call diagnostic patch checks passed")
