// SPDX-License-Identifier: MIT
// --probe-vkgeometry: original Maxwell VS/GS/FS through NVN recording and ordinary Vulkan replay.
// A completed readback proves the producer's exact bounded arguments before any indirect draw. The optional
// ordering round starts from a verified zero-count record and uses an explicit NVN dependency in one submission.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "cfg.h"
#include "host.h"
#include "nvn_api.h"
#include "nvn_geometry_control.h"
#include "vk_exec.h"

#define NVN_PROC(n) void nvnp_##n(Cpu *c);
#include "nvn_procs.inc"
#undef NVN_PROC
void vk_exec_draw_shutdown(void);
void vk_exec_xfer_shutdown(void);

enum { GP_CONTROL = 0x880, GP_CODE = 2048, GP_SKIP = 0x30, GP_WIDTH = 32, GP_HEIGHT = 32,
       GP_POOL = 0x100000, GP_COLOR = 0x10000, GP_UNIFORM = 0x20000, GP_VERTEX = 0x30000,
       GP_INDEX = 0x31000, GP_RECORD = 0x40100, GP_GUARD = GP_RECORD - 128, GP_RESET = 0x40200, GP_COMMAND = 0x50000,
       GP_COMMAND_CONTROL = 8192 };
static int gp_passthrough;

// Original program authoring. CPU preparation compiles these actual helpers without Vulkan and validates all modules.
static void gp_u32(uint8_t *p, uint32_t v) { memcpy(p, &v, 4); }
static uint64_t gp_movi(unsigned r, uint32_t v) {
    return UINT64_C(0x0100000000000000) | (uint64_t)v << 20 | UINT64_C(15) << 12 | UINT64_C(7) << 16 | r;
}
static uint64_t gp_movc(unsigned r, unsigned bank, unsigned word) {
    return UINT64_C(0x4c98000000000000) | UINT64_C(15) << 39 | (uint64_t)bank << 34 |
           (uint64_t)word << 20 | UINT64_C(7) << 16 | r;
}
static uint64_t gp_attr(unsigned r, unsigned address, unsigned vertex, int store, unsigned words) {
    return (store ? UINT64_C(0xeff0000000000000) : UINT64_C(0xefd8000000000000)) |
           (uint64_t)vertex << 39 | (uint64_t)(words - 1) << 47 | (uint64_t)address << 20 |
           UINT64_C(7) << 16 | UINT64_C(255) << 8 | r;
}
static uint64_t gp_ipa(unsigned r, unsigned address) {
    return UINT64_C(0xe000000000000000) | UINT64_C(255) << 39 | UINT64_C(7) << 47 |
           (uint64_t)address << 28 | UINT64_C(255) << 20 | UINT64_C(7) << 16 | UINT64_C(255) << 8 | r;
}
static uint64_t gp_stg(unsigned r, unsigned offset) {
    return UINT64_C(0xeed8000000000000) | UINT64_C(4) << 48 | UINT64_C(1) << 45 |
           (uint64_t)offset << 20 | UINT64_C(7) << 16 | UINT64_C(10) << 8 | r;
}
static uint32_t gp_program(unsigned stage, uint8_t control[GP_CONTROL], uint8_t code[GP_CODE]) {
    uint64_t ops[128];
    unsigned n = 0;
    memset(control, 0, GP_CONTROL), memset(code, 0, GP_CODE);
    if (stage == 0 && getenv("DKB_PROBE_NATIVE_HIGH_VS")) {
        // Authored native VS: position and color occupy the reserved lowering
        // register range while UR8 independently holds the multiplier 1.0.
        const uint32_t native[][4] = {
            {0xffe07321,0x80ff,0xc00,0}, // ALD.128 R224, a[0x80]
            {0xfff87321,0x90ff,0xc00,0}, // ALD.128 R248, a[0x90]
            {0x00087882,0x3f800000,0,0},   // UMOV UR8, 1.0 (mirror R224 must not replace native R224)
            {0x00087202,248,0xf00,0},      // low-register live color copy
            {0x00097c02,8,0x08000f00,0},   // MOV R9, UR8
            {0xe0e07220,9,0x00400000,0},  // FMUL R224, R224, R9
            {0xff007322,0x70e0,0xcff,0}, // AST.128 a[0x70], R224
            {0x00ef7802,0x3f800000,0xf00,0},
            {0xff007322,0x6cef,0xff,0},  // AST PointSize, R239
            {0xff007322,0x80f8,0xcff,0}, // AST.128 color, R248
            {0xff007322,0x8008,0xff,0},  // low-register copy survived all spills
            {0x0000794d,0,0x03800000,0},
        };
        gp_u32(code,1u|4u<<5|1u<<10);
        memcpy(code+0x80,native,sizeof native);
        const uint32_t length=0x80+sizeof native;
        gp_u32(control,0x98761234); gp_u32(control+4,0xc9);
        gp_u32(control+0x30,0xd8); gp_u32(control+0x38,length);
        return length;
    }
    unsigned sph = stage == 0 ? 1 : stage == 1 ? 5 : 4;
    gp_u32(code + GP_SKIP, 1u | 3u << 5 | sph << 10 | (stage == 2 ? 1u << 16 : 0));
    if (stage == 0) {
        ops[n++] = gp_attr(0, 0x80, 255, 0, 4);  // input Position and color, both user vertex attributes
        ops[n++] = gp_attr(4, 0x90, 255, 0, 4);
        ops[n++] = gp_attr(0, 0x70, 255, 1, 4);
        ops[n++] = gp_movi(8, 0x3f800000u);
        ops[n++] = gp_attr(8, 0x6c, 255, 1, 1);  // valid PointSize in the GS-disabled points control
        if (getenv("DKB_PROBE_LOCAL_ORDER")) {
            // The loaded color must survive a later overwrite of its local-memory slot.
            // Expression propagation may move arithmetic, but cannot defer this load.
            gp_u32(code + GP_SKIP + 4, 16);
            ops[n++] = UINT64_C(0xef50000000000000) | UINT64_C(4) << 48 |
                       UINT64_C(7) << 16 | UINT64_C(255) << 8 | 4;
            ops[n++] = UINT64_C(0xef40000000000000) | UINT64_C(4) << 48 |
                       UINT64_C(7) << 16 | UINT64_C(255) << 8 | 9;
            ops[n++] = gp_movi(10, 0x3f000000u);
            ops[n++] = UINT64_C(0xef50000000000000) | UINT64_C(4) << 48 |
                       UINT64_C(7) << 16 | UINT64_C(255) << 8 | 10;
            ops[n++] = UINT64_C(0x5c98000000000000) | UINT64_C(15) << 39 |
                       UINT64_C(9) << 20 | UINT64_C(7) << 16 | 4;
        }
        ops[n++] = gp_attr(4, 0x80, 255, 1, 4);
    } else if (stage == 1) {
        gp_u32(code + GP_SKIP + 6 * 4, 0xff);    // Location0 screen-linear RGBA interpolation
        gp_u32(code + GP_SKIP + 18 * 4, 15);     // RGBA target0
        for (unsigned i = 0; i < 4; i++) ops[n++] = gp_ipa(i, 0x80 + i * 4);
    } else {
        gp_u32(code + GP_SKIP + 8, 1u << 24);    // one invocation
        gp_u32(code + GP_SKIP + 12, 7u << 24);   // triangle strip
        gp_u32(code + GP_SKIP + 16, gp_passthrough ? 1 : 3);
        if (gp_passthrough) {
            uint32_t sph;
            memcpy(&sph, code + GP_SKIP, 4);
            gp_u32(code + GP_SKIP, sph | (1u << 24));
        }
        ops[n++] = gp_movc(10, 3, 0), ops[n++] = gp_movc(11, 3, 1);
        static const uint32_t args[5] = {3, 1, 0, 0, 0};
        for (unsigned i = 0; i < 5; i++) {
            ops[n++] = gp_movi(8, args[i]);
            ops[n++] = gp_stg(8, i * 4);
        }
        if (!gp_passthrough) {
            ops[n++] = gp_movi(9, 0);
            ops[n++] = gp_attr(12, 0x80, 9, 0, 4); // actual VS->GS Location0 color from valid input vertex0
            static const uint32_t positions[3][4] = {
                {0xbf400000u, 0xbf400000u, 0, 0x3f800000u},
                {0x3f400000u, 0xbf400000u, 0, 0x3f800000u},
                {0, 0x3f400000u, 0, 0x3f800000u}};
            for (unsigned v = 0; v < 3; v++) {
                for (unsigned i = 0; i < 4; i++) ops[n++] = gp_movi(i, positions[v][i]);
                // Outputs are undefined after EmitVertex; rewrite Position and color for every vertex.
                ops[n++] = gp_attr(0, 0x70, 255, 1, 4);
                ops[n++] = gp_attr(12, 0x80, 255, 1, 4);
                ops[n++] = UINT64_C(0xf6e0000000000000) | (uint64_t)(v == 2 ? 3 : 1) << 39 |
                           UINT64_C(7) << 16 | UINT64_C(255) << 8 | 255;
            }
        }
    }
    ops[n++] = UINT64_C(0xe30000000007000f);
    unsigned groups = (n + 2) / 3;
    for (unsigned g = 0; g < groups; g++) {
        uint64_t words[4] = {UINT64_C(0x001f8000fc0007e0), 0, 0, 0};
        for (unsigned lane = 0; lane < 3; lane++) if (g * 3 + lane < n) words[lane + 1] = ops[g * 3 + lane];
        memcpy(code + GP_SKIP + 0x50 + g * 32, words, sizeof words);
    }
    uint32_t total = GP_SKIP + 0x50 + groups * 32;
    gp_u32(control + 0x700, total), gp_u32(control + 0x704, total), gp_u32(control + 0x714, stage);
    return total;
}

