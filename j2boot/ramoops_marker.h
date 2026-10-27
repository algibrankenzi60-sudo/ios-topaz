#ifndef J2_RAMOOPS_MARKER_H
#define J2_RAMOOPS_MARKER_H

#define J2_STAGE_ARM32_ENTRY 1
#define J2_STAGE_ARM64_ENTRY 2
#define J2_STAGE_LOADER_READY 3
#define J2_STAGE_XNU_CALL 4

#ifndef __ASSEMBLER__
#include <stdint.h>
void j2_ramoops_mark(uint32_t stage, uint32_t info0,
		     uint32_t info1, uint32_t info2);
#endif

#endif
