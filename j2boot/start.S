/* AArch64 stage entry and XNU MMU handoff. Physical execution at 0x84004000. */
.section .text.start, "ax"
#include "ramoops_marker.h"
.global _start
.type _start, %function

_start:
	mrs	x19, CurrentEL
	mrs	x20, SCTLR_EL1
	mov	x21, xzr
	cmp	x19, #8
	b.eq	.Lfrom_el2
	cmp	x19, #4
	b.eq	.Lfrom_el1
	b	.Lunsupported_el

/* The Samsung kexec source reaches ARM32 with MMU/caches off. Flush any
 * state introduced by the MTK monitor before normalizing the A64 context. */
.Lfrom_el2:
	mrs	x21, SCTLR_EL2
	bl	.Lclean_all_dcache
	mrs	x0, SCTLR_EL2
	mov	x1, #0x1005             /* SCTLR.M | SCTLR.C | SCTLR.I */
	bic	x0, x0, x1
	msr	SCTLR_EL2, x0
		ldr	x0, =0x30100000          /* XNU ARM64 RES1 bits; MMU/cache off */
	msr	SCTLR_EL1, x0
	mov	x0, #0x80000000          /* HCR_EL2.RW; stage-2 and traps off */
	msr	HCR_EL2, x0
	msr	CPTR_EL2, xzr
	mov	x0, #3                   /* permit EL1 physical/virtual timer access */
	msr	CNTHCTL_EL2, x0
	msr	CNTVOFF_EL2, xzr
	adr	x0, .Lenter_el1
	msr	ELR_EL2, x0
	mov	x0, #0x3c5               /* EL1h, A/I/F/D masked */
	msr	SPSR_EL2, x0
	dsb	sy
	isb
	eret

.Lfrom_el1:
	bl	.Lclean_all_dcache
		ldr	x0, =0x30100000          /* XNU RES1 bits; MMU/cache off */
	msr	SCTLR_EL1, x0
	dsb	sy
	isb

.Lenter_el1:
	msr	DAIFSet, #0xf
	msr	SPSel, #1
	ldr	x0, =0x80f00000
	mov	sp, x0
	tlbi	vmalle1
	dsb	sy
	ic	iallu
	dsb	sy
	isb
	mov	w0, #J2_STAGE_ARM64_ENTRY
	mov	w1, w19                  /* actual CurrentEL on SMC return */
	mov	w2, w20                  /* original SCTLR_EL1 */
	mov	w3, w21                  /* original SCTLR_EL2, or zero at EL1 */
	bl	j2_ramoops_mark
	bl	j2_loader_main
.Lhang:
	wfe
	b	.Lhang

/* Clean+invalidate every data/unified cache by set/way before disabling C. */
.Lclean_all_dcache:
	mrs	x12, CSSELR_EL1
	mrs	x0, CLIDR_EL1
	mov	x8, #0
.Lcache_level:
	cmp	x8, #7
	b.hi	.Lcache_done
	lsl	x9, x8, #1
	lsr	x10, x0, x9
	and	x10, x10, #7
	cmp	x10, #2                  /* no data cache at this level */
	b.lo	.Lcache_next
	msr	CSSELR_EL1, x9
	isb
	mrs	x1, CCSIDR_EL1
	and	x2, x1, #7
	add	x2, x2, #4               /* line shift */
	ubfx	x3, x1, #13, #15
	add	x3, x3, #1               /* set count */
	ubfx	x4, x1, #3, #10
	add	x4, x4, #1               /* way count */
	sub	x5, x4, #1
	clz	w5, w5                   /* way field is in operand bits [31:32-log2(ways)] */
	sub	x3, x3, #1
.Lcache_set:
	mov	x6, x4
	sub	x6, x6, #1
.Lcache_way:
	lsl	x7, x6, x5
	lsl	x11, x3, x2
	orr	x7, x7, x11
	orr	x7, x7, x9
	dc	cisw, x7
	subs	x6, x6, #1
	b.ge	.Lcache_way
	subs	x3, x3, #1
	b.ge	.Lcache_set
.Lcache_next:
	add	x8, x8, #1
	b	.Lcache_level
.Lcache_done:
	msr	CSSELR_EL1, x12
	dsb	sy
	ret

.Lunsupported_el:
	/* No memory access is safe before an EL3 contract is known. */
	wfe
	b	.Lunsupported_el
.size _start, .-_start

/* x0=kernel entry VA, x1=boot_args PA, x2=TTBR0 PA, x3=TTBR1 PA. */
.global j2_enter_xnu
.type j2_enter_xnu, %function
j2_enter_xnu:
	mov	x9, x0
	mov	x10, x1
	mov	x11, x2
	mov	x12, x3
	ldr	x0, =0x22a519a519       /* XNU 4K, 39-bit VA, 40-bit PA TCR */
	msr	TCR_EL1, x0
	mov	x0, #0xff
	msr	MAIR_EL1, x0
	msr	TTBR0_EL1, x11
	msr	TTBR1_EL1, x12
	dsb	sy
	tlbi	vmalle1
	dsb	sy
	isb
	ic	iallu
	dsb	sy
	isb
	ldr	x0, =0x3454593d          /* XNU 8796 SCTLR_EL1_DEFAULT (A53) */
	msr	SCTLR_EL1, x0
	dsb	sy
	isb
	mov	x0, x10                  /* XNU boot protocol: x0 = boot_args PA */
	br	x9                      /* enter XNU at its mapped high VA */
.size j2_enter_xnu, .-j2_enter_xnu
