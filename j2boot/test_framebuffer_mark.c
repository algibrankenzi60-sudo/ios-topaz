/* Host-only test; the fake framebuffer is ordinary process memory. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "framebuffer_mark.h"

int main(void)
{
	volatile uint32_t *fb = calloc(J2_FB_HEIGHT * J2_FB_STRIDE_PIXELS,
				       sizeof(*fb));
	assert(fb != NULL);
	j2_framebuffer_render(fb, J2_SCREEN_ARM64_ENTRY);
	assert(fb[0] == 0xff0000ffU);
	assert(fb[136] == 0xff00ff00U);
	assert(fb[272] == 0xffff0000U);
	assert(fb[408] == 0xffffffffU);
	assert(fb[(J2_FB_HEIGHT - 1) * J2_FB_STRIDE_PIXELS + 543] == 0xffffffffU);
	j2_framebuffer_render(fb, J2_SCREEN_LOADER_READY);
	assert(fb[0] == 0xff00ff00U);
	assert(fb[J2_FB_HEIGHT * J2_FB_STRIDE_PIXELS - 1] == 0xff00ff00U);
	j2_framebuffer_render(fb, J2_SCREEN_LOADER_REJECT);
	assert(fb[0] == 0xff0000ffU);
	assert(fb[J2_FB_HEIGHT * J2_FB_STRIDE_PIXELS - 1] == 0xff0000ffU);
	j2_framebuffer_render(fb, J2_SCREEN_XNU_HANDOFF);
	assert(fb[0] == 0xffffffffU);
	assert(fb[J2_FB_HEIGHT * J2_FB_STRIDE_PIXELS - 1] == 0xffffffffU);
	free((void *)fb);
	puts("J2 framebuffer stage marker pattern checks passed, including pre-XNU handoff");
	return 0;
}
