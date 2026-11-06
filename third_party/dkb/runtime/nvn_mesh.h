// SPDX-License-Identifier: MIT
// Metadata for native mesh workgroup bodies lowered through the shared-memory IR.
#pragma once
#include <stdint.h>
#include <string.h>
#define NVN_MESH_META_OFFSET 0x780
#define NVN_MESH_META_MAGIC 0x314d4b44u
typedef struct {
    uint32_t magic, threads, payload, vertices, primitives, uses_task;
    uint32_t output_base, primitive_base, shared_bytes, components;
    // 0..127: user attribute component; 128..131: position component.
    uint8_t attribute[132];
} NvnMeshInfo;
static inline const NvnMeshInfo *nvn_mesh_info(const uint8_t *control) {
    if (!control) return NULL;
    const NvnMeshInfo *m = (const NvnMeshInfo *)(control + NVN_MESH_META_OFFSET);
    return m->magic == NVN_MESH_META_MAGIC ? m : NULL;
}