#define GP_U(p) ((uint64_t)(uintptr_t)(p))
#define GP_OBJECT(type, name) static _Alignas(16) type name
GP_OBJECT(NVNdeviceBuilder, gp_device_builder);
GP_OBJECT(NVNdevice, gp_device);
GP_OBJECT(NVNmemoryPoolBuilder, gp_memory_builder);
GP_OBJECT(NVNmemoryPool, gp_memory_pool);
GP_OBJECT(NVNtextureBuilder, gp_texture_builder);
GP_OBJECT(NVNtexture, gp_color);
GP_OBJECT(NVNprogram, gp_full_program);
GP_OBJECT(NVNprogram, gp_plain_program);
GP_OBJECT(NVNcommandBuffer, gp_command);
static _Alignas(16) uint8_t gp_control[3][GP_CONTROL], gp_code[3][GP_CODE];
static Cpu gp_cpu;
static unsigned gp_checks, gp_failures;

static uint64_t gp_call(void (*fn)(Cpu *), const uint64_t a[8]) {
    memcpy(gp_cpu.x, a, 8 * sizeof a[0]);
    fn(&gp_cpu);
    return gp_cpu.x[0];
}
#define GP_CALL(n, ...) gp_call(nvnp_##n, (const uint64_t[8]){__VA_ARGS__})
#define GP_REQUIRE(c, text) do { gp_checks++; if (!(c)) { \
    printf("probe-vkgeometry: FAIL %s\n", text); gp_failures++; goto done; } } while (0)

// Read the current GPU-visible backing after the preceding NVN submission completed. No guest VA is dereferenced.
static int gp_read_gpu(uint64_t address, void *out, uint64_t size) {
    VkCtx *c = vk_ctx();
    VkMemSpan source;
    if (!size || size > 4096 || (address | size) & 3 || !vk_mem_resolve(address, size, &source)) return 0;
    VK_MEM_PICK(source);
    if (!source.buffer || source.avail < size || (source.offset & 3)) return 0;
    VkBuffer buffer = VK_NULL_HANDLE;
    VmaAllocation allocation = NULL;
    VmaAllocationInfo mapped;
    VkBufferCreateInfo bi = {.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, .size = size,
                              .usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT};
    VmaAllocationCreateInfo ai = {.usage = VMA_MEMORY_USAGE_AUTO_PREFER_HOST,
        .flags = VMA_ALLOCATION_CREATE_HOST_ACCESS_RANDOM_BIT | VMA_ALLOCATION_CREATE_MAPPED_BIT};
    if (vmaCreateBuffer(c->vma, &bi, &ai, &buffer, &allocation, &mapped) != VK_SUCCESS) return 0;
    if (!mapped.pMappedData) { vmaDestroyBuffer(c->vma, buffer, allocation); return 0; }
    VkCommandBuffer cb = vk_upload_begin();
    VkMemoryBarrier2 mb = {.sType = VK_STRUCTURE_TYPE_MEMORY_BARRIER_2,
        .srcStageMask = VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT, .srcAccessMask = VK_ACCESS_2_MEMORY_WRITE_BIT,
        .dstStageMask = VK_PIPELINE_STAGE_2_TRANSFER_BIT, .dstAccessMask = VK_ACCESS_2_TRANSFER_READ_BIT};
    VkDependencyInfo di = {.sType = VK_STRUCTURE_TYPE_DEPENDENCY_INFO, .memoryBarrierCount = 1, .pMemoryBarriers = &mb};
    vkCmdPipelineBarrier2(cb, &di);
    VkBufferCopy copy = {source.offset, 0, size};
    vkCmdCopyBuffer(cb, source.buffer, buffer, 1, &copy);
    mb.srcStageMask = VK_PIPELINE_STAGE_2_TRANSFER_BIT, mb.srcAccessMask = VK_ACCESS_2_TRANSFER_WRITE_BIT;
    mb.dstStageMask = VK_PIPELINE_STAGE_2_HOST_BIT, mb.dstAccessMask = VK_ACCESS_2_HOST_READ_BIT;
    vkCmdPipelineBarrier2(cb, &di);
    vk_upload_end();
    vk_upload_flush(1);
    int ok = vmaInvalidateAllocation(c->vma, allocation, 0, size) == VK_SUCCESS;
    if (ok) memcpy(out, mapped.pMappedData, (size_t)size);
    vmaDestroyBuffer(c->vma, buffer, allocation);
    return ok;
}

static int gp_submit(void) {
    uint64_t commands = GP_CALL(nvnCommandBufferEndRecording, GP_U(&gp_command));
    if (!commands) return 0;
    uint64_t fence = gfx_vulkan_backend.submit(&commands, 1, rt_ticks());
    if (!gfx_vulkan_backend.fence_wait(fence, UINT64_C(10000000000))) return 0;
    gfx_vulkan_backend.finish(); // recorder and completion ownership are idle before main-thread texture/readback work
    gfx_vulkan_backend.cpu_synced(fence);
    return 1;
}

static void gp_prefix(uint8_t *memory, void *control, int indirect) {
    GP_CALL(nvnCommandBufferAddControlMemory, GP_U(&gp_command), GP_U(control), GP_COMMAND_CONTROL);
    GP_CALL(nvnCommandBufferBeginRecording, GP_U(&gp_command));
    const NVNtexture *color = &gp_color;
    GP_CALL(nvnCommandBufferSetRenderTargets, GP_U(&gp_command), 1, GP_U(&color), 0, 0, 0);
    static const float clear[4] = {0, 0, 1, 1};
    GP_CALL(nvnCommandBufferClearColor, GP_U(&gp_command), 0, GP_U(clear), 15);
    GP_CALL(nvnCommandBufferSetViewport, GP_U(&gp_command), 0, 0, GP_WIDTH, GP_HEIGHT);
    GP_CALL(nvnCommandBufferSetScissor, GP_U(&gp_command), 0, 0, GP_WIDTH, GP_HEIGHT);
    GP_CALL(nvnCommandBufferBindProgram, GP_U(&gp_command), GP_U(indirect ? &gp_plain_program : &gp_full_program),
        indirect ? NVN_SHADER_STAGE_VERTEX_BIT | NVN_SHADER_STAGE_FRAGMENT_BIT : NVN_SHADER_STAGE_ALL_GRAPHICS_BITS);
    NVNvertexAttribState attr[2];
    NVNvertexStreamState stream;
    for (unsigned i = 0; i < 2; i++) {
        GP_CALL(nvnVertexAttribStateSetDefaults, GP_U(&attr[i]));
        GP_CALL(nvnVertexAttribStateSetFormat, GP_U(&attr[i]), NVN_FORMAT_RGBA32F, i * 16);
        GP_CALL(nvnVertexAttribStateSetStreamIndex, GP_U(&attr[i]), 0);
    }
    GP_CALL(nvnVertexStreamStateSetDefaults, GP_U(&stream));
    GP_CALL(nvnVertexStreamStateSetStride, GP_U(&stream), 32);
    GP_CALL(nvnCommandBufferBindVertexAttribState, GP_U(&gp_command), 2, GP_U(attr));
    GP_CALL(nvnCommandBufferBindVertexStreamState, GP_U(&gp_command), 1, GP_U(&stream));
    GP_CALL(nvnCommandBufferBindVertexBuffer, GP_U(&gp_command), 0,
        GP_U(memory + GP_VERTEX + (indirect ? 0 : gp_passthrough ? 96 : 192)),
        indirect || gp_passthrough ? 96 : 32);
    if (!indirect) GP_CALL(nvnCommandBufferBindUniformBuffer, GP_U(&gp_command), NVN_SHADER_STAGE_GEOMETRY,
        0, GP_U(memory + GP_UNIFORM), 256); // actual shader c3, NVN user UBO slot0
}

