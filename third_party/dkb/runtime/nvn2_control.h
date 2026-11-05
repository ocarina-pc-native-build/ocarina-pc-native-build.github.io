// SPDX-License-Identifier: MIT
#pragma once
#include <stdint.h>

// SPH v4 graphics headers encode a supported graphics stage. A compute UMOV
// opcode also begins with the same header type/version bits, but its next bits
// are an execution predicate, not a graphics stage. Do not skip its first 128 bytes.
static inline uint32_t nvn2_sph_type(uint32_t word) {
    uint32_t type=(word>>10)&15;
    return ((word&31)==1 || (word&31)==2) && ((word>>5)&31)==4 && type>=1 && type<=5 ? type : 0;
}
