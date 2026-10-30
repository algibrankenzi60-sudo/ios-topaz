#!/usr/bin/env python3
"""Ensure a detected serial device cannot hide J2's later boot checkpoints."""
from pathlib import Path

patch = Path("xnu/patches/0966-j2prime-keep-early-framebuffer-diagnostics.patch").read_text()
required = (
    "if (serial_exists) {",
    "#if defined(J2PRIME)",
    "Keep the validated framebuffer console for J2 IOKit bring-up markers.",
    "sweet_early_disable();",
    "#endif",
    'sweet_early_mark(20, "kprintf startup complete");',
)
for item in required:
    if item not in patch:
        raise SystemExit(f"J2 persistent marker patch is missing: {item}")

disabled_branch = patch.split("#else", 1)[1].split("#endif", 1)[0]
if "sweet_early_disable();" not in disabled_branch:
    raise SystemExit("non-J2 serial console shutdown behavior must remain unchanged")

print("J2 post-kprintf framebuffer markers remain enabled; non-J2 behavior preserved")
