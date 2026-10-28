#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "j2prime_ramoops.h"

#define RECORD_BYTES 0x1000u
#define RECORD_COUNT 190u
#define HEADER_BYTES 12u
#define DATA_BYTES (RECORD_BYTES - HEADER_BYTES)
#define BUFFER_SIG 0x43474244u

static uint8_t region[RECORD_BYTES * RECORD_COUNT];
static uint8_t full_region[RECORD_BYTES * RECORD_COUNT];

static uint32_t *header_at(unsigned int slot)
{
	return (uint32_t *)(region + slot * RECORD_BYTES);
}

static const char *data_at(unsigned int slot)
{
	return (const char *)(region + slot * RECORD_BYTES + HEADER_BYTES);
}

static int count_records(void)
{
	int count = 0;
	for (unsigned int i = 0; i < RECORD_COUNT; ++i) {
		uint32_t *h = header_at(i);
		if (h[0] == BUFFER_SIG && h[2] && h[2] <= DATA_BYTES && h[1] <= h[2]) {
			++count;
		}
	}
	return count;
}

int main(void)
{
	memset(region, 0, sizeof(region));
	j2prime_ramoops_mark(region, 21, "vm-init-enter");
	j2prime_ramoops_mark(region, 22, "ram-range-ok");
	assert(count_records() == 1);
	assert(header_at(RECORD_COUNT - 1)[0] == BUFFER_SIG);
	assert(strstr(data_at(RECORD_COUNT - 1), "J2XNU/1\nJ2XNU:21:vm-init-enter\n"));
	assert(strstr(data_at(RECORD_COUNT - 1), "J2XNU:22:ram-range-ok\n"));

	/* An occupied foreign record must remain byte-for-byte unchanged. */
	uint8_t *foreign = region + (RECORD_COUNT - 2) * RECORD_BYTES;
	uint32_t *fh = (uint32_t *)foreign;
	fh[0] = BUFFER_SIG; fh[1] = 0; fh[2] = 5;
	memcpy(foreign + HEADER_BYTES, "prior", 5);
	uint8_t saved[RECORD_BYTES];
	memcpy(saved, foreign, sizeof(saved));
	j2prime_ramoops_mark(region, 23, "after-foreign");
	assert(!memcmp(saved, foreign, sizeof(saved)));
	assert(strstr(data_at(RECORD_COUNT - 1), "J2XNU:23:after-foreign\n"));

	/* With every slot occupied by valid foreign records, write nothing. */
	for (unsigned int i = 0; i < RECORD_COUNT; ++i) {
		uint32_t *h = (uint32_t *)(full_region + i * RECORD_BYTES);
		h[0] = BUFFER_SIG; h[1] = 0; h[2] = 1;
		full_region[i * RECORD_BYTES + HEADER_BYTES] = 'x';
	}
	uint8_t *snapshot = malloc(sizeof(full_region));
	assert(snapshot);
	memcpy(snapshot, full_region, sizeof(full_region));
	j2prime_ramoops_mark(full_region, 24, "no-space");
	assert(!memcmp(snapshot, full_region, sizeof(full_region)));
	free(snapshot);
	puts("J2 XNU ramoops checkpoint format and preservation tests passed");
	return 0;
}
