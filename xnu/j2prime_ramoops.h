#ifndef J2PRIME_RAMOOPS_H
#define J2PRIME_RAMOOPS_H

#include <stdint.h>

/* Values read from the running SM-G532G ramoops module parameters. */
#define J2_RAMOOPS_PHYS_BASE       0x43f10000ULL
#define J2_RAMOOPS_PHYS_BLOCK      0x43f00000ULL
#define J2_RAMOOPS_MEM_BYTES       0xe0000u
#define J2_RAMOOPS_RECORD_BYTES    0x1000u
#define J2_RAMOOPS_CONSOLE_BYTES   0x10000u
#define J2_RAMOOPS_FTRACE_BYTES    0x1000u
#define J2_RAMOOPS_PMSG_BYTES      0x1000u
#define J2_RAMOOPS_DMESG_BYTES \
	(J2_RAMOOPS_MEM_BYTES - 2u * J2_RAMOOPS_CONSOLE_BYTES - \
	 J2_RAMOOPS_FTRACE_BYTES - J2_RAMOOPS_PMSG_BYTES)
#define J2_RAMOOPS_RECORD_COUNT \
	(J2_RAMOOPS_DMESG_BYTES / J2_RAMOOPS_RECORD_BYTES)
#define J2_RAMOOPS_BLOCK_OFFSET \
	(J2_RAMOOPS_PHYS_BASE - J2_RAMOOPS_PHYS_BLOCK)

void j2prime_ramoops_mark(volatile void *mapped_base, uint32_t stage,
			  const char *label);

#endif
