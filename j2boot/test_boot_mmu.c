/* Host test: validate the exact table builder without touching device RAM. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "boot_mmu.h"

int main(void)
{
	const uint64_t table_pa = 0x81feb000ULL;
	const uint64_t virt_base = 0xfffffff006000000ULL;
	const uint64_t phys_base = 0x80000000ULL;
	const uint64_t mem_size = 0x04000000ULL;
	const uint64_t identity_end = 0x85000000ULL;
	volatile uint64_t *t = aligned_alloc(J2_PAGE_SIZE, J2_TABLE_BYTES);
	assert(t != NULL);
	assert(J2_TCR_EL1_BOOT == 0x22a519a519ULL);
	assert(J2_SCTLR_EL1_BOOT == 0x3454593dULL);
	assert(J2_MAIR_EL1 == 0xffULL);

	assert(j2_build_boot_tables(t, table_pa, virt_base, phys_base,
	                            mem_size, identity_end));
	assert(t[2] == (table_pa + J2_PAGE_SIZE) + J2_TTE_TABLE);
	assert(t[1024 + 448] == (table_pa + 3 * J2_PAGE_SIZE) + J2_TTE_TABLE);
	assert(t[512 + 0] == 0x80000601ULL); /* identity RAM base */
	assert(t[512 + 31] == 0x83e00601ULL); /* last advertised XNU block */
	assert(t[512 + 32] == 0x84000601ULL); /* physical trampoline/source */
	assert(t[512 + 39] == 0x84e00601ULL); /* end of mapped source */
	assert(t[1024 + 512 + 58] == 0x81400601ULL); /* XNU entry VA block */
	assert((t[1024 + 512 + 58] & 1) != 0);
	assert((t[1024 + 512 + 80] & 1) == 0); /* outside 64 MiB KVA */

	assert(!j2_build_boot_tables(t, table_pa, virt_base + 1, phys_base,
	                             mem_size, identity_end));
	assert(!j2_build_boot_tables(t, table_pa, virt_base, phys_base,
	                             mem_size, 0x84001000ULL));
	free((void *)t);
	puts("J2 TTBR0 identity + TTBR1 XNU VA mappings passed");
	return 0;
}