// Sample centers never lie on the authored triangle's edges. NVN viewport orientation may flip the whole image.
static int gp_inside(unsigned x, unsigned y, int flip) {
    int xx = (int)x * 2 + 1, yy = (int)(flip ? GP_HEIGHT - 1 - y : y) * 2 + 1;
    return yy > 8 && yy < 56 && 2 * xx - yy > 8 && 2 * xx + yy < 120;
}

static int gp_pixels(uint32_t pixels[GP_WIDTH * GP_HEIGHT], uint32_t color, int *orientation) {
    NVNcopyRegion region = {0, 0, 0, GP_WIDTH, GP_HEIGHT, 1};
    memset(pixels, 0x5a, GP_WIDTH * GP_HEIGHT * sizeof *pixels); // a refused/short read cannot reuse previous pixels
    GP_CALL(nvnTextureReadTexels, GP_U(&gp_color), 0, GP_U(&region), GP_U(pixels));
    unsigned bad[2] = {0};
    for (unsigned y = 0; y < GP_HEIGHT; y++) for (unsigned x = 0; x < GP_WIDTH; x++) {
        for (int flip = 0; flip < 2; flip++)
            bad[flip] += pixels[y * GP_WIDTH + x] != (gp_inside(x, y, flip) ? color : 0xffff0000u);
    }
    *orientation = bad[0] == 0 ? 0 : bad[1] == 0 ? 1 : -1;
    gp_checks += GP_WIDTH * GP_HEIGHT;
    if (*orientation < 0) {
        printf("probe-vkgeometry: FAIL triangle pixels (%u normal / %u flipped mismatches)\n", bad[0], bad[1]);
        gp_failures++;
    }
    return *orientation >= 0;
}

// Both possible argument records are bounded: reset draws no indices, and the already validated original GS
// writes exactly three owned indices/one instance. Reset completion is checked before the combined recording;
// there is no CPU readback or wait between its producer and consumer. The normal NVN barrier supplies ordering.
static int gp_ordered(uint8_t *memory, void *control, uint64_t record_address,
                      const uint8_t verified[256], int expected_orientation) {
    int ok = 0;
    uint8_t expected_guard[256], reset[256], after[256];
    static const uint32_t produced[5] = {3, 1, 0, 0, 0}, initial[5] = {0, 1, 0, 0, 0};
    memset(expected_guard, 0xa5, sizeof expected_guard);
    memcpy(expected_guard + 128, produced, sizeof produced);
    GP_REQUIRE(memory && control && gp_passthrough && record_address == GP_U(memory + GP_RECORD) &&
        expected_orientation >= 0 && expected_orientation <= 1, "ordering round owned inputs");
    GP_REQUIRE(verified && !memcmp(verified, expected_guard, sizeof expected_guard), "ordering round prior bounded GPU proof");
    memcpy(memory + GP_RESET, initial, sizeof initial);
    GP_CALL(nvnMemoryPoolFlushMappedRange, GP_U(&gp_memory_pool), GP_RESET, sizeof initial);
    GP_CALL(nvnCommandBufferAddControlMemory, GP_U(&gp_command), GP_U(control), GP_COMMAND_CONTROL);
    GP_CALL(nvnCommandBufferBeginRecording, GP_U(&gp_command));
    GP_CALL(nvnCommandBufferCopyBufferToBuffer, GP_U(&gp_command), GP_U(memory + GP_RESET),
        record_address, sizeof initial, 0);
    GP_REQUIRE(gp_submit(), "ordering round reset submission completion");
    GP_REQUIRE(gp_read_gpu(GP_U(memory + GP_GUARD), reset, sizeof reset), "ordering round reset GPU readback");
    memcpy(expected_guard + 128, initial, sizeof initial);
    GP_REQUIRE(!memcmp(reset, expected_guard, sizeof reset), "ordering round exact zero-count record and canaries");

    gp_prefix(memory, control, 0);
    GP_CALL(nvnCommandBufferDrawArrays, GP_U(&gp_command), NVN_DRAW_PRIMITIVE_TRIANGLES, 0, 3);
    GP_CALL(nvnCommandBufferBarrier, GP_U(&gp_command),
        NVN_BARRIER_ORDER_PRIMITIVES_BIT | NVN_BARRIER_ORDER_INDIRECT_DATA_BIT);
    GP_CALL(nvnCommandBufferBindProgram, GP_U(&gp_command), GP_U(&gp_plain_program),
        NVN_SHADER_STAGE_VERTEX_BIT | NVN_SHADER_STAGE_FRAGMENT_BIT);
    GP_CALL(nvnCommandBufferBindVertexBuffer, GP_U(&gp_command), 0, GP_U(memory + GP_VERTEX), 96);
    GP_CALL(nvnCommandBufferDrawElementsIndirect, GP_U(&gp_command), NVN_DRAW_PRIMITIVE_TRIANGLES,
        NVN_INDEX_TYPE_UNSIGNED_SHORT, GP_U(memory + GP_INDEX), record_address);
    GP_REQUIRE(gp_submit(), "ordering round combined submission completion");
    uint32_t pixels[GP_WIDTH * GP_HEIGHT];
    int orientation;
    GP_REQUIRE(gp_pixels(pixels, 0xff00ff00u, &orientation) && orientation == expected_orientation,
        "ordering round producer/barrier/indirect green triangle");
    GP_REQUIRE(gp_read_gpu(GP_U(memory + GP_GUARD), after, sizeof after), "ordering round final GPU readback");
    GP_REQUIRE(!memcmp(after, verified, sizeof after), "ordering round exact produced record and canaries");
    puts("probe-vkgeometry: verified zero reset -> GS -> NVN barrier -> indirect in one NVN recording/submission");
    ok = 1;
done:
    return ok;
}

// Reports sample a running counter; they must not stop it. Exercise consecutive
// reports, a pass boundary, a submission boundary, resets and genuinely empty draws.
static int gp_occlusion_reports(uint8_t *memory, void *control) {
    int ok = 0;
    enum { offset = 0x42000, guard_size = 512, reports = 10 };
    uint8_t *guard = memory + offset;
    NVNcounterData *result = (NVNcounterData *)(guard + 64);
    VkPhysicalDeviceFeatures features;
    vkGetPhysicalDeviceFeatures(vk_ctx()->phys, &features);
    GP_REQUIRE(features.occlusionQueryPrecise, "precise occlusion counts for exact coverage checks");
    memset(guard, 0xa5, guard_size);
    GP_CALL(nvnMemoryPoolFlushMappedRange, GP_U(&gp_memory_pool), offset, guard_size);
    unsigned coverage = 0;
    for (unsigned y = 0; y < GP_HEIGHT; y++) for (unsigned x = 0; x < GP_WIDTH; x++)
        coverage += gp_inside(x, y, 0);

#define GP_REPORT(i) GP_CALL(nvnCommandBufferReportCounter, GP_U(&gp_command), \
    NVN_COUNTER_TYPE_SAMPLES_PASSED, GP_U(&result[i]))
#define GP_TRIANGLE() GP_CALL(nvnCommandBufferDrawArrays, GP_U(&gp_command), NVN_DRAW_PRIMITIVE_TRIANGLES, 0, 3)
#define GP_RESET_COUNT() GP_CALL(nvnCommandBufferResetCounter, GP_U(&gp_command), NVN_COUNTER_TYPE_SAMPLES_PASSED)
    gp_prefix(memory, control, 1);
    GP_RESET_COUNT();
    GP_TRIANGLE(); GP_REPORT(0);
    GP_TRIANGLE(); GP_REPORT(1);
    GP_CALL(nvnCommandBufferBarrier, GP_U(&gp_command), NVN_BARRIER_ORDER_PRIMITIVES_BIT);
    GP_TRIANGLE(); GP_REPORT(2);
    GP_REQUIRE(gp_submit(), "consecutive occlusion reports complete");
    gp_prefix(memory, control, 1);
    GP_TRIANGLE(); GP_REPORT(3);
    GP_REQUIRE(gp_submit(), "occlusion count survives a submission boundary");
    gp_prefix(memory, control, 1);
    GP_RESET_COUNT(); GP_REPORT(4);
    GP_CALL(nvnCommandBufferSetScissor, GP_U(&gp_command), 0, 0, 0, 0);
    GP_TRIANGLE(); GP_REPORT(5);
    GP_CALL(nvnCommandBufferSetScissor, GP_U(&gp_command), 0, 0, GP_WIDTH, GP_HEIGHT);
    GP_TRIANGLE(); GP_REPORT(6); GP_REPORT(7);
    GP_RESET_COUNT(); GP_REPORT(8);
    GP_TRIANGLE(); GP_REPORT(9);
    GP_REQUIRE(gp_submit(), "empty, repeated and reset occlusion reports complete");
