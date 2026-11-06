// SPDX-License-Identifier: MIT
#pragma once
#include <stddef.h>
#include <stdint.h>

// NVN2 control stages differ from SPH types: a mesh program's SPH may look
// like a vertex or domain shader. Preserve the control identity before lowering.
enum {
    NVN2_STAGE_VERTEX = 0, NVN2_STAGE_FRAGMENT = 1, NVN2_STAGE_GEOMETRY = 2,
    NVN2_STAGE_TESS_CONTROL = 3, NVN2_STAGE_TESS_EVAL = 4, NVN2_STAGE_COMPUTE = 5,
    NVN2_STAGE_TASK = 6, NVN2_STAGE_MESH = 7, NVN2_STAGE_COUNT = 8,
    NVN2_STAGE_INVALID = NVN2_STAGE_COUNT
};

#ifdef __cplusplus
#define NVN2_CONTROL_CONSTEXPR constexpr
#else
#define NVN2_CONTROL_CONSTEXPR
#endif

static inline NVN2_CONTROL_CONSTEXPR uint32_t nvn2_control_u32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static inline NVN2_CONTROL_CONSTEXPR unsigned nvn2_control_stage(const uint8_t *control, size_t bytes) {
    if (!control || bytes < 0x57 || nvn2_control_u32(control) != 0x98761234u ||
        nvn2_control_u32(control + 4) != 0xc9u) return NVN2_STAGE_INVALID;
    uint32_t declared = nvn2_control_u32(control + 0x30);
    if (!declared) declared = 0xd8;   // compact controls use the same default as gfx_shader.c nvn2_sizes
    if (declared < 0x57 || declared > bytes || control[0x56] > NVN2_STAGE_MESH) return NVN2_STAGE_INVALID;
    return control[0x56];
}
#undef NVN2_CONTROL_CONSTEXPR

// SPH v4 graphics headers encode a supported graphics stage. A compute UMOV
// opcode also begins with the same header type/version bits, but its next bits
// are an execution predicate, not a graphics stage. Do not skip its first 128 bytes.
static inline uint32_t nvn2_sph_type(uint32_t word) {
    uint32_t type=(word>>10)&15;
    return ((word&31)==1 || (word&31)==2) && ((word>>5)&31)==4 && type>=1 && type<=5 ? type : 0;
}
