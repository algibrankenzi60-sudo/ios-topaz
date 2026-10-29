#!/usr/bin/env python3
"""Guard the J2 zero-deadline adaptation for console progress calls."""

from pathlib import Path

patch = Path("xnu/patches/0962-j2prime-zero-deadline-video-call.patch").read_text()
required = (
    "vc_thread_call_enter_deadline(thread_call_t call, uint64_t deadline)",
    "#if defined(J2PRIME)",
    "if (deadline == 0)",
    "thread_call_enter(call);",
    "thread_call_enter_delayed(call, deadline);",
    "&vc_progressmeter_call, vc_progressmeter_deadline",
    "&vc_progress_call, vc_progress_deadline",
)
missing = [item for item in required if item not in patch]
if missing:
    raise SystemExit("J2 zero-deadline patch is incomplete: " + ", ".join(missing))

replaced_calls = sum(
    line.startswith("-") and "thread_call_enter_delayed(" in line
    for line in patch.splitlines()
)
if replaced_calls != 6:
    raise SystemExit(f"expected six console delayed-call sites to use helper; found {replaced_calls}")

print("J2 zero-deadline patch checks passed")
