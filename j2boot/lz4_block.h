#ifndef J2_LZ4_BLOCK_H
#define J2_LZ4_BLOCK_H

#include <stdint.h>

int j2_lz4_decompress_block(const uint8_t *src, uint64_t src_size,
			    uint8_t *dst, uint64_t dst_capacity,
			    uint64_t expected_size);

#endif
