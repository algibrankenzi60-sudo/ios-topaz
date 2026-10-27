/* AArch32 kexec entry; Linux hands off with MMU/cache disabled. */
.syntax unified
.cpu cortex-a53
.arm
.section .text.start, "ax", %progbits
.global _start
.type _start, %function

.macro J2_DELAY count
	ldr r6, =\count
.Ldelay\@:
	subs r6, r6, #1
	bne .Ldelay\@
.endm

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
	/*
	 * Linux's panel shutdown calls the G532G S6D78A0 LCM driver's
	 * lcm_setbacklight(0), which drives BLIC_EN GPIO7 and BLIC_CTL GPIO3
	 * low. The matching DTS assigns those pins to the panel backlight.
	 * Re-arm it at the driver's documented low level (brightness 20,
	 * tune level 2 = 30 EN pulses) so the framebuffer marker is visible.
	 * The GPIO set/clear aliases and pins come from the matching MT6735
	 * GPIO driver and live DT; no Topaz register or guessed address is used.
	 */
	ldr r7, =0x10211104 /* MT6735 GPIO DATAOUT set alias */
	ldr r0, =0x10211108 /* MT6735 GPIO DATAOUT clear alias */
	mov r1, #0x80       /* GPIO7: BLIC_EN */
	str r1, [r7]
	dsb sy
	J2_DELAY 8000000    /* >=10 ms across the handset CPU OPP range */
	mov r1, #0x08       /* GPIO3: BLIC_CTL */
	str r1, [r7]
	dsb sy
	J2_DELAY 4000000    /* >=5 ms across the handset CPU OPP range */
	mov r1, #0x80
	mov r4, #30
.Lblic_pulse:
	J2_DELAY 8000       /* >=10 us at the measured maximum CPU frequency */
	str r1, [r0]        /* EN low */
	dsb sy
	J2_DELAY 32000      /* >=40 us at the measured maximum CPU frequency */
	str r1, [r7]        /* EN high */
	dsb sy
	subs r4, r4, #1
	bne .Lblic_pulse
	ldr r0, =0x82000200
	ldr r1, =0x84004000
	dsb sy
	smc #0
.Lfailed_smc:
	wfe
	b .Lfailed_smc
