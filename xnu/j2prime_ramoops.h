#ifndef J2PRIME_RAMOOPS_H
#define J2PRIME_RAMOOPS_H

#include <stdint.h>

void j2prime_ramoops_mark(volatile void *mapped_base, uint32_t stage,
			  const char *label);

#endif