#undef GP_REPORT
#undef GP_TRIANGLE
#undef GP_RESET_COUNT
    static const unsigned multiples[reports] = {1, 2, 3, 4, 0, 0, 1, 1, 0, 1};
    unsigned failures_before = gp_failures;
    for (unsigned i = 0; i < reports; i++) {
        uint64_t expected = (uint64_t)coverage * multiples[i];
        gp_checks++;
        if (result[i].counter != expected || !result[i].timestamp) {
            printf("probe-vkgeometry: FAIL occlusion report %u: %llu samples, expected %llu, timestamp %llu\n",
                i, (unsigned long long)result[i].counter, (unsigned long long)expected,
                (unsigned long long)result[i].timestamp);
            gp_failures++;
        }
    }
    for (unsigned i = 0; i < guard_size; i++) if (i < 64 || i >= 64 + reports * sizeof *result) {
        gp_checks++;
        if (guard[i] != 0xa5) gp_failures++;
    }
    ok = gp_failures == failures_before;
    printf("probe-vkgeometry: cumulative occlusion reports %s, exact triangle coverage %u\n", ok ? "passed" : "FAILED", coverage);
done:
    return ok;
}

// A condition must not read stale host counters merely because many other
// reports were recorded later in the same, still unsubmitted command buffer.
static int gp_pending_condition(uint8_t *memory, void *control) {
    int ok = 0, orientation;
    enum { offset = 0x60000, reports = 1025 };
    NVNcounterData *result = (NVNcounterData *)(memory + offset);
    uint32_t pixels[GP_WIDTH * GP_HEIGHT];
    memset(result, 0, (reports + 2) * sizeof *result);
    GP_CALL(nvnMemoryPoolFlushMappedRange, GP_U(&gp_memory_pool), offset, (reports + 2) * sizeof *result);
    gp_prefix(memory, control, 1);
    GP_CALL(nvnCommandBufferResetCounter, GP_U(&gp_command), NVN_COUNTER_TYPE_SAMPLES_PASSED);
    GP_CALL(nvnCommandBufferDrawArrays, GP_U(&gp_command), NVN_DRAW_PRIMITIVE_TRIANGLES, 0, 3);
    GP_CALL(nvnCommandBufferReportCounter, GP_U(&gp_command), NVN_COUNTER_TYPE_SAMPLES_PASSED, GP_U(&result[0]));
    for (unsigned i = 2; i < reports + 2; i++)
        GP_CALL(nvnCommandBufferReportCounter, GP_U(&gp_command), NVN_COUNTER_TYPE_TIMESTAMP, GP_U(&result[i]));
    static const float blue[4] = {0, 0, 1, 1};
    GP_CALL(nvnCommandBufferClearColor, GP_U(&gp_command), 0, GP_U(blue), 15);
    GP_CALL(nvnCommandBufferSetRenderEnableConditional, GP_U(&gp_command), 1, GP_U(result));
    GP_CALL(nvnCommandBufferDrawArrays, GP_U(&gp_command), NVN_DRAW_PRIMITIVE_TRIANGLES, 0, 3);
    GP_CALL(nvnCommandBufferSetRenderEnable, GP_U(&gp_command), 1);
    GP_REQUIRE(gp_submit(), "many pending counter reports complete");
    GP_REQUIRE(result[0].counter > 0 && result[1].counter == 0, "visibility producer counter completed");
    GP_REQUIRE(gp_pixels(pixels, 0xff00ff00u, &orientation), "pending visibility report survives later reports");
    gp_prefix(memory, control, 1);
    GP_CALL(nvnCommandBufferSetRenderEnableConditional, GP_U(&gp_command), 1, GP_U(result));
    GP_CALL(nvnCommandBufferDrawArrays, GP_U(&gp_command), NVN_DRAW_PRIMITIVE_TRIANGLES, 0, 3);
    GP_CALL(nvnCommandBufferSetRenderEnable, GP_U(&gp_command), 1);
    GP_REQUIRE(gp_submit(), "completed counter condition completes");
    GP_REQUIRE(gp_pixels(pixels, 0xff00ff00u, &orientation), "completed visibility report is readable");
    gp_prefix(memory, control, 1);
    GP_CALL(nvnCommandBufferSetRenderEnableConditional, GP_U(&gp_command), 0, GP_U(result));
    GP_CALL(nvnCommandBufferDrawArrays, GP_U(&gp_command), NVN_DRAW_PRIMITIVE_TRIANGLES, 0, 3);
    GP_CALL(nvnCommandBufferSetRenderEnable, GP_U(&gp_command), 1);
    GP_REQUIRE(gp_submit(), "completed false condition completes");
    GP_REQUIRE(gp_pixels(pixels, 0xffff0000u, &orientation), "completed unequal values still suppress equality draw");
    gp_prefix(memory, control, 1);
    GP_CALL(nvnCommandBufferReportCounter, GP_U(&gp_command), NVN_COUNTER_TYPE_SAMPLES_PASSED, GP_U(result));
    GP_CALL(nvnCommandBufferReportCounter, GP_U(&gp_command), NVN_COUNTER_TYPE_TIMESTAMP, GP_U(result));
    GP_CALL(nvnCommandBufferSetRenderEnableConditional, GP_U(&gp_command), 1, GP_U(result));
    GP_CALL(nvnCommandBufferDrawArrays, GP_U(&gp_command), NVN_DRAW_PRIMITIVE_TRIANGLES, 0, 3);
    GP_CALL(nvnCommandBufferSetRenderEnable, GP_U(&gp_command), 1);
    GP_REQUIRE(gp_submit(), "overwritten pending counter completes");
    GP_REQUIRE(result[0].counter == 0 && result[0].timestamp, "latest report overwrites the sample count");
    GP_REQUIRE(gp_pixels(pixels, 0xffff0000u, &orientation), "latest timestamp report controls the condition");
    gp_prefix(memory, control, 1);
    GP_CALL(nvnCommandBufferResetCounter, GP_U(&gp_command), NVN_COUNTER_TYPE_SAMPLES_PASSED);
    GP_CALL(nvnCommandBufferReportCounter, GP_U(&gp_command), NVN_COUNTER_TYPE_SAMPLES_PASSED, GP_U(result));
    GP_CALL(nvnCommandBufferSetRenderEnableConditional, GP_U(&gp_command), 1, GP_U(result));
    static const float red[4] = {1, 0, 0, 1};
    GP_CALL(nvnCommandBufferClearColor, GP_U(&gp_command), 0, GP_U(red), 15);
    GP_CALL(nvnCommandBufferDrawArrays, GP_U(&gp_command), NVN_DRAW_PRIMITIVE_TRIANGLES, 0, 3);
    GP_CALL(nvnCommandBufferSetRenderEnable, GP_U(&gp_command), 1);
    GP_REQUIRE(gp_submit(), "pending zero-count condition completes");
    GP_REQUIRE(result[0].counter == 0, "zero-count report has no covered samples");
    GP_REQUIRE(gp_pixels(pixels, 0xffff0000u, &orientation), "pending false condition suppresses clears and draws");
    gp_prefix(memory, control, 1);
    GP_CALL(nvnCommandBufferResetCounter, GP_U(&gp_command), NVN_COUNTER_TYPE_SAMPLES_PASSED);
    for (unsigned i = 0; i < 3; i++) {
        GP_CALL(nvnCommandBufferDrawArrays, GP_U(&gp_command), NVN_DRAW_PRIMITIVE_TRIANGLES, 0, 3);
        GP_CALL(nvnCommandBufferReportCounter, GP_U(&gp_command), NVN_COUNTER_TYPE_SAMPLES_PASSED, GP_U(result));
        GP_CALL(nvnCommandBufferSetRenderEnableConditional, GP_U(&gp_command), 1, GP_U(result));
        GP_CALL(nvnCommandBufferSetRenderEnable, GP_U(&gp_command), 1);
        if (i == 1) {
            GP_CALL(nvnCommandBufferReportCounter, GP_U(&gp_command), NVN_COUNTER_TYPE_TIMESTAMP, GP_U(result));
            GP_CALL(nvnCommandBufferSetRenderEnableConditional, GP_U(&gp_command), 0, GP_U(result));
            GP_CALL(nvnCommandBufferClearColor, GP_U(&gp_command), 0, GP_U(blue), 15);
            GP_CALL(nvnCommandBufferSetRenderEnable, GP_U(&gp_command), 1);
        }
    }
    GP_CALL(nvnCommandBufferResetCounter, GP_U(&gp_command), NVN_COUNTER_TYPE_SAMPLES_PASSED);
    GP_CALL(nvnCommandBufferReportCounter, GP_U(&gp_command), NVN_COUNTER_TYPE_SAMPLES_PASSED, GP_U(&result[2]));
    GP_CALL(nvnCommandBufferSetRenderEnableConditional, GP_U(&gp_command), 1, GP_U(&result[2]));
    GP_CALL(nvnCommandBufferClearColor, GP_U(&gp_command), 0, GP_U(red), 15);
    GP_CALL(nvnCommandBufferSetRenderEnable, GP_U(&gp_command), 1);
    GP_REQUIRE(gp_submit(), "multiple conditional prefixes and reset complete");
    unsigned coverage = 0;
    for (unsigned y = 0; y < GP_HEIGHT; y++) for (unsigned x = 0; x < GP_WIDTH; x++)
        coverage += gp_inside(x, y, 0);
    GP_REQUIRE(result[0].counter == 3 * coverage && result[2].counter == 0,
        "prefix snapshots preserve overwrite order and count samples exactly once");
    GP_REQUIRE(gp_pixels(pixels, 0xff00ff00u, &orientation), "reset after resolved prefixes suppresses destructive clear");
    puts("probe-vkgeometry: pending condition survives 1025 later reports and completion");
    ok = 1;
done:
    return ok;
}

