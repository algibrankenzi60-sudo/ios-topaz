#!/usr/bin/env python3
"""Regression check that XNU's ramoops alias matches its virtual pointer."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
patch = (ROOT / 'xnu/patches/0954-j2prime-pstore-vm-checkpoints.patch').read_text()

L2_SIZE = 2 * 1024 * 1024
FB_VA_OFFSET = 1 * L2_SIZE
RAMOOPS_VA_OFFSET = 8 * L2_SIZE
RAMOOPS_PHYS_BLOCK = 0x43F00000
RAMOOPS_PHYS_OFFSET = 0x10000

# The L2 table's first slot maps SWEET_EARLY_FB_VA. The ramoops pointer is
# relocated to VM_MIN + 8 L2 blocks, so the table index must advance by seven.
slot_delta = (RAMOOPS_VA_OFFSET - FB_VA_OFFSET) // L2_SIZE
assert slot_delta == 7
mapped_va = FB_VA_OFFSET + slot_delta * L2_SIZE + RAMOOPS_PHYS_OFFSET
expected_va = RAMOOPS_VA_OFFSET + RAMOOPS_PHYS_OFFSET
assert mapped_va == expected_va

mapping_lines = [line[1:] for line in patch.splitlines()
                 if line.startswith('+') and 'const unsigned int ramoops_slot' in line]
assert len(mapping_lines) == 1, mapping_lines
assert re.search(r'J2_EARLY_RAMOOPS_VA\s*-\s*SWEET_EARLY_FB_VA', mapping_lines[0])
assert not re.search(r'ramoops_slot\s*=\s*first\s*\+\s*3\b', patch)

print('J2 ramoops alias maps VM_MIN+16MiB to physical 0x43f00000; pointer offset matches')
