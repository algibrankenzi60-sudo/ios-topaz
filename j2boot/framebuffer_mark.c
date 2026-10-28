#include <stdint.h>
#include "framebuffer_mark.h"

#define J2_FB_BASE 0x7f900000ULL

static void clean_framebuffer(void)
{
	uint64_t ctr;
	__asm__ volatile("mrs %0, ctr_el0" : "=r"(ctr));
	uint64_t line_size = 4ULL << ((ctr >> 16) & 0xf);
	for (uint64_t p = J2_FB_BASE; p < J2_FB_BASE + J2_FB_BYTES; p += line_size)
		__asm__ volatile("dc cvac, %0" :: "r"(p) : "memory");
	__asm__ volatile("dsb sy" ::: "memory");
}

void j2_framebuffer_mark(uint32_t stage)
{
	j2_framebuffer_render((volatile uint32_t *)J2_FB_BASE, stage);
	clean_framebuffer();
}