// Original depth-export fixture: partial color masks still reserve four GPRs
// per active target. Distinct filler values expose a component-count mistake.
static int gp_fragment_depth(uint8_t *memory, void *control) {
    int ok = 0, depth_live = 0, program_live = 0;
    static _Alignas(16) NVNtexture depth;
    static _Alignas(16) NVNprogram program;
    static _Alignas(16) uint8_t fs_control[GP_CONTROL], fs_code[GP_CODE];
    GP_CALL(nvnTextureBuilderSetFormat, GP_U(&gp_texture_builder), NVN_FORMAT_DEPTH32F);
    GP_CALL(nvnTextureBuilderSetStorage, GP_U(&gp_texture_builder), GP_U(&gp_memory_pool), 0x80000);
    GP_REQUIRE(GP_CALL(nvnTextureBuilderGetStorageSize, GP_U(&gp_texture_builder)) <= 0x10000,
        "bounded fragment-depth storage");
    GP_REQUIRE((uint8_t)GP_CALL(nvnTextureInitialize, GP_U(&depth), GP_U(&gp_texture_builder)),
        "fragment-depth texture initialization");
    depth_live = 1;
    static const uint32_t masks[] = {0, 15, 1, 0x10f, 0x80000001u, 0xffffffffu};
    for (unsigned test = 0; test < sizeof masks / sizeof *masks; test++) {
        uint32_t mask = masks[test];
        unsigned targets = 0;
        for (unsigned i = 0; i < 8; i++) targets += !!((mask >> (4 * i)) & 15);
        unsigned depth_register = 4 * targets + 1;
        memset(fs_control, 0, sizeof fs_control), memset(fs_code, 0, sizeof fs_code);
        gp_u32(fs_code + GP_SKIP, 1u | 3u << 5 | 5u << 10);
        gp_u32(fs_code + GP_SKIP + 18 * 4, mask);
        gp_u32(fs_code + GP_SKIP + 19 * 4, 2); // depth export
        uint64_t ops[35];
        for (unsigned i = 0; i < 34; i++)
            ops[i] = gp_movi(i, i == depth_register ? 0x3e800000u : 0x3f400000u);
        ops[34] = UINT64_C(0xe30000000007000f);
        for (unsigned g = 0; g < 12; g++) {
            uint64_t words[4] = {UINT64_C(0x001f8000fc0007e0), 0, 0, 0};
            for (unsigned lane = 0; lane < 3; lane++)
                if (3 * g + lane < 35) words[lane + 1] = ops[3 * g + lane];
            memcpy(fs_code + GP_SKIP + 0x50 + g * 32, words, sizeof words);
        }
        gp_u32(fs_control + 0x700, GP_SKIP + 0x50 + 12 * 32);
        gp_u32(fs_control + 0x704, GP_SKIP + 0x50 + 12 * 32);
        gp_u32(fs_control + 0x714, 1);
        NVNshaderData stages[2] = {{GP_U(gp_code[0]), gp_control[0]}, {GP_U(fs_code), fs_control}};
        GP_REQUIRE((uint8_t)GP_CALL(nvnProgramInitialize, GP_U(&program), GP_U(&gp_device)),
            "fragment-depth program initialization");
        program_live = 1;
        GP_REQUIRE((uint8_t)GP_CALL(nvnProgramSetShaders, GP_U(&program), 2, GP_U(stages)),
            "original fragment-depth program");
        gp_prefix(memory, control, 1);
        const NVNtexture *color = &gp_color;
        GP_CALL(nvnCommandBufferSetRenderTargets, GP_U(&gp_command), 1, GP_U(&color), 0, GP_U(&depth), 0);
        gp_cpu.v[0] = 0x3f800000u;
        GP_CALL(nvnCommandBufferClearDepthStencil, GP_U(&gp_command), 1, 0, 0);
        NVNdepthStencilState ds;
        GP_CALL(nvnDepthStencilStateSetDefaults, GP_U(&ds));
        GP_CALL(nvnDepthStencilStateSetDepthTestEnable, GP_U(&ds), 1);
        GP_CALL(nvnDepthStencilStateSetDepthWriteEnable, GP_U(&ds), 1);
        GP_CALL(nvnDepthStencilStateSetDepthFunc, GP_U(&ds), NVN_DEPTH_FUNC_ALWAYS);
        GP_CALL(nvnCommandBufferBindDepthStencilState, GP_U(&gp_command), GP_U(&ds));
        GP_CALL(nvnCommandBufferBindProgram, GP_U(&gp_command), GP_U(&program),
            NVN_SHADER_STAGE_VERTEX_BIT | NVN_SHADER_STAGE_FRAGMENT_BIT);
        GP_CALL(nvnCommandBufferDrawArrays, GP_U(&gp_command), NVN_DRAW_PRIMITIVE_TRIANGLES, 0, 3);
        GP_REQUIRE(gp_submit(), "fragment-depth submission completion");
        float pixels[GP_WIDTH * GP_HEIGHT];
        memset(pixels, 0xa5, sizeof pixels);
        NVNcopyRegion region = {0, 0, 0, GP_WIDTH, GP_HEIGHT, 1};
        GP_CALL(nvnTextureReadTexels, GP_U(&depth), 0, GP_U(&region), GP_U(pixels));
        unsigned bad[2] = {0, 0};
        for (unsigned y = 0; y < GP_HEIGHT; y++) for (unsigned x = 0; x < GP_WIDTH; x++)
            for (int flip = 0; flip < 2; flip++)
                bad[flip] += pixels[y * GP_WIDTH + x] != (gp_inside(x, y, flip) ? 0.25f : 1.0f);
        gp_checks += GP_WIDTH * GP_HEIGHT;
        if (bad[0] && bad[1]) {
            printf("probe-vkgeometry: FAIL fragment-depth mask %#x register %u (%u/%u mismatches)\n",
                mask, depth_register, bad[0], bad[1]);
            gp_failures++;
        }
        GP_CALL(nvnProgramFinalize, GP_U(&program));
        program_live = 0;
    }
    ok = 1;
done:
    gfx_vulkan_backend.finish();
    if (program_live) GP_CALL(nvnProgramFinalize, GP_U(&program));
    if (depth_live) GP_CALL(nvnTextureFinalize, GP_U(&depth));
    return ok;
}

