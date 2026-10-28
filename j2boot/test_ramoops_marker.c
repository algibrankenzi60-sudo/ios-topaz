/* Host-only test for the exact marker writer; never maps handset memory. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define RECORD_SIZE 0x1000U
#define HEADER_SIZE 12U
#define RECORD_COUNT 190U
#define BUFFER_SIG 0x43474244U

uint8_t j2_test_ramoops_dmesg[RECORD_SIZE * RECORD_COUNT];
#include "ramoops_marker.h"

static uint8_t *record(unsigned int slot)
{
	return j2_test_ramoops_dmesg + slot * RECORD_SIZE;
}

static void seed_record(unsigned int slot, const char *text)
{
	uint32_t length = (uint32_t)strlen(text);
	uint32_t *header = (uint32_t *)record(slot);
	memcpy(record(slot) + HEADER_SIZE, text, length);
	header[1] = 0;
	header[2] = length;
	header[0] = BUFFER_SIG;
}

/* Match the Samsung persistent_ram_post_init() bounds checks and pstore read. */
static const char *pstore_record(unsigned int slot, uint32_t *size)
{
	uint32_t *header = (uint32_t *)record(slot);
	if (header[0] != BUFFER_SIG || header[2] > RECORD_SIZE - HEADER_SIZE ||
	    header[1] > header[2] || header[2] == 0)
		return NULL;
	*size = header[2];
	return (const char *)record(slot) + HEADER_SIZE + header[1];
}

int main(void)
{
	seed_record(RECORD_COUNT - 1, "OLD-PSTORE-RECORD\n");
	uint8_t preserved[RECORD_SIZE];
	memcpy(preserved, record(RECORD_COUNT - 1), sizeof(preserved));

	j2_ramoops_mark(J2_STAGE_ARM32_ENTRY, 0, 0, 0);
	j2_ramoops_mark(J2_STAGE_ARM64_ENTRY, 4, 0x00c50838, 0);
	j2_ramoops_mark(J2_STAGE_LOADER_READY, 0, 0, 0);
	assert(!memcmp(record(RECORD_COUNT - 1), preserved, sizeof(preserved)));
	uint32_t imported_size = 0;
	const char *imported = pstore_record(188, &imported_size);
	assert(imported);
	char *imported_text = malloc(imported_size + 1);
	assert(imported_text);
	memcpy(imported_text, imported, imported_size);
	imported_text[imported_size] = '\0';
	const char expected_prefix[] = "J2KEX/1\nJ2KEX:ARM32_ENTRY\n";
	assert(!memcmp(imported_text, expected_prefix, sizeof(expected_prefix) - 1));
	assert(strstr(imported_text, "J2KEX:ARM64_ENTRY EL=0x00000004 SCTLR1=0x00c50838 SCTLR2=0x00000000\n"));
	assert(strstr(imported_text, "J2KEX:LOADER_READY\n"));
	assert(imported_size == strlen("J2KEX/1\nJ2KEX:ARM32_ENTRY\nJ2KEX:ARM64_ENTRY EL=0x00000004 SCTLR1=0x00c50838 SCTLR2=0x00000000\nJ2KEX:LOADER_READY\n"));
	/* The entire trace is one valid nonempty ramoops record for pstorefs. */
	unsigned int valid_marker_records = 0;
	for (unsigned int i = 0; i < RECORD_COUNT; ++i) {
		uint32_t size;
		const char *data = pstore_record(i, &size);
		(void)size;
		if (data && size >= 8 && !memcmp(data, "J2KEX/1\n", 8))
			++valid_marker_records;
	}
	assert(valid_marker_records == 1);
	free(imported_text);

	/* With no free record, the writer must leave every old record untouched. */
	memset(j2_test_ramoops_dmesg, 0, sizeof(j2_test_ramoops_dmesg));
	for (unsigned int i = 0; i < RECORD_COUNT; ++i) {
		seed_record(i, "OLD\n");
	}
	uint8_t *snapshot = malloc(sizeof(j2_test_ramoops_dmesg));
	assert(snapshot);
	memcpy(snapshot, j2_test_ramoops_dmesg, sizeof(j2_test_ramoops_dmesg));
	j2_ramoops_mark(J2_STAGE_XNU_CALL, 0, 0, 0);
	assert(!memcmp(snapshot, j2_test_ramoops_dmesg, sizeof(j2_test_ramoops_dmesg)));
	free(snapshot);
	puts("ramoops marker allocation/preservation checks passed");
	return 0;
}
