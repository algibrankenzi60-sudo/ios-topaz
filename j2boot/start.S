.section .text.start, "ax"
.global _start
_start:
	msr	daifset, #0xf
	msr	spsel, #1
	ldr	x0, =0x42f00000
	mov	sp, x0
	bl	j2_loader_main
1:	wfe
	b	1b
