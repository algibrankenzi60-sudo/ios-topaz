/* Append early XNU checkpoints to an unused Samsung ramoops dmesg record. */
#include "j2prime_ramoops.h"

#define RECORD_BYTES  0x1000u
#define RECORD_COUNT  190u
#define HEADER_BYTES  12u
#define DATA_BYTES    (RECORD_BYTES - HEADER_BYTES)
#define BUFFER_SIG    0x43474244u /* persistent_ram: PERSISTENT_RAM_SIG ^ 0 */
#define PREFIX        "J2XNU/1\n"
#define PREFIX_BYTES  (sizeof(PREFIX) - 1u)
#define MAX_LINE      112u

static void
clean_persistent(uintptr_t start, uintptr_t end)
{
#if defined(__aarch64__)
	uint64_t ctr;
	__asm__ volatile("mrs %0, ctr_el0" : "=r"(ctr));
	uintptr_t line = (uintptr_t)4 << ((ctr >> 16) & 0xf);
	for (uintptr_t p = start & ~(line - 1); p < end; p += line) {
		__asm__ volatile("dc cvac, %0" :: "r"(p) : "memory");
	}
	__asm__ volatile("dsb sy" ::: "memory");
#else
	(void)start;
	(void)end;
	__atomic_thread_fence(__ATOMIC_SEQ_CST);
#endif
}

static uint32_t
format_line(uint8_t *out, uint32_t stage, const char *label)
{
	uint32_t n = 0;
	out[n++] = 'J'; out[n++] = '2'; out[n++] = 'X';
	out[n++] = 'N'; out[n++] = 'U'; out[n++] = ':';
	if (stage >= 10) {
		out[n++] = (uint8_t)('0' + (stage / 10) % 10);
	}
	out[n++] = (uint8_t)('0' + stage % 10);
	out[n++] = ':';
	while (*label && n < MAX_LINE - 2u) {
		char c = *label++;
		out[n++] = (c >= 32 && c <= 126) ? (uint8_t)c : (uint8_t)'?';
	}
	out[n++] = '\n';
	return n;
}

static int
valid_nonempty(volatile uint32_t *header)
{
	uint32_t size = header[2];
	return header[0] == BUFFER_SIG && size != 0 &&
	       size <= DATA_BYTES && header[1] <= size;
}

static int
is_ours(uintptr_t address, volatile uint32_t *header)
{
	volatile uint8_t *data = (volatile uint8_t *)(address + HEADER_BYTES);
	if (header[0] != BUFFER_SIG || header[2] < PREFIX_BYTES ||
	    header[2] > DATA_BYTES || header[1] > header[2]) {
		return 0;
	}
	for (uint32_t i = 0; i < PREFIX_BYTES; ++i) {
		if (data[i] != (uint8_t)PREFIX[i]) {
			return 0;
		}
	}
	return 1;
}

void
j2prime_ramoops_mark(volatile void *mapped_base, uint32_t stage,
		     const char *label)
{
	uint8_t line[MAX_LINE];
	uint32_t line_size = format_line(line, stage, label);
	uintptr_t base = (uintptr_t)mapped_base;
	if (!mapped_base || PREFIX_BYTES + line_size > DATA_BYTES) {
		return;
	}

	/* Reuse our owned record so pstore imports one self-contained trace. */
	for (int slot = (int)RECORD_COUNT - 1; slot >= 0; --slot) {
		uintptr_t address = base + (uintptr_t)slot * RECORD_BYTES;
		volatile uint32_t *header = (volatile uint32_t *)address;
		if (!is_ours(address, header)) {
			continue;
		}
		uint32_t old_size = header[2];
		if (old_size + line_size > DATA_BYTES) {
			return;
		}
		volatile uint8_t *data = (volatile uint8_t *)(address + HEADER_BYTES);
		for (uint32_t i = 0; i < line_size; ++i) {
			data[old_size + i] = line[i];
		}
		clean_persistent(address + HEADER_BYTES + old_size,
				 address + HEADER_BYTES + old_size + line_size);
		__atomic_thread_fence(__ATOMIC_RELEASE);
		header[2] = old_size + line_size;
		clean_persistent(address + 8, address + 12);
		return;
	}

	/* Preserve every valid, nonempty record owned by Android or recovery. */
	for (int slot = (int)RECORD_COUNT - 1; slot >= 0; --slot) {
		uintptr_t address = base + (uintptr_t)slot * RECORD_BYTES;
		volatile uint32_t *header = (volatile uint32_t *)address;
		if (valid_nonempty(header)) {
			continue;
		}
		volatile uint8_t *data = (volatile uint8_t *)(address + HEADER_BYTES);
		for (uint32_t i = 0; i < PREFIX_BYTES; ++i) {
			data[i] = (uint8_t)PREFIX[i];
		}
		for (uint32_t i = 0; i < line_size; ++i) {
			data[PREFIX_BYTES + i] = line[i];
		}
		header[1] = 0;
		header[2] = PREFIX_BYTES + line_size;
		clean_persistent(address + 4,
				 address + HEADER_BYTES + PREFIX_BYTES + line_size);
		__atomic_thread_fence(__ATOMIC_RELEASE);
		header[0] = BUFFER_SIG;
		clean_persistent(address, address + 4);
		return;
	}
}