static int gp_run(int passthrough, int ordered) {
    gp_passthrough = passthrough;
    const GfxBackend *backend = &gfx_vulkan_backend;
    if (gfx_backend() != backend || cfg_bool("TOTK_FIX_C0")) {
        printf("probe-vkgeometry: requires TOTK_GPU=vulkan and TOTK_FIX_C0=0 (ordinary Maxwell only)\n");
        return 1;
    }
    gp_checks = gp_failures = 0;
    uint64_t heap = 0, shader_failures = gfx_shader_failures();
    uint8_t *memory = NULL;
    void *control = NULL;
    int device_live = 0, pool_live = 0, texture_live = 0, command_live = 0, programs_live = 0;
    GP_REQUIRE(!mem_set_heap_size(16ull << 20, &heap) && heap, "SetHeapSize");
    memory = (uint8_t *)(uintptr_t)heap;
    control = mem_kernel_alloc(GP_COMMAND_CONTROL, 16);
    GP_REQUIRE(control, "owned command control allocation");
    GP_CALL(nvnDeviceBuilderSetDefaults, GP_U(&gp_device_builder));
    GP_REQUIRE((uint8_t)GP_CALL(nvnDeviceInitialize, GP_U(&gp_device), GP_U(&gp_device_builder)), "DeviceInitialize");
    device_live = 1;
    GP_CALL(nvnMemoryPoolBuilderSetDefaults, GP_U(&gp_memory_builder));
    GP_CALL(nvnMemoryPoolBuilderSetDevice, GP_U(&gp_memory_builder), GP_U(&gp_device));
    GP_CALL(nvnMemoryPoolBuilderSetStorage, GP_U(&gp_memory_builder), GP_U(memory), GP_POOL);
    GP_CALL(nvnMemoryPoolBuilderSetFlags, GP_U(&gp_memory_builder),
        NVN_MEMORY_POOL_FLAGS_CPU_CACHED | NVN_MEMORY_POOL_FLAGS_GPU_CACHED);
    GP_REQUIRE((uint8_t)GP_CALL(nvnMemoryPoolInitialize, GP_U(&gp_memory_pool), GP_U(&gp_memory_builder)), "MemoryPoolInitialize");
    pool_live = 1;
    printf("probe-vkgeometry: device %s driver %#x core-validation-active %d\n", vk_ctx()->props.deviceName,
        vk_ctx()->props.driverVersion, vk_ctx()->validation);
    GP_CALL(nvnTextureBuilderSetDefaults, GP_U(&gp_texture_builder));
    GP_CALL(nvnTextureBuilderSetDevice, GP_U(&gp_texture_builder), GP_U(&gp_device));
    GP_CALL(nvnTextureBuilderSetTarget, GP_U(&gp_texture_builder), NVN_TEXTURE_TARGET_2D);
    GP_CALL(nvnTextureBuilderSetSize2D, GP_U(&gp_texture_builder), GP_WIDTH, GP_HEIGHT);
    GP_CALL(nvnTextureBuilderSetLevels, GP_U(&gp_texture_builder), 1);
    GP_CALL(nvnTextureBuilderSetFormat, GP_U(&gp_texture_builder), NVN_FORMAT_RGBA8);
    GP_CALL(nvnTextureBuilderSetStorage, GP_U(&gp_texture_builder), GP_U(&gp_memory_pool), GP_COLOR);
    uint64_t texture_bytes = GP_CALL(nvnTextureBuilderGetStorageSize, GP_U(&gp_texture_builder));
    GP_REQUIRE(texture_bytes && texture_bytes <= 0x10000, "bounded color storage");
    GP_REQUIRE((uint8_t)GP_CALL(nvnTextureInitialize, GP_U(&gp_color), GP_U(&gp_texture_builder)), "TextureInitialize");
    texture_live = 1;
    static const float vertices[7][8] = {
        {-0.75f, -0.75f, 0, 1, 0, 1, 0, 1}, {0.75f, -0.75f, 0, 1, 0, 1, 0, 1},
        {0, 0.75f, 0, 1, 0, 1, 0, 1},
        {-0.75f, -0.75f, 0, 1, 1, 0, 0, 1}, {0.75f, -0.75f, 0, 1, 1, 0, 0, 1},
        {0, 0.75f, 0, 1, 1, 0, 0, 1}, {0, 0, 0, 1, 1, 0, 0, 1}};
    static const uint16_t indices[3] = {0, 1, 2};
    uint64_t record_address = GP_U(memory + GP_RECORD);
    memcpy(memory + GP_UNIFORM, &record_address, 8);
    memcpy(memory + GP_VERTEX, vertices, sizeof vertices), memcpy(memory + GP_INDEX, indices, sizeof indices);
    memset(memory + GP_GUARD, 0xa5, 256), memset(memory + GP_RECORD, 0, 20);
    GP_CALL(nvnMemoryPoolFlushMappedRange, GP_U(&gp_memory_pool), GP_UNIFORM, GP_POOL - GP_UNIFORM);
    NVNshaderData shaders[3];
    for (unsigned stage = 0; stage < 3; stage++) {
        uint32_t length = gp_program(stage, gp_control[stage], gp_code[stage]);
        if (stage == 2 && gp_passthrough) {
            static const uint32_t skip[8] = {0x0fffffffu, 0xfffffff0u, UINT32_MAX, UINT32_MAX,
                                             UINT32_MAX, UINT32_MAX, UINT32_MAX, UINT32_MAX};
            GP_REQUIRE(nvn_geometry_control_pack_portable(gp_control[stage], GP_CONTROL,
                gp_code[stage], length, skip), "canonical portable geometry metadata");
        }
        shaders[stage] = (NVNshaderData){GP_U(gp_code[stage]), gp_control[stage]};
    }
    GP_REQUIRE((uint8_t)GP_CALL(nvnProgramInitialize, GP_U(&gp_full_program), GP_U(&gp_device)), "full ProgramInitialize");
    programs_live = 1;
    GP_REQUIRE((uint8_t)GP_CALL(nvnProgramSetShaders, GP_U(&gp_full_program), 3, GP_U(shaders)), "original VS/FS/GS program");
    GP_REQUIRE((uint8_t)GP_CALL(nvnProgramInitialize, GP_U(&gp_plain_program), GP_U(&gp_device)), "plain ProgramInitialize");
    programs_live = 2;
    GP_REQUIRE((uint8_t)GP_CALL(nvnProgramSetShaders, GP_U(&gp_plain_program), 2, GP_U(shaders)), "original VS/FS program");
    GP_REQUIRE((uint8_t)GP_CALL(nvnCommandBufferInitialize, GP_U(&gp_command), GP_U(&gp_device)), "CommandBufferInitialize");
    command_live = 1;
    GP_CALL(nvnCommandBufferAddCommandMemory, GP_U(&gp_command), GP_U(&gp_memory_pool), GP_COMMAND, 0x10000);
    gp_prefix(memory, control, 0);
    GP_CALL(nvnCommandBufferDrawArrays, GP_U(&gp_command),
        gp_passthrough ? NVN_DRAW_PRIMITIVE_TRIANGLES : NVN_DRAW_PRIMITIVE_POINTS, 0, gp_passthrough ? 3 : 1);
    GP_REQUIRE(gp_submit(), "GS submission completion");
    uint8_t guard[256];
    GP_REQUIRE(gp_read_gpu(GP_U(memory + GP_GUARD), guard, sizeof guard), "GPU argument/canary readback");
    static const uint32_t expected[5] = {3, 1, 0, 0, 0};
    int safe = 1;
    for (unsigned i = 0; i < 5; i++) {
        uint32_t value;
        memcpy(&value, guard + 128 + i * 4, 4);
        gp_checks++;
        if (value != expected[i]) {
            printf("probe-vkgeometry: FAIL argument %u = %u expected %u\n", i, value, expected[i]);
            gp_failures++, safe = 0;
        }
    }
    for (unsigned i = 0; i < sizeof guard; i++) if (i < 128 || i >= 148) {
        gp_checks++;
        if (guard[i] != 0xa5) { gp_failures++, safe = 0; printf("probe-vkgeometry: FAIL canary %u\n", i); }
    }
    uint32_t first[GP_WIDTH * GP_HEIGHT], second[GP_WIDTH * GP_HEIGHT];
    int first_orientation, second_orientation;
    gp_pixels(first, 0xff0000ffu, &first_orientation);
    if (safe) {
        puts("probe-vkgeometry: GPU record {3,1,0,0,0} and all 236 surrounding canary bytes verified");
        // Only exact {3,1,0,0,0} can reach this call; all three uint16 indices and 96 vertex bytes are owned and valid.
        gp_prefix(memory, control, 1);
        GP_CALL(nvnCommandBufferDrawElementsIndirect, GP_U(&gp_command), NVN_DRAW_PRIMITIVE_TRIANGLES,
            NVN_INDEX_TYPE_UNSIGNED_SHORT, GP_U(memory + GP_INDEX), record_address);
        GP_REQUIRE(gp_submit(), "validated indexed-indirect submission completion");
        gp_pixels(second, 0xff00ff00u, &second_orientation);
        GP_REQUIRE(first_orientation >= 0 && first_orientation == second_orientation, "same direct-GS/indirect triangle coverage");
        uint8_t after[256];
        GP_REQUIRE(gp_read_gpu(GP_U(memory + GP_GUARD), after, sizeof after), "post-indirect GPU record readback");
        GP_REQUIRE(!memcmp(guard, after, sizeof guard), "indirect consumption preserves argument record/canaries");
        if (ordered) GP_REQUIRE(gp_ordered(memory, control, record_address, guard, first_orientation), "same-submission ordering round");
    } else printf("probe-vkgeometry: indexed-indirect SKIPPED: exact bounded argument preflight failed\n");
    GP_REQUIRE(gp_occlusion_reports(memory, control), "cumulative visibility counter semantics");
    GP_REQUIRE(gp_pending_condition(memory, control), "pending visibility condition retention");
    GP_REQUIRE(gp_fragment_depth(memory, control), "fragment-depth register groups");
    GP_REQUIRE(gfx_shader_failures() == shader_failures, "no translation failures");
    if (gp_passthrough) {
        GfxShaderAnswers answers = {0};
        answers.geometry_input = GFX_GEOMETRY_TRIANGLES;
        uint32_t length = nvn_geometry_control_u32(gp_control[2] + 0x704);
        const GfxShader *source = gfx_shader_get(GFX_STAGE_GS, gp_control[2], gp_code[2], length, NULL, &answers);
        GP_REQUIRE(source && gfx_shader_geometry(source) &&
                   gfx_shader_geometry(source)->version == GFX_GEOMETRY_PASSTHROUGH_VERSION,
                   "real portable shader/cache result");
        int owned = -1;
        GP_REQUIRE(gfx_shader_load_private(gfx_shader_input_id(source), &owned) == source && !owned,
                   "borrowed portable shader validates its stored source");
        GP_REQUIRE(gfx_shader_load_input(gfx_shader_input_id(source), 0) == source,
                   "portable input-ID lookup preserves its source");
    }
done:
    if (pool_live) backend->finish();
    if (command_live) {
        if (control) GP_CALL(nvnCommandBufferAddControlMemory, GP_U(&gp_command), GP_U(control), GP_COMMAND_CONTROL);
        GP_CALL(nvnCommandBufferFinalize, GP_U(&gp_command));
    }
    if (programs_live >= 2) GP_CALL(nvnProgramFinalize, GP_U(&gp_plain_program));
    if (programs_live >= 1) GP_CALL(nvnProgramFinalize, GP_U(&gp_full_program));
    if (texture_live) GP_CALL(nvnTextureFinalize, GP_U(&gp_color));
    if (pool_live) GP_CALL(nvnMemoryPoolFinalize, GP_U(&gp_memory_pool));
    if (device_live) GP_CALL(nvnDeviceFinalize, GP_U(&gp_device));
    if (control) mem_kernel_free(control, GP_COMMAND_CONTROL);
    vk_pipeline_shutdown(), vk_exec_draw_shutdown(), vk_exec_xfer_shutdown(), vk_backend_shutdown();
    long errors = vk_validation_errors_total();
    printf("probe-vkgeometry: %s (%u checks, %u failures, %ld validation errors, enabled %d)\n",
        gp_failures || errors ? "FAILED" : "passed", gp_checks, gp_failures, errors, cfg_bool("TOTK_EXPERIMENTAL_GEOMETRY"));
    printf("probe-vkgeometry: %s, user-c3 store, %s; ",
           gp_passthrough ? "portable triangles->triangle" : "ordinary points->triangle",
           ordered ? "explicit NVN dependency in one NVN submission" : "separate completed-submission indirect consumption");
    puts(getenv("DKB_PROBE_NATIVE_HIGH_VS") ? "native high-register VS with private spills; Maxwell GS/FS" :
         "no native lowering, NV passthrough extension or other input topologies");
    return gp_failures || errors;
}

