#include "lz4_block.h"

static int read_length(const uint8_t *src, uint64_t src_size,
		       uint64_t *src_pos, uint64_t *length)
{
	uint8_t part;
	do {
		if (*src_pos >= src_size)
			return 0;
		part = src[(*src_pos)++];
		if (*length > UINT64_MAX - part)
			return 0;
		*length += part;
	} while (part == 255);
	return 1;
}

int j2_lz4_decompress_block(const uint8_t *src, uint64_t src_size,
			    uint8_t *dst, uint64_t dst_capacity,
			    uint64_t expected_size)
{
	uint64_t ip = 0, op = 0;
	if (!src || !dst || expected_size > dst_capacity || !src_size)
		return 0;
	while (ip < src_size) {
		uint8_t token = src[ip++];
		uint64_t literals = token >> 4;
		if (literals == 15 && !read_length(src, src_size, &ip, &literals))
			return 0;
		if (literals > src_size - ip || literals > dst_capacity - op)
			return 0;
		for (uint64_t i = 0; i < literals; ++i)
			dst[op++] = src[ip++];
		if (ip == src_size)
			break;
		if (src_size - ip < 2)
			return 0;
		uint64_t offset = (uint64_t)src[ip] | ((uint64_t)src[ip + 1] << 8);
		ip += 2;
		if (!offset || offset > op)
			return 0;
		uint64_t match = token & 0xf;
		if (match == 15 && !read_length(src, src_size, &ip, &match))
			return 0;
		if (match > UINT64_MAX - 4)
			return 0;
		match += 4;
		if (match > dst_capacity - op)
			return 0;
		for (uint64_t i = 0; i < match; ++i)
			dst[op + i] = dst[op + i - offset];
		op += match;
	}
	return ip == src_size && op == expected_size;
}
