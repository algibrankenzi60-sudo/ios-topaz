/*
 * Reboot-persistent stage stamps in unused Linux ramoops dmesg records.
 * Geometry is taken from the attached handset's read-only ramoops sysfs
 * parameters: 0x43f10000/0xe0000, record=0x1000, console=0x10000,
 * ftrace=0x1000, pmsg=0x1000, ECC=0.  The kernel reserves this entire range.
 */
#include <stdint.h>
#include "ramoops_marker.h"

#define RAMOOPS_BASE       0x43f10000UL
#define RAMOOPS_RECORD     0x1000UL
#define RAMOOPS_RECORDS    190U
#define RAM_BUFFER_HEADER  12U
#define RAM_BUFFER_BYTES   (RAMOOPS_RECORD - RAM_BUFFER_HEADER)
#define RAM_BUFFER_SIG     0x43474244U /* PERSISTENT_RAM_SIG, sig argument 0 */
#define J2_MARKER_PREFIX   "J2KEX/1\n"
#define J2_MARKER_PREFIX_LEN (sizeof(J2_MARKER_PREFIX) - 1)

#ifdef J2_RAMOOPS_TEST
extern uint8_t j2_test_ramoops_dmesg[];
#define RAMOOPS_DMESG_BASE ((uintptr_t)j2_test_ramoops_dmesg)
#else
#define RAMOOPS_DMESG_BASE ((uintptr_t)RAMOOPS_BASE)
#endif

static void append(char *dst, uint32_t *offset, const char *src)
{
	while (*src)
		dst[(*offset)++] = *src++;
}

static void append_hex32(char *dst, uint32_t *offset, uint32_t value)
{
	static const char hex[] = "0123456789abcdef";
	for (int shift = 28; shift >= 0; shift -= 4)
		dst[(*offset)++] = hex[(value >> shift) & 0xf];
}

static const char *stage_text(uint32_t stage, uint32_t info0,
			      uint32_t info1, uint32_t info2,
			      char *buffer, uint32_t *length)
{
	switch (stage) {
	case J2_STAGE_ARM32_ENTRY:
		*length = sizeof("J2KEX:ARM32_ENTRY\n") - 1;
		return "J2KEX:ARM32_ENTRY\n";
	case J2_STAGE_ARM64_ENTRY:
	{
		uint32_t offset = 0;
		append(buffer, &offset, "J2KEX:ARM64_ENTRY EL=0x");
		append_hex32(buffer, &offset, info0);
		append(buffer, &offset, " SCTLR1=0x");
		append_hex32(buffer, &offset, info1);
		append(buffer, &offset, " SCTLR2=0x");
		append_hex32(buffer, &offset, info2);
		buffer[offset] = '\n';
		*length = offset + 1;
		return buffer;
	}
	case J2_STAGE_LOADER_READY:
		*length = sizeof("J2KEX:LOADER_READY\n") - 1;
		return "J2KEX:LOADER_READY\n";
	case J2_STAGE_XNU_CALL:
		*length = sizeof("J2KEX:XNU_CALL\n") - 1;
		return "J2KEX:XNU_CALL\n";
	case J2_STAGE_LOADER_REJECT:
	{
		uint32_t offset = 0;
		append(buffer, &offset, "J2KEX:LOADER_REJECT REASON=0x");
		append_hex32(buffer, &offset, info0);
		buffer[offset] = '\n';
		*length = offset + 1;
		return buffer;
	}
	case J2_STAGE_SMC_RETURNED:
		*length = sizeof("J2KEX:SMC_RETURNED\n") - 1;
		return "J2KEX:SMC_RETURNED\n";
	default:
		*length = 0;
		return 0;
	}
}

static void persist_range(uintptr_t start, uintptr_t end)
{
#ifdef J2_RAMOOPS_TEST
	(void)start;
	(void)end;
	__atomic_thread_fence(__ATOMIC_SEQ_CST);
#elif defined(__aarch64__)
	uintptr_t p = start & ~(uintptr_t)63;
	for (; p < end; p += 64)
		__asm__ volatile("dc cvac, %0" :: "r"(p) : "memory");
	__asm__ volatile("dsb sy" ::: "memory");
#else
	uintptr_t p = start & ~(uintptr_t)31;
	for (; p < end; p += 32)
		__asm__ volatile("mcr p15, 0, %0, c7, c10, 1" :: "r"(p) : "memory");
	__asm__ volatile("dsb sy" ::: "memory");
#endif
}