int probe_vkgeometry(void) { return gp_run(0, 0); }
int probe_vkgeometry_passthrough(void) { return gp_run(1, 0); }
int probe_vkgeometry_ordering(void) { return gp_run(1, 1); }

// Authored Ampere fixture: a single active lane emits one triangle, including
// packed primitive bytes. Other lanes return before the wrapper's uniform export.
static void gp_mesh_program(void) {
    uint8_t *c = gp_control[0], *b = gp_code[0];
    memset(c,0,GP_CONTROL); memset(b,0,GP_CODE);
    gp_u32(b,1u|4u<<5|1u<<10); b[0x35]=0xf0; b[0x36]=0xf;
    unsigned at=0x80;
    #define MP(a,b0,c0) do { uint32_t w[4]={(a),(b0),(c0),0}; memcpy(b+at,w,16);at+=16; } while(0)
    MP(0x00007919,0,0); // lane ID
    MP(0x0000720c,255,0x03f05000); // P0 = lane != 0
    MP(0x0000094d,0,0x03800000); // other lanes return
    MP(0xff027923,0,0x7800); // R2 = draw's first + workgroup
    MP(0xff007927,2|(3u<<8),0x8800); // primitive count byte
    const float v[3][8]={{-.75f,-.75f,.25f,1,1,0,0,1},
                        {.75f,-.75f,.25f,1,1,0,0,1},
                        {0,.75f,.25f,1,1,0,0,1}};
    for(unsigned n=0;n<3;n++) {
        for(unsigned k=0;k<8;k++) {
            uint32_t f;memcpy(&f,&v[n][k],4);
            MP(0x00017802,f,0xf00);
            MP(0xff007927,1|((k*128+n*4)<<8),0xf800);
        }
        MP(0x00017802,n,0xf00);
        MP(0xff007927,1|((4+n)<<8),0x8000);
    }
    MP(0x0000794d,0,0x03800000);
    #undef MP
    gp_u32(c,0x98761234);gp_u32(c+4,0xc9);
    gp_u32(c+0x30,0xd8);gp_u32(c+0x38,at);
    c[0x56]=7;c[0x58]=32;c[0x5a]=16;c[0x60]=32;c[0x62]=1;
}

// Authored task fixture exports one mesh group per requested first index and
// a payload value consumed by the mesh primitive-count instruction.
static void gp_task_program(uint8_t *c, uint8_t *b) {
    memset(c,0,GP_CONTROL);memset(b,0,GP_CODE);
    gp_u32(b,1u|4u<<5|2u<<10);
    const uint32_t ins[][4]={
        {0x00007919,0,0,0}, {0x0000720c,255,0x03f05000,0}, {0x0000094d,0,0x03800000,0},
        {0xff027923,0,0x7800,0}, {0xff007927,2|(4u<<8),0xb800,0},
        {0x00017802,1,0xf00,0}, {0xff007927,1|(8u<<8),0xb800,0},
        {0x0000794d,0,0x03800000,0}};
    memcpy(b+0x80,ins,sizeof ins);
    gp_u32(c,0x98761234);gp_u32(c+4,0xc9);gp_u32(c+0x30,0xd8);gp_u32(c+0x38,0x80+sizeof ins);
    c[0x56]=6;c[0x58]=32;c[0x5a]=16;
}

