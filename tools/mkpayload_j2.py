#!/usr/bin/env python3
"""Build an offline J2 Mach-O package for the RAM-only kexec loader.

The J2PRIME magic is intentionally incompatible with the Topaz shim's SWEETXNU
format. It embeds the real J2 ADT and 4 KiB aligned kernel segments, with strict
bounds checks. The generated package is not itself a boot image or flash image.
"""
import argparse, hashlib, json, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adt
from mkpayload import parse_macho, apply_chained_fixups
from mkadt_j2 import RAM_BASE, RAM_SIZE

PAGE = 4096
HDR = 0x2a8
MAGIC = b'J2PRIME\0'

def align(v, a): return (v + a - 1) & -a

def build(kernel_path, adt_path, source_window=(0x40008000, 0x41000000)):
    image = bytearray(open(kernel_path, 'rb').read())
    m = parse_macho(image)
    if m['cputype'] != 0x0100000c: raise ValueError('Mach-O is not ARM64')
    if not m['entry']: raise ValueError('missing LC_UNIXTHREAD entry point')
    fixups = apply_chained_fixups(image, m)
    segs = [s for s in m['segs'] if s['vmsize']]
    if not segs or segs[0]['name'] != '__TEXT' or segs[0]['fileoff'] != 0:
        raise ValueError('unexpected Mach-O segment layout')
    virt_base = segs[0]['vmaddr'] & ~(0x2000000 - 1)
    kernel_end = align(max(s['vmaddr'] + s['vmsize'] for s in segs), PAGE)
    adt_blob = open(adt_path, 'rb').read()
    root, _ = adt.parse(adt_blob)
    chosen = next((n for n in root.children if n.name == 'chosen'), None)
    if not chosen or chosen.prop('dram-base') is None or chosen.prop('dram-size') is None:
        raise ValueError('ADT lacks candidate RAM window')
    pa, length = struct.unpack('<QQ', chosen.prop('dram-base') + chosen.prop('dram-size'))
    if (pa, length) != (RAM_BASE, RAM_SIZE):
        raise ValueError('ADT RAM window differs from configured J2 candidate')
    bias = pa - virt_base
    for s in segs:
        if s['fileoff'] + s['filesize'] > len(image): raise ValueError(f"{s['name']} exceeds Mach-O file")
        lo, hi = s['vmaddr'] + bias, s['vmaddr'] + bias + s['vmsize']
        if lo < pa or hi > pa + length: raise ValueError(f"{s['name']} destination outside audited RAM")
    kernel_end_pa = pa + (kernel_end - virt_base)
    adt_pa = align(kernel_end_pa, 4096)
    adt_end_pa = adt_pa + len(adt_blob)
    boot_args_pa = align(adt_end_pa, PAGE)
    boot_args_end = boot_args_pa + PAGE
    tables_pa = boot_args_end
    tables_end = tables_pa + 5 * PAGE
    if tables_end > pa + length:
        raise ValueError('kernel, ADT, boot_args, and five bootstrap tables exceed the audited RAM window')
    # The compressed container lives in the Android ramdisk. The loader expands
    # this package to a bounded staging window immediately below XNU's first
    # physical segment; validate this source window after the final size is known.
    src_lo, src_hi = source_window
    if src_lo >= src_hi:
        raise ValueError('invalid package source window')
    pieces = []
    for s in segs:
        data = bytes(image[s['fileoff']:s['fileoff'] + s['filesize']])
        pieces.append((s['vmaddr'], s['vmsize'], data, s['name']))
    out = bytearray(HDR + 32 * len(pieces))
    table=[]
    for va, vs, data, name in pieces:
        off=len(out); out += data; out += bytes(-len(out) & 15)
        table.append((va, vs, off, len(data)))
    adt_off=len(out); out += adt_blob; out += bytes(-len(out) & 15)
    if src_lo + len(out) > src_hi:
        raise ValueError(f'package [{src_lo:#x},{src_lo+len(out):#x}) exceeds source window ending at {src_hi:#x}')
    for va, vs, _, name in pieces:
        dst_lo, dst_hi = va + bias, va + bias + vs
        if src_lo < dst_hi and dst_lo < src_lo + len(out):
            raise ValueError(f'staging package overlaps {name}: [{src_lo:#x},{src_lo+len(out):#x}) vs [{dst_lo:#x},{dst_hi:#x})')
    if src_lo < tables_end and kernel_end_pa < src_lo + len(out):
        raise ValueError('staging package overlaps XNU end, ADT, boot_args, or bootstrap tables')
    struct.pack_into('<8sII', out, 0, MAGIC, 1, len(pieces))
    struct.pack_into('<7Q', out, 0x10, virt_base, m['entry'], adt_off, len(adt_blob), kernel_end, pa, length)
    struct.pack_into('<Q', out, 0x48, len(out))
    for i, seg in enumerate(table): struct.pack_into('<4Q', out, HDR + i*32, *seg)
    report = {
        'status': 'OFFLINE_PACKAGE; device execution remains unverified',
        'kernel_sha256': hashlib.sha256(open(kernel_path,'rb').read()).hexdigest(),
        'payload_sha256': hashlib.sha256(out).hexdigest(), 'payload_bytes': len(out),
        'format': 'J2PRIME v1, 4 KiB pages', 'segments': len(pieces), 'chained_fixups_applied': fixups,
        'virt_base': hex(virt_base), 'entry_va': hex(m['entry']), 'kernel_end_va': hex(kernel_end),
        'candidate_ram_pa': hex(pa), 'candidate_ram_size': hex(length), 'load_source_window': [hex(src_lo),hex(src_hi)],
        'segment_ranges_pa': [[name,hex(va+bias),hex(va+bias+vs)] for va,vs,_,name in pieces],
        'kernel_footprint_from_phys_base': hex((kernel_end - virt_base)),
        'adt_physical_range': [hex(adt_pa), hex(adt_end_pa)],
        'boot_args_physical_range': [hex(boot_args_pa), hex(boot_args_end)],
        'bootstrap_tables_physical_range': [hex(tables_pa), hex(tables_end)],
        'loader_identity_mapping': ['0x40000000', '0x42000000'],
        'remaining_ram_after_loader_data': hex(pa + length - tables_end),
        'adt_bytes': len(adt_blob), 'partition_limit_bytes': 16*1024*1024,
        'fits_partition_alone': len(out) <= 16*1024*1024,
    }
    return bytes(out), report

if __name__ == '__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('kernel'); ap.add_argument('adt'); ap.add_argument('out'); ap.add_argument('--report')
    ap.add_argument('--source-window', nargs=2, type=lambda x: int(x, 0), default=(0x84006000, 0x85000000), metavar=('START','END'))
    a=ap.parse_args(); blob,report=build(a.kernel,a.adt,tuple(a.source_window))
    open(a.out,'wb').write(blob)
    text=json.dumps(report,indent=2)+'\n'
    if a.report: open(a.report,'w').write(text)
    print(text,end='')
