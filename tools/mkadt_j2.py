#!/usr/bin/env python3
"""Create a conservative J2 Prime ADT from the captured Android DTB.

The 64 MiB early-boot window is a subset of the observed upper System RAM
interval, starts at the exact end of the captured consys alloc-range, and is
checked against every memory/reserved-memory range in the input FDT.
"""
import argparse
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adt

DEFAULT_DTB = '/mnt/d/J2-iOS-audit-20261027/live-boot-88f000.dtb'
# Captured /proc/iomem audit: 0x80000000..0x9f5c0000 is contiguous System RAM.
# The live FDT's dynamic consys alloc-range is [0x40000000,0x80000000).
# Keep the first XNU window to a conservative 64 MiB subset at that boundary.
RAM_BASE, RAM_SIZE = 0x80000000, 0x04000000
SOC_BASE = 0x01000000
GICD, GICC = 0x10221000, 0x10222000
GIC_SIZE = 0x10000
FB, FB_SIZE = 0x7f900000, 0x1fe000
FB_W, FB_H, FB_STRIDE = 540, 960, 2176
TIMEBASE, VTIMER_INTID = 13_000_000, 27

def u32(*v): return struct.pack('<%dI' % len(v), *v)
def u64(*v): return struct.pack('<%dQ' % len(v), *v)
def cstr(s): return s.encode() + b'\0'

def node(name, props=(), children=()):
    n = adt.Node()
    n.props = [('name', 0, cstr(name))] + [(k, 0, v) for k, v in props]
    n.children = list(children)
    return n

class FNode:
    def __init__(self, name): self.name, self.props, self.children = name, {}, []

def parse_fdt(blob):
    if len(blob) < 40: raise ValueError('short FDT')
    magic, total, struct_off, strings_off, _, version, _, _, strings_size, struct_size = struct.unpack_from('>10I', blob)
    if magic != 0xd00dfeed or total > len(blob) or version < 17:
        raise ValueError('invalid/unsupported FDT header')
    strings = blob[strings_off:strings_off + strings_size]
    pos, end, stack, root = struct_off, struct_off + struct_size, [], None
    while pos + 4 <= end:
        token, = struct.unpack_from('>I', blob, pos); pos += 4
        if token == 1:
            stop = blob.index(b'\0', pos, end)
            name = blob[pos:stop].decode(errors='strict'); pos = (stop + 4) & ~3
            cur = FNode(name)
            if stack: stack[-1].children.append(cur)
            else: root = cur
            stack.append(cur)
        elif token == 2:
            if not stack: raise ValueError('unbalanced FDT node end')
            stack.pop()
        elif token == 3:
            size, nameoff = struct.unpack_from('>II', blob, pos); pos += 8
            stop = strings.index(b'\0', nameoff)
            name = strings[nameoff:stop].decode()
            stack[-1].props[name] = blob[pos:pos + size]
            pos = (pos + size + 3) & ~3
        elif token == 4: continue
        elif token == 9: break
        else: raise ValueError(f'unknown FDT token {token:#x}')
    if root is None or stack: raise ValueError('incomplete FDT')
    return root

def be_cells(raw, n):
    if len(raw) != 4*n: raise ValueError('invalid DT cell tuple')
    return int.from_bytes(raw, 'big')

