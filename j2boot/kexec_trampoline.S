/* AArch32 kexec entry; Linux hands off with MMU/cache disabled. */
.syntax unified
.cpu cortex-a53
.arm
.section .text.start, "ax", %progbits
.global _start
.type _start, %function
_start:
	b .Lrun
	.ascii "J2KEX001"
	.word 0x84000000 /* image base */
	.word 0x84000000 /* kexec entry */
	.word 0x84004000 /* AArch64 loader */
	.word 0x84005000 /* J2PRIME package */
	.word 0x85000000 /* reserved source-window end */
.Lrun:
	cpsid if
	/* Blue screen proves the ARM32 kexec entry ran before the SMC. */
	ldr r2, =0x7f900000
	ldr r3, =0xff0000ff
	mov r4, #960
.Lrow:
	mov r5, #540
.Lpixel:
	str r3, [r2], #4
	subs r5, r5, #1
	bne .Lpixel
	add r2, r2, #16
	subs r4, r4, #1
	bne .Lrow
	ldr r0, =0x82000200
	ldr r1, =0x84004000
	dsb sy
	smc #0
.Lfailed_smc:
	wfe
	b .Lfailed_smc
