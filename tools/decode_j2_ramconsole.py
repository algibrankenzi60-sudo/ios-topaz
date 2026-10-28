#!/usr/bin/env python3
"""Decode the one-word J2 XNU marker shown in /proc/last_kmsg."""
import re
import sys
from pathlib import Path


def describe(value: int) -> str:
    if value >> 16 == 0x4A32:
        stage = value & 0xFF
        return f"XNU reached post-operation stage {stage} (0x{value:08x})"
    if value >> 16 == 0x4A2E:
        exception_class = (value >> 8) & 0x3F
        phase = value & 0xFF
        return (f"XNU exception class 0x{exception_class:02x} in phase {phase} "
                f"(0x{value:08x})")
    return f"unrecognized/stock fiq_step {value} (0x{value:08x})"


def main() -> int:
    if len(sys.argv) > 2:
        print(f"usage: {sys.argv[0]} [last_kmsg.txt]", file=sys.stderr)
        return 2
    text = Path(sys.argv[1]).read_text(errors="replace") if len(sys.argv) == 2 else sys.stdin.read()
    match = re.search(r"fiq step\s+(\d+)", text, re.IGNORECASE)
    if match is None:
        print("No RAM-console fiq_step line found", file=sys.stderr)
        return 1
    print(describe(int(match.group(1))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