def audit_ram(dtb_path, base=RAM_BASE, size=RAM_SIZE, iomem_path=None):
    root = parse_fdt(open(dtb_path, 'rb').read())
    ac = be_cells(root.props.get('#address-cells', b'\0\0\0\2'), 1)
    sc = be_cells(root.props.get('#size-cells', b'\0\0\0\2'), 1)
    banks = []
    for n in root.children:
        if n.name.startswith('memory') or n.props.get('device_type') == b'memory\0':
            reg = n.props.get('reg', b'')
            cells = 4*(ac+sc)
            if not reg or len(reg) % cells: raise ValueError(f'bad memory reg in {n.name}')
            for i in range(0, len(reg), cells):
                banks.append((be_cells(reg[i:i+4*ac], ac), be_cells(reg[i+4*ac:i+cells], sc)))
    if not banks: raise ValueError('DTB has no memory bank')
    rm = next((n for n in root.children if n.name == 'reserved-memory'), None)
    reserved, dynamic = [], []
    if rm:
        rac = be_cells(rm.props.get('#address-cells', root.props.get('#address-cells')), 1)
        rsc = be_cells(rm.props.get('#size-cells', root.props.get('#size-cells')), 1)
        step = 4*(rac+rsc)
        for n in rm.children:
            raw = n.props.get('reg', b'')
            if raw:
                if len(raw) % step: raise ValueError(f'bad reserved reg in {n.name}')
                for i in range(0, len(raw), step):
                    reserved.append((be_cells(raw[i:i+4*rac], rac), be_cells(raw[i+4*rac:i+step], rsc), n.name))
            elif n.props.get('size'):
                sz = be_cells(n.props['size'], rsc)
                ar = n.props.get('alloc-ranges', b'')
                ranges = []
                if ar:
                    if len(ar) % step: raise ValueError(f'bad alloc-ranges in {n.name}')
                    for i in range(0, len(ar), step):
                        ranges.append((be_cells(ar[i:i+4*rac], rac), be_cells(ar[i+4*rac:i+step], rsc)))
                dynamic.append((n.name, sz, ranges))
    bank_ok = any(base >= b and base + size <= b + s for b, s in banks)
    overlaps = [(b, s, n) for b, s, n in reserved if base < b+s and b < base+size]
    if not bank_ok: raise ValueError(f'RAM window {base:#x}+{size:#x} is outside captured FDT memory banks {banks!r}')
    if overlaps: raise ValueError(f'RAM window overlaps reserved-memory: {overlaps!r}')
    dynamic_risk = [n for n, sz, ranges in dynamic if not ranges or any(base < b+s and b < base+size for b,s in ranges)]
    dynamic_overlaps = []
    for n, sz, ranges in dynamic:
        for b, s in ranges:
            lo, hi = max(base, b), min(base + size, b + s)
            if lo < hi:
                dynamic_overlaps.append([n, hex(lo), hex(hi)])
    runtime_ram = None
    if iomem_path:
        runtime_ram = []
        for line in open(iomem_path, encoding='ascii', errors='replace'):
            m = re.match(r'^\s*([0-9a-fA-F]+)-([0-9a-fA-F]+)\s*:\s*System RAM\s*$', line)
            if m:
                lo, hi_inclusive = int(m.group(1), 16), int(m.group(2), 16)
                if hi_inclusive < lo: raise ValueError(f'invalid /proc/iomem interval: {line.rstrip()}')
                runtime_ram.append((lo, hi_inclusive + 1))
        if not runtime_ram: raise ValueError(f'no System RAM intervals found in {iomem_path}')
        if not any(base >= lo and base + size <= hi for lo, hi in runtime_ram):
            raise ValueError(f'candidate RAM [{base:#x},{base+size:#x}) is not inside one /proc/iomem System RAM interval')
    return {'dtb': os.path.basename(dtb_path), 'memory_banks': [[hex(b), hex(s)] for b,s in banks],
            'static_reserved': [[hex(b), hex(s), n] for b,s,n in reserved],
            'dynamic_reserved': [{'node':n,'size':hex(sz),'alloc_ranges':[[hex(b),hex(s)] for b,s in ranges]} for n,sz,ranges in dynamic],
            'kernel_ram': [hex(base), hex(size)], 'static_reserved_overlap': [],
            'dynamic_reservation_risk': dynamic_risk, 'dynamic_alloc_range_overlap': dynamic_overlaps,
            'runtime_system_ram': [[hex(lo),hex(hi)] for lo,hi in runtime_ram] if runtime_ram else None,
            'runtime_iomem_source': os.path.abspath(iomem_path) if iomem_path else None,
            'caveat': ('Candidate is inside captured FDT RAM, outside static reservations and every declared dynamic alloc-range, '
                       'and contained in one captured runtime System RAM interval. Exact consys base is not logged in the available '
                       'kernel ring; undocumented firmware ownership is still outside these checks.' if runtime_ram else
                       'Candidate is inside captured FDT RAM and outside static reservations and declared dynamic alloc-ranges; '
                       'no runtime /proc/iomem evidence was supplied.')}

