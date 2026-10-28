#include "lz4_block.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>

static uint8_t *read_file(const char *path, size_t *size)
{
	FILE *f = fopen(path, "rb");
	if (!f || fseek(f, 0, SEEK_END)) return NULL;
	long n = ftell(f);
	if (n < 0 || fseek(f, 0, SEEK_SET)) return NULL;
	uint8_t *p = malloc((size_t)n ? (size_t)n : 1);
	if (!p || fread(p, 1, (size_t)n, f) != (size_t)n) return NULL;
	fclose(f);
	*size = (size_t)n;
	return p;
}

int main(int argc, char **argv)
{
	size_t src_n, expected_n;
	if (argc != 3) return 2;
	uint8_t *src = read_file(argv[1], &src_n);
	uint8_t *expected = read_file(argv[2], &expected_n);
	uint8_t *out = malloc(expected_n ? expected_n : 1);
	if (!src || !expected || !out ||
	    !j2_lz4_decompress_block(src, src_n, out, expected_n, expected_n)) return 3;
	for (size_t i = 0; i < expected_n; ++i) if (out[i] != expected[i]) return 4;
	if (j2_lz4_decompress_block(src, src_n, out, expected_n, expected_n - (expected_n != 0))) return 5;
	puts("C LZ4 decoder: real payload round-trip and output-bound checks passed");
	free(src); free(expected); free(out);
	return 0;
}