static int record_is_valid_and_occupied(volatile uint32_t *header)
{
	uint32_t sig = header[0];
	uint32_t start = header[1];
	uint32_t size = header[2];

	/* Match persistent_ram_post_init(): valid nonempty records are preserved. */
	return sig == RAM_BUFFER_SIG && size != 0 &&
	       size <= RAM_BUFFER_BYTES && start <= size;
}

static int is_our_record(uintptr_t address, volatile uint32_t *header)
{
	uint32_t size = header[2];
	volatile uint8_t *data = (volatile uint8_t *)(address + RAM_BUFFER_HEADER);
	if (header[0] != RAM_BUFFER_SIG || size < J2_MARKER_PREFIX_LEN ||
	    size > RAM_BUFFER_BYTES || header[1] > size)
		return 0;
	for (uint32_t i = 0; i < J2_MARKER_PREFIX_LEN; ++i)
		if (data[i] != (uint8_t)J2_MARKER_PREFIX[i])
			return 0;
	return 1;
}

static uint32_t marker_line(uint32_t stage, uint32_t info0,
			    uint32_t info1, uint32_t info2,
			    char *buffer)
{
	uint32_t length;
	char formatted[96];
	const char *text = stage_text(stage, info0, info1, info2,
				      formatted, &length);
	if (!text || !length || length > sizeof(formatted))
		return 0;
	for (uint32_t i = 0; i < length; ++i)
		buffer[i] = text[i];
	return length;
}

void j2_ramoops_mark(uint32_t stage, uint32_t info0,
		     uint32_t info1, uint32_t info2)
{
	char line[96];
	uint32_t line_length = marker_line(stage, info0, info1, info2, line);
	if (!line_length || J2_MARKER_PREFIX_LEN + line_length > RAM_BUFFER_BYTES)
		return;

	/* Reuse our own single record so pstore imports one file for all stages. */
	for (int slot = (int)RAMOOPS_RECORDS - 1; slot >= 0; --slot) {
		uintptr_t address = RAMOOPS_DMESG_BASE +
		                    (uintptr_t)slot * RAMOOPS_RECORD;
		volatile uint32_t *header = (volatile uint32_t *)address;
		if (!is_our_record(address, header))
			continue;
		uint32_t old_size = header[2];
		if (old_size + line_length > RAM_BUFFER_BYTES)
			return;
		volatile uint8_t *data = (volatile uint8_t *)(address + RAM_BUFFER_HEADER);
		for (uint32_t i = 0; i < line_length; ++i)
			data[old_size + i] = (uint8_t)line[i];
		persist_range(address + RAM_BUFFER_HEADER + old_size,
		              address + RAM_BUFFER_HEADER + old_size + line_length);
		__atomic_thread_fence(__ATOMIC_RELEASE);
		header[2] = old_size + line_length;
		persist_range(address + 8, address + 12);
		return;
	}

	/* Pick a free dmesg slot from the end; never overwrite a valid record. */
	for (int slot = (int)RAMOOPS_RECORDS - 1; slot >= 0; --slot) {
		uintptr_t address = RAMOOPS_DMESG_BASE +
		                    (uintptr_t)slot * RAMOOPS_RECORD;
		volatile uint32_t *header = (volatile uint32_t *)address;
		if (record_is_valid_and_occupied(header))
			continue;

		volatile uint8_t *data = (volatile uint8_t *)(address + RAM_BUFFER_HEADER);
		for (uint32_t i = 0; i < J2_MARKER_PREFIX_LEN; ++i)
			data[i] = (uint8_t)J2_MARKER_PREFIX[i];
		for (uint32_t i = 0; i < line_length; ++i)
			data[J2_MARKER_PREFIX_LEN + i] = (uint8_t)line[i];
		/* Publish the record fields first and the signature last. */
		header[1] = 0;
		header[2] = J2_MARKER_PREFIX_LEN + line_length;
		persist_range(address + 4,
		              address + RAM_BUFFER_HEADER + J2_MARKER_PREFIX_LEN + line_length);
		header[0] = RAM_BUFFER_SIG;
		persist_range(address, address + sizeof(uint32_t));
		return;
	}
}
