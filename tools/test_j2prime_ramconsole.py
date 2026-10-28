#!/usr/bin/env python3
"""Exercise the exact fail-closed Samsung RAM-console marker writer on host."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "xnu/patches/0958-j2prime-ramconsole-exception-trace.patch"

# Test the implementation as embedded in patch 0958, without applying it to XNU.
patch = SOURCE.read_text()
start = patch.index("diff --git a/osfmk/arm64/j2prime_ramconsole.h")
end = patch.index("diff --git a/osfmk/arm64/j2prime_exception_vectors.s")
section = patch[start:end]
files = {}
current = None
collect = False
for line in section.splitlines():
    if line.startswith("diff --git "):
        current = line.split(" b/", 1)[1]
        files[current] = []
        collect = False
    elif line.startswith("@@ "):
        collect = True
    elif collect and line.startswith("+") and not line.startswith("+++"):
        files[current].append(line[1:])

vm_start = patch.index("diff --git a/osfmk/arm64/arm_vm_init.c")
vm_patch = patch[vm_start:]
assert vm_patch.index("j2prime_early_exception_install();") < vm_patch.index(
    "set_mmu_ttb_alternate(cpu_ttep & TTBR_BADDR_MASK);")
assert vm_patch.index('sweet_early_mark(27, "kernel TTBR1 active");') < vm_patch.index(
    "j2prime_ramconsole_mark(27);")
assert vm_patch.index("j2prime_ramconsole_mark(27);") < vm_patch.index(
    "j2prime_early_exception_set_phase(30);")
for marker in ["31", "32", "33", "34", "28"]:
    assert f"j2prime_ramconsole_mark({marker});" in vm_patch
assert vm_patch.index("j2prime_ramconsole_mark(34);") < vm_patch.index(
    'sweet_early_mark(28, "replacement TTBR1 aliases active; TTBR0 retained");')
assert vm_patch.index("j2prime_ramconsole_mark(28);") < vm_patch.index(
    "j2prime_early_exception_restore();")

vectors = patch[patch.index("diff --git a/osfmk/arm64/j2prime_exception_vectors.s"):]
assert ".align 11" in vectors and ".rept 16" in vectors and ".space\t124" in vectors
for reg in ["esr_el1", "elr_el1", "far_el1", "spsr_el1"]:
    assert f"mrs\tx" in vectors and reg in vectors

with tempfile.TemporaryDirectory(prefix="j2-ramconsole-host-") as td:
    tmp = Path(td)
    for rel, lines in files.items():
        out = tmp / Path(rel).name
        out.write_text("\n".join(lines) + "\n")
    source = tmp / "j2prime_ramconsole.c"
    header = tmp / "j2prime_ramconsole.h"
    harness = tmp / "test.c"
    harness.write_text(f'''#include <assert.h>
#include <stdint.h>
#include <string.h>
#define J2_RAMCONSOLE_HOST_TEST 1
#include "{source}"

int main(void) {{
    uint8_t mem[J2_RAMCONSOLE_SIZE];
    memset(mem, 0xa5, sizeof(mem));
    volatile struct j2_ramconsole_header *h =
        (volatile struct j2_ramconsole_header *)mem;
    h->sig = J2_RAMCONSOLE_SIG;
    h->sz_buffer = J2_RAMCONSOLE_SIZE;
    h->off_linux = 512;
    h->off_console = 1216; /* 512 + ALIGN(sizeof(G532G rr), 64), NR_CPUS=4 */
    assert(h->off_console - h->off_linux == 704u);
    h->sz_console = J2_RAMCONSOLE_SIZE - h->off_console;
    h->log_start = 0;
    h->log_size = 17;
    uint32_t at = h->off_linux + J2_RAMCONSOLE_FIQ_STEP_OFFSET;
    uint8_t before[J2_RAMCONSOLE_SIZE];
    memcpy(before, mem, sizeof(mem));
    j2_store_marker((uintptr_t)mem, 0x4a32001bu);
    assert(*(uint32_t *)(mem + at) == 0x4a32001bu);
    for (uint32_t i = 0; i < sizeof(mem); ++i) {{
        if (i < at || i >= at + sizeof(uint32_t)) assert(mem[i] == before[i]);
    }}

    memcpy(mem, before, sizeof(mem));
    h->sig ^= 1u;
    memcpy(before, mem, sizeof(mem));
    j2_store_marker((uintptr_t)mem, 0x4a32001cu);
    assert(memcmp(mem, before, sizeof(mem)) == 0);

    memcpy(mem, before, sizeof(mem));
    h->sig = J2_RAMCONSOLE_SIG;
    h->off_console = h->off_linux + 256u;
    memcpy(before, mem, sizeof(mem));
    j2_store_marker((uintptr_t)mem, 0x4a32001du);
    assert(memcmp(mem, before, sizeof(mem)) == 0);

    assert(j2_exception_marker((uint64_t)0x24 << 26, 35) == 0x4a2e2423u);
    assert(J2_RAMCONSOLE_BASE + J2_RAMCONSOLE_SIZE == 0x43f10000ULL);

    /* Append only to a non-wrapped tail; existing Samsung log stays intact. */
    h->sig = J2_RAMCONSOLE_SIG;
    h->off_linux = 512;
    h->off_console = 1216;
    h->sz_console = J2_RAMCONSOLE_SIZE - h->off_console;
    h->log_start = h->log_size = 17;
    memcpy(mem + h->off_console, "preserved-log!!", 15);
    char line[128];
    uint32_t n = j2_format_exception(line, 35, 0x96000004ULL,
        0xfffffff012345678ULL, 0x43f00000ULL, 0x3c5ULL);
    assert(n < sizeof(line));
    assert(j2_append_console_line((uintptr_t)mem, line, n) == 1);
    assert(h->log_size == 17 + n && h->log_start == 17 + n);
    assert(memcmp(mem + h->off_console, "preserved-log!!", 15) == 0);
    assert(memcmp(mem + h->off_console + 17, line, n) == 0);
    assert(memcmp(line, "J2XNU EXC phase=0000000000000023 ESR=", 37) == 0);

    /* Wrapped/full rings and insufficient capacity must not be modified. */
    h->log_start = 4; h->log_size = 17;
    memcpy(before, mem, sizeof(mem));
    assert(j2_append_console_line((uintptr_t)mem, line, n) == 0);
    assert(memcmp(mem, before, sizeof(mem)) == 0);
    h->log_start = h->sz_console;
    h->log_size = h->sz_console;
    memcpy(before, mem, sizeof(mem));
    assert(j2_append_console_line((uintptr_t)mem, line, n) == 0);
    assert(memcmp(mem, before, sizeof(mem)) == 0);
    return 0;
}}
''')
    binary = tmp / "test"
    subprocess.run(
        ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", str(harness), "-o", str(binary)],
        check=True,
    )
    subprocess.run([str(binary)], check=True)

print("J2 RAM-console writer, exception vector, phase ordering, and fail-closed host checks passed")
