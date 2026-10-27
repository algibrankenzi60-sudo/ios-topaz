/* RAM-only kexec loader/control for the J2 Prime early-boot experiment.
 * Deliberately fixed to the audited image address and entry; never writes flash.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/reboot.h>
#include <sys/syscall.h>
#include <unistd.h>

#ifndef __NR_kexec_load
#define __NR_kexec_load 347
#endif
#ifndef __NR_reboot
#define __NR_reboot 88
#endif

#define KEXEC_ARCH_ARM (40UL << 16)
#define IMAGE_BASE 0x84000000UL
#define IMAGE_ENTRY 0x84000000UL
#define LOADER_BASE 0x84004000UL
#define PACKAGE_BASE 0x84005000UL
#define IMAGE_LIMIT 0x85000000UL
#define PAGE_SIZE_J2 4096UL
#define KEXEC_CMD 0x45584543UL

struct kexec_segment_j2 {
    const void *buf;
    size_t bufsz;
    const void *mem;
    size_t memsz;
};

static unsigned long align_page(unsigned long n) {
    return (n + PAGE_SIZE_J2 - 1) & ~(PAGE_SIZE_J2 - 1);
}

static int loaded(void) {
    FILE *f = fopen("/sys/kernel/kexec_loaded", "r");
    int state = -1;
    if (!f) return -1;
    if (fscanf(f, "%d", &state) != 1) state = -1;
    fclose(f);
    return state;
}

static uint32_t le32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint64_t le64(const uint8_t *p) {
    return (uint64_t)le32(p) | ((uint64_t)le32(p + 4) << 32);
}

static int load_image(const char *path) {
    FILE *f;
    long file_len;
    uint8_t *buf = NULL;
    void *aligned = NULL;
    struct kexec_segment_j2 seg;
    int rc = 1;

    if (loaded() != 0) {
        fprintf(stderr, "refusing: /sys/kernel/kexec_loaded is %d, expected 0\n", loaded());
        return 1;
    }
    f = fopen(path, "rb");
    if (!f) { perror("open image"); return 1; }
    if (fseek(f, 0, SEEK_END) || (file_len = ftell(f)) < 0 || fseek(f, 0, SEEK_SET)) {
        perror("size image"); fclose(f); return 1;
    }
    if ((unsigned long)file_len < 0x5000 || (unsigned long)file_len > IMAGE_LIMIT - IMAGE_BASE) {
        fprintf(stderr, "refusing: image size %ld outside audited bounds\n", file_len);
        fclose(f); return 1;
    }
    buf = calloc(1, align_page((unsigned long)file_len));
    if (!buf) { perror("calloc"); fclose(f); return 1; }
    if (fread(buf, 1, (size_t)file_len, f) != (size_t)file_len) {
        perror("read image"); fclose(f); goto out;
    }
    fclose(f);
    if (memcmp(buf + 4, "J2KEX001", 8) || le32(buf + 12) != IMAGE_BASE ||
        le32(buf + 16) != IMAGE_ENTRY || le32(buf + 20) != LOADER_BASE ||
        le32(buf + 24) != PACKAGE_BASE || le32(buf + 28) != IMAGE_LIMIT ||
        memcmp(buf + 0x5000, "J2PRIME\0", 8)) {
        fprintf(stderr, "refusing: image header, addresses, or embedded package do not match\n");
        goto out;
    }
    if (le64(buf + 0x5000 + 0x48) > (uint64_t)file_len - 0x5000) {
        fprintf(stderr, "refusing: embedded package length exceeds image\n");
        goto out;
    }
    if (posix_memalign(&aligned, PAGE_SIZE_J2, align_page((unsigned long)file_len))) {
        perror("posix_memalign"); goto out;
    }
    memcpy(aligned, buf, align_page((unsigned long)file_len));
    seg.buf = aligned;
    seg.bufsz = align_page((unsigned long)file_len);
    seg.mem = (const void *)IMAGE_BASE;
    seg.memsz = seg.bufsz;
    if (seg.memsz > IMAGE_LIMIT - IMAGE_BASE) {
        fprintf(stderr, "refusing: aligned kexec segment crosses audited source window\n");
        goto out;
    }
    if (syscall(__NR_kexec_load, IMAGE_ENTRY, 1UL, &seg, KEXEC_ARCH_ARM) < 0) {
        fprintf(stderr, "kexec_load failed: errno=%d (%s)\n", errno, strerror(errno));
        goto out;
    }
    printf("loaded RAM-only image at 0x%08lx, entry 0x%08lx, bytes %lu; loaded=%d\n",
           IMAGE_BASE, IMAGE_ENTRY, (unsigned long)file_len, loaded());
    rc = 0;
out:
    free(aligned);
    free(buf);
    return rc;
}

static int unload_image(void) {
    if (loaded() == 0) { puts("no kexec image loaded"); return 0; }
    if (syscall(__NR_kexec_load, 0UL, 0UL, NULL, KEXEC_ARCH_ARM) < 0) {
        fprintf(stderr, "kexec unload failed: errno=%d (%s)\n", errno, strerror(errno));
        return 1;
    }
    printf("unloaded; loaded=%d\n", loaded());
    return loaded() == 0 ? 0 : 1;
}

static int execute_image(void) {
    if (loaded() != 1) { fprintf(stderr, "refusing: no kexec image loaded\n"); return 1; }
    puts("syncing filesystems, then requesting the already-loaded RAM-only kexec image");
    sync();
    sleep(2);
    if (syscall(__NR_reboot, LINUX_REBOOT_MAGIC1, LINUX_REBOOT_MAGIC2,
                KEXEC_CMD, NULL) < 0) {
        fprintf(stderr, "kexec reboot failed: errno=%d (%s)\n", errno, strerror(errno));
        return 1;
    }
    return 0;
}

int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "status")) {
        printf("kexec_loaded=%d\n", loaded());
        return loaded() < 0;
    }
    if (argc == 2 && !strcmp(argv[1], "unload")) return unload_image();
    if (argc == 2 && !strcmp(argv[1], "execute")) return execute_image();
    if (argc == 3 && !strcmp(argv[1], "load")) return load_image(argv[2]);
    fprintf(stderr, "usage: %s status | load IMAGE | unload | execute\n", argv[0]);
    return 2;
}
