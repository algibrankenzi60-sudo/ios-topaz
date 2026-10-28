/* Freestanding second stage for J2 Prime; physically linked at 0x84004000. */
#include <stdint.h>
#include "boot_mmu.h"
#include "ramoops_marker.h"

#define RAM_BASE 0x80000000ULL
#define RAM_SIZE 0x04000000ULL
#define FB_BASE  0x7f900000ULL
#define FB_BYTES 0x001fe000ULL
#define FB_STRIDE 2176ULL
#define PAGE 4096ULL
#define IDENTITY_END 0x85000000ULL
#define LOADER_MAP_BASE 0x40000000ULL
#define LOADER_MAP_END  0x42000000ULL
#define MAX_SEGS 32
#define BOOT_LINE 608
#ifndef J2_DIAGNOSTIC_HALT
#define J2_DIAGNOSTIC_HALT 0
#endif
#ifndef J2_PAYLOAD_BASE
#define J2_PAYLOAD_BASE 0x84006000ULL
#endif
#ifndef J2_PAYLOAD_LIMIT
#define J2_PAYLOAD_LIMIT 0x85000000ULL
#endif

struct seg { uint64_t va, vs, off, fs; };
struct payload {
    char magic[8]; uint32_t version, nsegs;
    uint64_t virt, entry, adt_off, adt_size, kernel_end, phys, mem_size;
    uint64_t total_size;
    uint8_t reserved[0x2a8 - 0x50];
    struct seg segs[MAX_SEGS];
};
struct video { uint64_t base, display, rowbytes, width, height, depth; };
struct boot_args {
    uint16_t rev, ver; uint64_t virt, phys, memsize, top;
    struct video video; uint32_t machine; uint64_t dt; uint32_t dtlen;
    char cmdline[BOOT_LINE]; uint64_t flags, actual;
};
_Static_assert(__builtin_offsetof(struct payload, segs) == 0x2a8, "payload header layout");
_Static_assert(__builtin_offsetof(struct boot_args, video) == 40, "boot_args video offset");
_Static_assert(__builtin_offsetof(struct boot_args, cmdline) == 108, "boot_args command line offset");
_Static_assert(sizeof(struct boot_args) == 736, "boot_args v2 layout");
extern uint8_t _payload[];
extern void j2_enter_xnu(uint64_t entry_va, uint64_t boot_args_pa,
			 uint64_t ttbr0_pa, uint64_t ttbr1_pa) __attribute__((noreturn));

static int eq8(const char *a, const char *b) { for (int i=0;i<8;i++) if(a[i]!=b[i]) return 0; return 1; }
static int add_ok(uint64_t a,uint64_t b,uint64_t *r) { *r=a+b; return *r>=a; }
static int va_to_pa(uint64_t va,uint64_t virt,uint64_t phys,uint64_t *pa) {
    return va>=virt && add_ok(phys,va-virt,pa);
}
static int pa_to_va(uint64_t pa,uint64_t phys,uint64_t virt,uint64_t *va) {
    return pa>=phys && add_ok(virt,pa-phys,va);
}
static void bytes_copy(uint8_t *d,const uint8_t *s,uint64_t n) { while(n--) *d++=*s++; }
static void bytes_zero(uint8_t *d,uint64_t n) { while(n--) *d++=0; }
static void clean_invalidate_dcache(uint64_t addr,uint64_t len) {
    uint64_t ctr; __asm__ volatile("mrs %0, ctr_el0" : "=r"(ctr));
    uint64_t line=4ULL << ((ctr >> 16) & 0xf), end=addr+len;
    for (uint64_t p=addr & ~(line-1); p<end; p+=line)
        __asm__ volatile("dc civac, %0" :: "r"(p) : "memory");
    __asm__ volatile("dsb sy" ::: "memory");
}
static void halt(uint32_t reason) {
    j2_ramoops_mark(J2_STAGE_LOADER_REJECT, reason, 0, 0);
    for (;;) __asm__ volatile("wfe");
}

