#!/usr/bin/env python3
"""Verify the J2 ADT carries the boot entropy XNU requires during VM init."""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import adt

spec = importlib.util.spec_from_file_location('mkadt_j2', os.path.join(ROOT, 'mkadt_j2.py'))
mkadt_j2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mkadt_j2)


def find(node, name):
    if node.name == name:
        return node
    for child in node.children:
        result = find(child, name)
        if result is not None:
            return result
    return None


seed = bytes(range(1, 65))
root = mkadt_j2.build(seed)
encoded = adt.serialize(root)
decoded, end = adt.parse(encoded)
assert end == len(encoded)
chosen = find(decoded, 'chosen')
assert chosen is not None
assert chosen.prop('random-seed') == seed

for invalid in (b'', bytes(64), bytes(63), bytes(65)):
    try:
        mkadt_j2.build(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError(f'invalid random seed accepted: {len(invalid)} bytes')

print('J2 ADT includes a nonzero 64-byte /chosen/random-seed; invalid sizes rejected')
