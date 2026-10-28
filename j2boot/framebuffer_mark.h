#ifndef J2_FRAMEBUFFER_MARK_H
#define J2_FRAMEBUFFER_MARK_H

#define J2_SCREEN_ARM64_ENTRY 1
#define J2_SCREEN_LOADER_READY 2
#define J2_SCREEN_LOADER_REJECT 3
#define J2_SCREEN_XNU_HANDOFF 4
#define J2_FB_WIDTH 540U
#define J2_FB_HEIGHT 960U
#define J2_FB_STRIDE_PIXELS 544U
#define J2_FB_BYTES (J2_FB_HEIGHT * J2_FB_STRIDE_PIXELS * 4U)

#ifndef __ASSEMBLER__
#include <stdint.h>

static inline void j2_framebuffer_render(volatile uint32_t *fb, uint32_t stage)
{
	for (uint32_t y = 0; y < J2_FB_HEIGHT; ++y) {
		volatile uint32_t *row = fb + y * J2_FB_STRIDE_PIXELS;
		for (uint32_t x = 0; x < J2_FB_STRIDE_PIXELS; ++x) {
			uint32_t pixel;
			if (stage == J2_SCREEN_ARM64_ENTRY) {
				if (x < 136)
					pixel = 0xff0000ffU;
				else if (x < 272)
					pixel = 0xff00ff00U;
				else if (x < 408)
					pixel = 0xffff0000U;
				else
					pixel = 0xffffffffU;
			} else if (stage == J2_SCREEN_LOADER_READY) {
				pixel = 0xff00ff00U;
			} else if (stage == J2_SCREEN_XNU_HANDOFF) {
				pixel = 0xffffffffU;
			} else {
				pixel = 0xff0000ffU;
			}
			row[x] = pixel;
		}
	}
}

void j2_framebuffer_mark(uint32_t stage);
#endif

#endif
