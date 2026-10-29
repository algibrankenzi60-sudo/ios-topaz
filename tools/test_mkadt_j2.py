#!/usr/bin/env python3
"""Verify XNU-required entropy and the J2 pmap bootstrap ADT paths."""
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

defaults = [node for node in decoded.children if node.name == 'defaults']
assert len(defaults) == 1, "XNU pmap requires exactly one root /defaults node"
props = {name: value for name, _flags, value in defaults[0].props}
assert props['name'] == b'defaults\0'
assert 'AAPL,phandle' in props
assert 'pmap-max-asids' not in props, "leave XNU's compiled-in MAX_ASIDS default intact"
assert 'pmap-pv-count' not in props, "leave XNU's compiled-in PV defaults intact"

for invalid in (b'', bytes(64), bytes(63), bytes(65)):
    try:
        mkadt_j2.build(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError(f'invalid random seed accepted: {len(invalid)} bytes')

print('J2 ADT has nonzero /chosen/random-seed and root /defaults with stock pmap defaults')