int probe_vkmesh(void) {
    const GfxBackend *backend=&gfx_vulkan_backend;
    gp_checks = gp_failures = 0;
    uint64_t heap = 0, shader_failures = gfx_shader_failures();
    uint8_t *memory = NULL;
    void *control = NULL;
    int depth_live = 0;
    static _Alignas(16) NVNtexture depth;
    static _Alignas(16) uint8_t task_ctl[GP_CONTROL],task_code[GP_CODE];
    int device_live = 0, pool_live = 0, texture_live = 0, command_live = 0, programs_live = 0;
    GP_REQUIRE(!mem_set_heap_size(16ull << 20, &heap) && heap, "SetHeapSize");
    memory = (uint8_t *)(uintptr_t)heap;
    control = mem_kernel_alloc(GP_COMMAND_CONTROL, 16);
    GP_REQUIRE(control, "owned command control allocation");
    GP_CALL(nvnDeviceBuilderSetDefaults, GP_U(&gp_device_builder));
    GP_REQUIRE((uint8_t)GP_CALL(nvnDeviceInitialize, GP_U(&gp_device), GP_U(&gp_device_builder)), "DeviceInitialize");
    device_live = 1;
    GP_CALL(nvnMemoryPoolBuilderSetDefaults, GP_U(&gp_memory_builder));
    GP_CALL(nvnMemoryPoolBuilderSetDevice, GP_U(&gp_memory_builder), GP_U(&gp_device));
    GP_CALL(nvnMemoryPoolBuilderSetStorage, GP_U(&gp_memory_builder), GP_U(memory), GP_POOL);
    GP_CALL(nvnMemoryPoolBuilderSetFlags, GP_U(&gp_memory_builder),
        NVN_MEMORY_POOL_FLAGS_CPU_CACHED | NVN_MEMORY_POOL_FLAGS_GPU_CACHED);
    GP_REQUIRE((uint8_t)GP_CALL(nvnMemoryPoolInitialize, GP_U(&gp_memory_pool), GP_U(&gp_memory_builder)), "MemoryPoolInitialize");
    pool_live = 1;
    printf("probe-vkgeometry: device %s driver %#x core-validation-active %d\n", vk_ctx()->props.deviceName,
        vk_ctx()->props.driverVersion, vk_ctx()->validation);
    GP_CALL(nvnTextureBuilderSetDefaults, GP_U(&gp_texture_builder));
    GP_CALL(nvnTextureBuilderSetDevice, GP_U(&gp_texture_builder), GP_U(&gp_device));
    GP_CALL(nvnTextureBuilderSetTarget, GP_U(&gp_texture_builder), NVN_TEXTURE_TARGET_2D);
    GP_CALL(nvnTextureBuilderSetSize2D, GP_U(&gp_texture_builder), GP_WIDTH, GP_HEIGHT);
    GP_CALL(nvnTextureBuilderSetLevels, GP_U(&gp_texture_builder), 1);
    GP_CALL(nvnTextureBuilderSetFormat, GP_U(&gp_texture_builder), NVN_FORMAT_RGBA8);
    GP_CALL(nvnTextureBuilderSetStorage, GP_U(&gp_texture_builder), GP_U(&gp_memory_pool), GP_COLOR);
    uint64_t texture_bytes = GP_CALL(nvnTextureBuilderGetStorageSize, GP_U(&gp_texture_builder));
    GP_REQUIRE(texture_bytes && texture_bytes <= 0x10000, "bounded color storage");
    GP_REQUIRE((uint8_t)GP_CALL(nvnTextureInitialize, GP_U(&gp_color), GP_U(&gp_texture_builder)), "TextureInitialize");
    texture_live = 1;

    GP_CALL(nvnTextureBuilderSetFormat,GP_U(&gp_texture_builder),NVN_FORMAT_DEPTH32F);
    GP_CALL(nvnTextureBuilderSetStorage,GP_U(&gp_texture_builder),GP_U(&gp_memory_pool),0x80000);
    GP_REQUIRE((uint8_t)GP_CALL(nvnTextureInitialize,GP_U(&depth),GP_U(&gp_texture_builder)),"mesh depth target");
    depth_live=1;
    GP_REQUIRE(vk_ctx()->has_task_shader,"device enables task shaders");
    GP_REQUIRE(vk_ctx()->has_mesh_shader,"device enables mesh shaders");
    gp_mesh_program();gp_program(1,gp_control[1],gp_code[1]);
    NVNshaderData shaders[2]={{GP_U(gp_code[0]),gp_control[0]}, {GP_U(gp_code[1]),gp_control[1]}};
    GP_REQUIRE((uint8_t)GP_CALL(nvnProgramInitialize,GP_U(&gp_full_program),GP_U(&gp_device)),"mesh program initialization");
    programs_live=1;
    GP_REQUIRE((uint8_t)GP_CALL(nvnProgramSetShaders,GP_U(&gp_full_program),2,GP_U(shaders)),"native mesh program");
    GP_REQUIRE((uint8_t)GP_CALL(nvnCommandBufferInitialize,GP_U(&gp_command),GP_U(&gp_device)),"mesh command buffer");
    command_live=1;
    GP_CALL(nvnCommandBufferAddCommandMemory,GP_U(&gp_command),GP_U(&gp_memory_pool),GP_COMMAND,0x10000);
    uint32_t pixels[GP_WIDTH*GP_HEIGHT];int orientation;
    // Repeat each scene once: the first replay can request a background pipeline.
    for(unsigned test=0;test<8;test++) {
        if(test==2 || test==4 || test==6) {
            GP_CALL(nvnProgramFinalize,GP_U(&gp_full_program));programs_live=0;
            gp_mesh_program();
            gp_control[0][0x5e]=(test==2 || test==6);
            if(test==2 || test==6) {gp_u32(gp_code[0]+0x80+3*16+4,8u<<8);gp_u32(gp_code[0]+0x80+3*16+8,0x3800);}
            gp_task_program(task_ctl,task_code);
            NVNshaderData task_stages[3]={shaders[0],shaders[1],{GP_U(task_code),task_ctl}};
            GP_REQUIRE((uint8_t)GP_CALL(nvnProgramInitialize,GP_U(&gp_full_program),GP_U(&gp_device)),"task program init");
            programs_live=1;
            GP_REQUIRE((uint8_t)GP_CALL(nvnProgramSetShaders,GP_U(&gp_full_program),test==4 ? 2 : 3,GP_U(task_stages)),"task mesh program");
        }
        for(unsigned warm=0;warm<2;warm++) {
            gp_prefix(memory,control,0);
            const NVNtexture *color=&gp_color;
            GP_CALL(nvnCommandBufferSetRenderTargets,GP_U(&gp_command),1,GP_U(&color),0,GP_U(&depth),0);
            gp_cpu.v[0]=0x3f800000u;
            GP_CALL(nvnCommandBufferClearDepthStencil,GP_U(&gp_command),1,0,0);
            NVNdepthStencilState ds;GP_CALL(nvnDepthStencilStateSetDefaults,GP_U(&ds));
            GP_CALL(nvnDepthStencilStateSetDepthTestEnable,GP_U(&ds),1);
            GP_CALL(nvnDepthStencilStateSetDepthWriteEnable,GP_U(&ds),1);
            GP_CALL(nvnDepthStencilStateSetDepthFunc,GP_U(&ds),NVN_DEPTH_FUNC_ALWAYS);
            GP_CALL(nvnCommandBufferBindDepthStencilState,GP_U(&gp_command),GP_U(&ds));
            GP_CALL(nvnCommandBufferBindProgram,GP_U(&gp_command),GP_U(&gp_full_program),test==2 || test==3 || test>=6 ? 0xc2 : 0x82);
            if(test<4) GP_CALL(nvnCommandBufferDrawMeshTasks,GP_U(&gp_command),test%2 ? 0 : 1,1);
            else {
                static uint32_t args[4];args[0]=test%2 ? 0 : 1;args[1]=1;args[2]=0x11223344;args[3]=0x55667788;
                GP_CALL(nvnCommandBufferUpdateUniformBuffer,GP_U(&gp_command),GP_U(memory+GP_GUARD),16,0,16,GP_U(args));
                GP_CALL(nvnCommandBufferBarrier,GP_U(&gp_command),NVN_BARRIER_ORDER_PRIMITIVES_BIT|NVN_BARRIER_ORDER_INDIRECT_DATA_BIT);
                GP_CALL(nvnCommandBufferDrawMeshTasksIndirect,GP_U(&gp_command),GP_U(memory+GP_GUARD));
            }
            GP_REQUIRE(gp_submit(),"mesh submission completed");
        }
        if(!(test%2)) gp_pixels(pixels,0xff0000ffu,&orientation);
        else {
            NVNcopyRegion region={0,0,0,GP_WIDTH,GP_HEIGHT,1};
            memset(pixels,0x5a,sizeof pixels);
            GP_CALL(nvnTextureReadTexels,GP_U(&gp_color),0,GP_U(&region),GP_U(pixels));
            for(unsigned i=0;i<GP_WIDTH*GP_HEIGHT;i++) GP_REQUIRE(pixels[i]==0xffff0000u,"zero primitive count preserves clear");
        }
        float depth_pixels[GP_WIDTH*GP_HEIGHT];NVNcopyRegion region={0,0,0,GP_WIDTH,GP_HEIGHT,1};
        GP_CALL(nvnTextureReadTexels,GP_U(&depth),0,GP_U(&region),GP_U(depth_pixels));
        for(unsigned i=0;i<GP_WIDTH*GP_HEIGHT;i++)
            GP_REQUIRE(depth_pixels[i]==(pixels[i]==0xff0000ffu ? .25f : 1.f),"mesh writes matching depth");
    }
    GP_REQUIRE(gfx_shader_failures()==shader_failures,"mesh translation succeeded");
done:
    if (pool_live) backend->finish();
    if (command_live) {
        if (control) GP_CALL(nvnCommandBufferAddControlMemory, GP_U(&gp_command), GP_U(control), GP_COMMAND_CONTROL);
        GP_CALL(nvnCommandBufferFinalize, GP_U(&gp_command));
    }
    if (programs_live >= 2) GP_CALL(nvnProgramFinalize, GP_U(&gp_plain_program));
    if (programs_live >= 1) GP_CALL(nvnProgramFinalize, GP_U(&gp_full_program));
    if (depth_live) GP_CALL(nvnTextureFinalize,GP_U(&depth));
    if (texture_live) GP_CALL(nvnTextureFinalize, GP_U(&gp_color));
    if (pool_live) GP_CALL(nvnMemoryPoolFinalize, GP_U(&gp_memory_pool));
    if (device_live) GP_CALL(nvnDeviceFinalize, GP_U(&gp_device));
    if (control) mem_kernel_free(control, GP_COMMAND_CONTROL);
    vk_pipeline_shutdown(), vk_exec_draw_shutdown(), vk_exec_xfer_shutdown(), vk_backend_shutdown();
    long errors = vk_validation_errors_total();

    printf("probe-vkmesh: %s (%u checks, %u failures, %ld validation errors)\n",
           gp_failures || errors ? "FAILED" : "passed", gp_checks, gp_failures, errors);
    return gp_failures || errors;
}
