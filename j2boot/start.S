.section .text.start, "ax"
.global _start
_start:
	msr	daifset, #0xf
	msr	spsel, #1
	/* Separate from the payload at 0x40008000 and the XNU image at 0x81004000+. */
	ldr	x0, =0x80f00000
	mov	sp, x0
	bl	j2_loader_main
1:	wfe
	b	1b
