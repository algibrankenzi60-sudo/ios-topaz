/* Freestanding second stage for the verified MT6737 AArch32->AArch64 shim.
 * Link at 0x40008000; package starts at the following 4 KiB boundary. */
#include <stdint.h>

#define RAM_BASE 0x44000000ULL
#define RAM_SIZE 0x04000000ULL
#define FB_BASE  0x7f900000ULL
#define FB_BYTES 0x001fe000ULL
#define FB_STRIDE 2176ULL
#define PAGE 4096ULL
#define MAX_SEGS 32
#define BOOT_LINE 608

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
extern uint8_t _payload[];

static int eq8(const char *a, const char *b) { for (int i=0;i<8;i++) if(a[i]!=b[i]) return 0; return 1; }
static int add_ok(uint64_t a,uint64_t b,uint64_t *r) { *r=a+b; return *r>=a; }
static void bytes_copy(uint8_t *d,const uint8_t *s,uint64_t n) { while(n--) *d++=*s++; }
static void bytes_zero(uint8_t *d,uint64_t n) { while(n--) *d++=0; }
static void screen(uint32_t c) {
    volatile uint32_t *p=(volatile uint32_t *)FB_BASE;
    for (uint64_t y=0;y<960;y++) for(uint64_t x=0;x<540;x++) p[y*(FB_STRIDE/4)+x]=c;
}
static void halt(uint32_t color) { screen(color); for (;;) __asm__ volatile("wfe"); }

void j2_loader_main(void) {
    const struct payload *p=(const struct payload *)_payload;
    uint64_t payload_end, adt_end;
    if (!eq8(p->magic,"J2PRIME\0") || p->version!=1 || !p->nsegs || p->nsegs>MAX_SEGS ||
        p->phys!=RAM_BASE || p->mem_size!=RAM_SIZE || p->total_size<sizeof(uint32_t)*2 ||
        !add_ok((uint64_t)_payload,p->total_size,&payload_end) ||
        payload_end>0x41000000ULL ||
        p->adt_off<0x2a8ULL+(uint64_t)p->nsegs*sizeof(struct seg) ||
        !add_ok(p->adt_off,p->adt_size,&adt_end) || adt_end>p->total_size)
        halt(0xffff0000U);
    uint64_t bias=p->phys-p->virt, max_end=0, entry_pa=0;
    for (uint32_t i=0;i<p->nsegs;i++) {
        const struct seg *s=&p->segs[i]; uint64_t file_end=0, dst=0, dst_end=0;
        if (!s->vs || s->fs>s->vs || !add_ok(s->off,s->fs,&file_end) || file_end>p->total_size ||
            s->off<0x2a8ULL+(uint64_t)p->nsegs*sizeof(struct seg) || file_end>p->adt_off ||
            !add_ok(s->va,bias,&dst) || !add_ok(dst,s->vs,&dst_end) || dst<RAM_BASE || dst_end>RAM_BASE+RAM_SIZE)
            halt(0xffff0000U);
        if ((uint64_t)_payload < dst_end && dst < payload_end) halt(0xffff0000U);
        for (uint32_t j=0;j<i;j++) {
            const struct seg *q=&p->segs[j]; uint64_t qlo=q->va+bias, qhi=qlo+q->vs;
            if (dst<qhi && qlo<dst_end) halt(0xffff0000U);
        }
        if (s->va<=p->entry && p->entry< s->va+s->vs) entry_pa=p->entry+bias;
        if (dst_end>max_end) max_end=dst_end;
    }
    if (!entry_pa || max_end>RAM_BASE+RAM_SIZE || (p->adt_off & 7)) halt(0xffff0000U);
    /* Copy segment file bytes and zero BSS. */
    for (uint32_t i=0;i<p->nsegs;i++) {
        const struct seg *s=&p->segs[i]; uint8_t *dst=(uint8_t *)(s->va+bias);
        bytes_copy(dst,_payload+s->off,s->fs);
        bytes_zero(dst+s->fs,s->vs-s->fs);
    }
    uint64_t adt_pa=(max_end+7)&~7ULL, ba_pa=(adt_pa+p->adt_size+PAGE-1)&~(PAGE-1);
    uint64_t ba_end=ba_pa+PAGE;
    if (ba_end>RAM_BASE+RAM_SIZE || adt_pa<max_end || (adt_pa< payload_end && (uint64_t)_payload<adt_pa+p->adt_size)) halt(0xffff0000U);
    bytes_copy((uint8_t *)adt_pa,_payload+p->adt_off,p->adt_size);
    bytes_zero((uint8_t *)ba_pa,PAGE);
    struct boot_args *ba=(struct boot_args *)ba_pa;
    ba->rev=2; ba->ver=2; ba->virt=p->virt; ba->phys=p->phys; ba->memsize=p->mem_size;
    ba->top=ba_end; ba->video.base=FB_BASE; ba->video.display=1; ba->video.rowbytes=FB_STRIDE;
    ba->video.width=540; ba->video.height=960; ba->video.depth=32;
    ba->dt=adt_pa-bias; ba->dtlen=(uint32_t)p->adt_size; ba->actual=p->mem_size;
    screen(0xff008000U);
    __asm__ volatile("dsb sy; ic iallu; dsb sy; isb" ::: "memory");
    ((void (*)(uint64_t))entry_pa)(ba_pa);
    halt(0xffff0000U);
}