void j2_loader_main(void) {
    const struct payload *p=(const struct payload *)_payload;
    uint64_t payload_end, adt_end;
    if (!eq8(p->magic,"J2PRIME\0") || p->version!=1 || !p->nsegs || p->nsegs>MAX_SEGS ||
        p->phys!=RAM_BASE || p->mem_size!=RAM_SIZE || p->total_size<sizeof(uint32_t)*2 ||
        !add_ok((uint64_t)_payload,p->total_size,&payload_end) ||
        (uint64_t)_payload<J2_PAYLOAD_BASE || payload_end>J2_PAYLOAD_LIMIT ||
        p->adt_off<0x2a8ULL+(uint64_t)p->nsegs*sizeof(struct seg) ||
        !add_ok(p->adt_off,p->adt_size,&adt_end) || adt_end>p->total_size)
        halt(0xffff0000U);
    uint64_t max_end=0, entry_pa=0;
    for (uint32_t i=0;i<p->nsegs;i++) {
        const struct seg *s=&p->segs[i]; uint64_t file_end=0, va_end=0, dst=0, dst_end=0;
        if (!s->vs || s->fs>s->vs || !add_ok(s->off,s->fs,&file_end) || file_end>p->total_size ||
            s->off<0x2a8ULL+(uint64_t)p->nsegs*sizeof(struct seg) || file_end>p->adt_off ||
            !add_ok(s->va,s->vs,&va_end) || !va_to_pa(s->va,p->virt,p->phys,&dst) ||
            !add_ok(dst,s->vs,&dst_end) || dst<RAM_BASE || dst_end>RAM_BASE+RAM_SIZE)
            halt(0xffff0000U);
        if ((uint64_t)_payload < dst_end && dst < payload_end) halt(0xffff0000U);
        for (uint32_t j=0;j<i;j++) {
            const struct seg *q=&p->segs[j]; uint64_t qlo=0, qhi=0;
            if (!va_to_pa(q->va,p->virt,p->phys,&qlo) || !add_ok(qlo,q->vs,&qhi)) halt(0xffff0000U);
            if (dst<qhi && qlo<dst_end) halt(0xffff0000U);
        }
        if (s->va<=p->entry && p->entry<va_end && !va_to_pa(p->entry,p->virt,p->phys,&entry_pa)) halt(0xffff0000U);
        if (dst_end>max_end) max_end=dst_end;
    }
    uint64_t header_kernel_end=0;
    if (!add_ok(max_end,PAGE-1,&max_end)) halt(0xffff0000U);
    max_end &= ~(PAGE-1);
    if (!entry_pa || max_end>RAM_BASE+RAM_SIZE || (p->adt_off & 7) ||
        !va_to_pa(p->kernel_end,p->virt,p->phys,&header_kernel_end) || header_kernel_end!=max_end)
        halt(0xffff0000U);
    /* Copy segment file bytes and zero BSS. */
    for (uint32_t i=0;i<p->nsegs;i++) {
        const struct seg *s=&p->segs[i]; uint64_t dst_pa=0;
        if (!va_to_pa(s->va,p->virt,p->phys,&dst_pa)) halt(0xffff0000U);
        uint8_t *dst=(uint8_t *)dst_pa;
        bytes_copy(dst,_payload+s->off,s->fs);
        bytes_zero(dst+s->fs,s->vs-s->fs);
        clean_invalidate_dcache(dst_pa,s->vs);
    }
    uint64_t adt_pa=max_end, adt_end_pa=0, ba_pa=0;
    if (!add_ok(adt_pa,p->adt_size,&adt_end_pa) || !add_ok(adt_end_pa,PAGE-1,&ba_pa)) halt(0xffff0000U);
    ba_pa &= ~(PAGE-1);
    uint64_t ba_end=ba_pa+PAGE;
    uint64_t tables_pa=ba_end, tables_end=tables_pa+J2_TABLE_BYTES;
    if (ba_end>RAM_BASE+RAM_SIZE || tables_end<tables_pa ||
        tables_end>RAM_BASE+RAM_SIZE || adt_pa<max_end ||
        (adt_pa<payload_end && (uint64_t)_payload<adt_end_pa) ||
        (ba_pa<payload_end && (uint64_t)_payload<ba_end) ||
        (ba_pa<adt_end_pa && adt_pa<ba_end) ||
        (tables_pa<adt_end_pa && adt_pa<tables_end) ||
        (tables_pa<payload_end && (uint64_t)_payload<tables_end)) halt(0x1001U);
    bytes_copy((uint8_t *)adt_pa,_payload+p->adt_off,p->adt_size);
    clean_invalidate_dcache(adt_pa,p->adt_size);
    bytes_zero((uint8_t *)ba_pa,PAGE);
    struct boot_args *ba=(struct boot_args *)ba_pa;
    ba->rev=2; ba->ver=2; ba->virt=p->virt; ba->phys=p->phys; ba->memsize=p->mem_size;
    ba->top=tables_end; ba->video.base=FB_BASE; ba->video.display=1; ba->video.rowbytes=FB_STRIDE;
    ba->video.width=540; ba->video.height=960; ba->video.depth=32;
    if (!pa_to_va(adt_pa,p->phys,p->virt,&ba->dt)) halt(0xffff0000U);
    ba->dtlen=(uint32_t)p->adt_size; ba->actual=p->mem_size;
    const char cmdline[]="debug=0xc cpus=1 keepsyms=1";
    for (uint32_t i=0;i<sizeof(cmdline);i++) ba->cmdline[i]=cmdline[i];
    clean_invalidate_dcache(ba_pa,PAGE);
    if (!j2_build_boot_tables((volatile uint64_t *)tables_pa, tables_pa,
                              p->virt, p->phys, p->mem_size, IDENTITY_END,
                              LOADER_MAP_BASE, LOADER_MAP_END))
        halt(0x1002U);
    clean_invalidate_dcache(tables_pa,J2_TABLE_BYTES);
    j2_ramoops_mark(J2_STAGE_LOADER_READY, 0, 0, 0);
#if J2_DIAGNOSTIC_HALT
    for (;;) __asm__ volatile("wfe");
#endif
    j2_ramoops_mark(J2_STAGE_XNU_CALL, 0, 0, 0);
    j2_enter_xnu(p->entry, ba_pa, tables_pa, tables_pa + 2 * PAGE);
}
