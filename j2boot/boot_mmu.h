#ifndef J2_BOOT_MMU_H
#define J2_BOOT_MMU_H

#include <stdint.h>

#define J2_PAGE_SIZE       0x1000ULL
#define J2_BLOCK_SIZE      0x200000ULL
#define J2_TABLE_BYTES     0x4000ULL
#define J2_TTBR_MASK       0x0000fffffffff000ULL
#define J2_TTE_TABLE       0x3ULL
#define J2_TTE_NORMAL_RW   0x601ULL /* valid, AF, outer-shareable, AttrIdx 0 */

#define J2_MAIR_EL1        0x00000000000000ffULL
#define J2_TCR_EL1_BOOT    0x00000022a519a519ULL
#define J2_SCTLR_EL1_BOOT  0x000000003454593dULL

/* Four 4 KiB tables: TTBR0 L1/L2 for PA identity, TTBR1 L1/L2 for kernel VA. */
static inline int
j2_build_boot_tables(volatile uint64_t *tables, uint64_t tables_pa,
		     uint64_t virt_base, uint64_t phys_base,
		     uint64_t mem_size, uint64_t identity_end)
{
	volatile uint64_t *ttbr0_l1 = tables;
	volatile uint64_t *ttbr0_l2 = tables + 512;
	volatile uint64_t *ttbr1_l1 = tables + 1024;
	volatile uint64_t *ttbr1_l2 = tables + 1536;
	uint64_t va_limit, pa_limit;

	if (!tables || (tables_pa & (J2_PAGE_SIZE - 1)) ||
	    (virt_base & (J2_BLOCK_SIZE - 1)) ||
	    (phys_base & (J2_BLOCK_SIZE - 1)) ||
	    (mem_size & (J2_BLOCK_SIZE - 1)) ||
	    identity_end < phys_base + mem_size ||
	    (identity_end & (J2_BLOCK_SIZE - 1)) ||
	    tables_pa > J2_TTBR_MASK || tables_pa + J2_TABLE_BYTES < tables_pa ||
	    tables_pa + J2_TABLE_BYTES > identity_end ||
	    (virt_base >> 39) != ((1ULL << 25) - 1))
		return 0;
	if (virt_base > UINT64_MAX - mem_size || phys_base > UINT64_MAX - mem_size ||
	    identity_end > UINT64_MAX - J2_BLOCK_SIZE)
		return 0;
	va_limit = virt_base + mem_size;
	pa_limit = phys_base + mem_size;
	if (((virt_base >> 30) & 0x1ff) != (((va_limit - 1) >> 30) & 0x1ff) ||
	    ((phys_base >> 30) & 0x1ff) != (((pa_limit - 1) >> 30) & 0x1ff) ||
	    ((phys_base >> 30) & 0x1ff) != (((identity_end - 1) >> 30) & 0x1ff))
		return 0;

	for (unsigned int i = 0; i < 2048; ++i)
		tables[i] = 0;

	unsigned int pa_l1 = (unsigned int)((phys_base >> 30) & 0x1ff);
	unsigned int va_l1 = (unsigned int)((virt_base >> 30) & 0x1ff);
	unsigned int pa_l2 = (unsigned int)((phys_base >> 21) & 0x1ff);
	unsigned int va_l2 = (unsigned int)((virt_base >> 21) & 0x1ff);
	unsigned int mem_blocks = (unsigned int)(mem_size / J2_BLOCK_SIZE);
	unsigned int identity_blocks = (unsigned int)((identity_end - phys_base) / J2_BLOCK_SIZE);

	if (pa_l2 + identity_blocks > 512 || va_l2 + mem_blocks > 512)
		return 0;
	ttbr0_l1[pa_l1] = (tables_pa + J2_PAGE_SIZE) | J2_TTE_TABLE;
	ttbr1_l1[va_l1] = (tables_pa + 3 * J2_PAGE_SIZE) | J2_TTE_TABLE;
	for (unsigned int i = 0; i < identity_blocks; ++i)
		ttbr0_l2[pa_l2 + i] = (phys_base + (uint64_t)i * J2_BLOCK_SIZE) | J2_TTE_NORMAL_RW;
	for (unsigned int i = 0; i < mem_blocks; ++i)
		ttbr1_l2[va_l2 + i] = (phys_base + (uint64_t)i * J2_BLOCK_SIZE) | J2_TTE_NORMAL_RW;
	return 1;
}

#endif
