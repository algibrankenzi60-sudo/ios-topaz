.section .text.start, "ax"
#include "ramoops_marker.h"
.global _start
_start:
	/* Record the actual AArch64 exception level and control-register state. */
	mrs	x1, CurrentEL
	mrs	x2, SCTLR_EL1
	mov	x3, xzr
	cmp	x1, #8
	b.lo	1f
	mrs	x3, SCTLR_EL2
1:
	msr	daifset, #0xf
	msr	spsel, #1
	/* Separate from the payload at 0x40008000 and the XNU image at 0x81004000+. */
	ldr	x0, =0x80f00000
	mov	sp, x0
	mov	w0, #J2_STAGE_ARM64_ENTRY
	mov	w1, w1
	mov	w2, w2
	mov	w3, w3
	bl	j2_ramoops_mark
	bl	j2_loader_main
1:	wfe
	b	1b