def build():
    phandle = iter(range(1, 100))
    ph = lambda: ('AAPL,phandle', u32(next(phandle)))
    chosen = node('chosen', [ph(), ('dram-base', u64(RAM_BASE)), ('dram-size', u64(RAM_SIZE)),
        ('debug-enabled', u32(1)),
        ('firmware-version', cstr('j2prime-mt6737t-earlyboot'))],
        [node('memory-map', [ph()])])
    cpu = node('cpu0', [ph(), ('device_type', cstr('cpu')), ('compatible', cstr('arm,cortex-a53')),
        ('reg', u32(0)), ('cpu-id', u32(0)), ('cluster-id', u32(0)),
        ('cluster-type', u32(0)), ('cluster-core-id', u32(0)),
        ('state', cstr('running')), ('clock-frequency', u32(1_300_000_000)),
        ('timebase-frequency', u32(TIMEBASE))])
    cpus = node('cpus', [ph(), ('#address-cells', u32(1)), ('#size-cells', u32(0))], [cpu])
    # Bus offsets are relative to the explicitly declared 16 MiB /arm-io base.
    gic = node('gic', [ph(), ('compatible', cstr('arm,gic-v2') + cstr('mediatek,mt6735-gic')),
        ('interrupt-controller', b''), ('#interrupt-cells', u32(3)),
        ('virtual-timer-intid', u32(VTIMER_INTID)),
        ('reg', u64(GICD-SOC_BASE, GIC_SIZE, GICC-SOC_BASE, GIC_SIZE))])
    armio = node('arm-io', [ph(), ('device_type', cstr('j2prime-io')),
        ('compatible', cstr('j2prime,mt6737t-io') + cstr('arm-io')),
        ('#address-cells', u32(2)), ('#size-cells', u32(2)),
        ('ranges', u64(0, SOC_BASE, 0x100000000-SOC_BASE))], [gic])
    fbcon = node('fbcon', [ph(), ('reg', u64(FB, FB_SIZE)), ('width', u32(FB_W)),
        ('height', u32(FB_H)), ('rowBytes', u32(FB_STRIDE)), ('depth', u32(32)),
        ('pixel-format', cstr('ARGB8888'))])
    return node('device-tree', [ph(), ('compatible', cstr('samsung,sm-g532g') +
        cstr('samsung,grand-prime-plus') + cstr('mediatek,mt6737t') + cstr('J2PRIME')),
        ('model', cstr('Samsung Galaxy J2 Prime SM-G532G')), ('manufacturer', cstr('Samsung')),
        ('#address-cells', u32(2)), ('#size-cells', u32(2))], [chosen, cpus, armio, fbcon])

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--dtb', default=DEFAULT_DTB); ap.add_argument('--iomem')
    ap.add_argument('--audit-json')
    a = ap.parse_args()
    audit = audit_ram(a.dtb, iomem_path=a.iomem)
    if audit['dynamic_reservation_risk']:
        raise SystemExit('candidate RAM intersects a dynamic reserved-memory allocation range: ' +
                         ', '.join(audit['dynamic_reservation_risk']))
    blob = adt.serialize(build())
    with open(a.out, 'wb') as f: f.write(blob)
    if a.audit_json:
        with open(a.audit_json, 'w') as f: json.dump(audit, f, indent=2); f.write('\n')
    print(f'{a.out}: {len(blob)} bytes; candidate RAM [{RAM_BASE:#x},{RAM_BASE+RAM_SIZE:#x}); diagnostic ADT')
