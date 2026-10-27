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

int main(void)
{
	seed_record(RECORD_COUNT - 1, "OLD-PSTORE-RECORD\n");
	uint8_t preserved[RECORD_SIZE];
	memcpy(preserved, record(RECORD_COUNT - 1), sizeof(preserved));

	j2_ramoops_mark(J2_STAGE_ARM32_ENTRY, 0, 0, 0);
	j2_ramoops_mark(J2_STAGE_ARM64_ENTRY, 4, 0x00c50838, 0);
	j2_ramoops_mark(J2_STAGE_LOADER_READY, 0, 0, 0);
	assert(!memcmp(record(RECORD_COUNT - 1), preserved, sizeof(preserved)));
	assert(!strcmp((char *)record(188) + HEADER_SIZE, "J2KEX:ARM32_ENTRY\n"));
	assert(!strcmp((char *)record(187) + HEADER_SIZE,
	               "J2KEX:ARM64_ENTRY EL=0x00000004 SCTLR1=0x00c50838 SCTLR2=0x00000000\n"));
	assert(!strcmp((char *)record(186) + HEADER_SIZE, "J2KEX:LOADER_READY\n"));

	/* With no free record, the writer must leave every old record untouched. */
	for (unsigned int i = 0; i < RECORD_COUNT; ++i) {
		if (i == 186 || i == 187 || i == 188 || i == 189)
			continue;
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
