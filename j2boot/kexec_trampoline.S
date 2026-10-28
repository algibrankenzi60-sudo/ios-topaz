/* Linux ARM32 kexec entry for Samsung G532G / MT6737T. */
.syntax unified
.cpu cortex-a53
.arm
#include "ramoops_marker.h"
.section .text.start, "ax", %progbits
.global _start
.type _start, %function

_start:
	b .Lrun
	.ascii "J2KEX001"
	.word 0x84000000 /* image base */
	.word 0x84000000 /* ARM32 kexec entry */
	.word 0x84004000 /* MT6737 AArch64 handoff stage */
	.word 0x84006000 /* J2PRIME package */
	.word 0x85000000 /* audited source-window end */
.Lrun:
	cpsid if
	/* Samsung Linux relocate_kernel enters in ARM state with r0/r1/r2 ABI;
	 * use a known physical stack because its restart stack is unmapped now. */
	ldr sp, =0x83f00000
	mov r0, #J2_STAGE_ARM32_ENTRY
	mov r1, #0
	mov r2, #0
	mov r3, #0
	bl j2_ramoops_mark
	/* MT6737 SiP service: r0=function ID, r1=AArch64 physical entry. */
	ldr r0, =0x82000200
	ldr r1, =0x84004000
	dsb sy
	smc #0
	/* A successful service transfers to A64 and does not return. */
	mov r0, #J2_STAGE_SMC_RETURNED
	mov r1, #0
	mov r2, #0
	mov r3, #0
	bl j2_ramoops_mark
.Lfailed_smc:
	wfe
	b .Lfailed_smc
