// SPDX-License-Identifier: MIT
// --probe-vkpool: original sampled-texture shader through the real NVN recorder and Vulkan replay.
// No game/census shader or direct descriptor injection. CPU preparation checks this exact instruction array.
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "cfg.h"
#include "host.h"
#include "nvn_api.h"
#include "vk_exec.h"
#include "tex.h"

#define NVN_PROC(n) void nvnp_##n(Cpu *c);
#include "nvn_procs.inc"
#undef NVN_PROC

// Original Maxwell: MOV32I R0,1.25; MOV32I R1,0.5; MOV R2,c0[0x20];
// TEX.B.2D.LZ R8..R11,[R0,R1],R2; MOV R4/R5,c0[0x10/0x14]; STG.E.B128 [R4],R8; EXIT.
// DKC1: zero root words, one storage buffer and one texture. Its handle is reflected to slot 0, not read as a pointer.
static const uint64_t pool_probe_code[] = {
    UINT64_C(0x001f8000fc0007e0), UINT64_C(0x0103fa000007f000), UINT64_C(0x0103f0000007f001), UINT64_C(0x4c98078000870002),
    UINT64_C(0x001f8000fc0007e0), UINT64_C(0xdeb80027a0270008), UINT64_C(0x4c98078000470004), UINT64_C(0x4c98078000570005),
    UINT64_C(0x001f8000fc0007e0), UINT64_C(0xeede200000070408), UINT64_C(0xe30000000007000f), UINT64_C(0x0000000000000000),
};

enum { POOL_BYTES = 0x100000, TABLE_A = 0x40000, TABLE_B = 0x50000,
       TABLE_REPEAT = 0x60000, TABLE_CLAMP = 0x70000, COMMAND_OFF = 0x80000,
       OUTPUT_OFF = 0xa0000, OUTPUT_BYTES = 0x10000, CONTROL_BYTES = 4096 };
#define U(p) ((uint64_t)(uintptr_t)(p))
#define OBJECT(type, name) static _Alignas(16) type name
OBJECT(NVNdeviceBuilder, device_builder);
OBJECT(NVNdevice, device);
OBJECT(NVNmemoryPoolBuilder, memory_builder);
OBJECT(NVNmemoryPool, memory_pool);
OBJECT(NVNtextureBuilder, texture_builder);
OBJECT(NVNtexture, red_texture);
OBJECT(NVNtexture, green_texture);
OBJECT(NVNtexture, pattern_texture);
OBJECT(NVNtexture, srgb_texture);
OBJECT(NVNtexture, typed_texture);
OBJECT(NVNtexture, array_texture);
OBJECT(NVNtexture, unused_depth_texture);
OBJECT(NVNtexture, alias_rgb9_texture);
OBJECT(NVNtexture, alias_r11_texture);
OBJECT(NVNsamplerBuilder, sampler_builder);
OBJECT(NVNsampler, repeat_sampler);
OBJECT(NVNsampler, clamp_sampler);
OBJECT(NVNtexturePool, texture_a);
OBJECT(NVNtexturePool, texture_b);
OBJECT(NVNsamplerPool, sampler_repeat);
OBJECT(NVNsamplerPool, sampler_clamp);
OBJECT(NVNprogram, program);
OBJECT(NVNcommandBuffer, command);
static _Alignas(16) uint8_t control[0x880];
static Cpu cpu;
static unsigned checks, failures;
static uint64_t unused_image_handle;

static uint64_t call(void (*fn)(Cpu *), const uint64_t a[8]) {
    memcpy(cpu.x, a, sizeof cpu.x[0] * 8);
    fn(&cpu);
    return cpu.x[0];
}
#define CALL(n, ...) call(nvnp_##n, (const uint64_t[8]){__VA_ARGS__})
#define REQUIRE(cond, text) do { checks++; if (!(cond)) { \
    printf("probe-vkpool: FAIL %s\n", text); failures++; goto done; } } while (0)

static int make_texture(NVNtexture *texture, uint64_t off, const uint8_t pixels[8]) {
    CALL(nvnTextureBuilderSetDevice, U(&texture_builder), U(&device));
    CALL(nvnTextureBuilderSetDefaults, U(&texture_builder));
    CALL(nvnTextureBuilderSetTarget, U(&texture_builder), NVN_TEXTURE_TARGET_2D);
    CALL(nvnTextureBuilderSetSize2D, U(&texture_builder), 2, 1);
    CALL(nvnTextureBuilderSetLevels, U(&texture_builder), 1);
    CALL(nvnTextureBuilderSetFormat, U(&texture_builder), texture == &srgb_texture ? NVN_FORMAT_RGBA8_SRGB :
         texture == &typed_texture ? NVN_FORMAT_RG16UI : NVN_FORMAT_RGBA8);
    CALL(nvnTextureBuilderSetStorage, U(&texture_builder), U(&memory_pool), off);
    uint64_t bytes = CALL(nvnTextureBuilderGetStorageSize, U(&texture_builder));
    if (!bytes || bytes > 0x10000) return 0;
    if (!(uint8_t)CALL(nvnTextureInitialize, U(texture), U(&texture_builder))) return 0;
    NVNcopyRegion region = {0, 0, 0, 2, 1, 1};
    CALL(nvnTextureWriteTexels, U(texture), 0, U(&region), U(pixels));
    return 1;
}

static int make_sampler(NVNsampler *sampler, int wrap) {
    CALL(nvnSamplerBuilderSetDevice, U(&sampler_builder), U(&device));
    CALL(nvnSamplerBuilderSetDefaults, U(&sampler_builder));
    CALL(nvnSamplerBuilderSetMinMagFilter, U(&sampler_builder), NVN_MIN_FILTER_NEAREST, NVN_MAG_FILTER_NEAREST);
    CALL(nvnSamplerBuilderSetWrapMode, U(&sampler_builder), wrap, NVN_WRAP_MODE_CLAMP_TO_EDGE, NVN_WRAP_MODE_CLAMP_TO_EDGE);
    return (uint8_t)CALL(nvnSamplerInitialize, U(sampler), U(&sampler_builder));
}

static int run_case(const char *name, uint8_t *memory, void *command_control, uint64_t handle,
                    const NVNtexturePool *const textures[3], const NVNsamplerPool *const samplers[3],
                    const uint32_t expected[3][4], unsigned phases, size_t stride) {
    const GfxBackend *backend = &gfx_vulkan_backend;
    memset(memory + OUTPUT_OFF, 0xa5, OUTPUT_BYTES);
    CALL(nvnMemoryPoolFlushMappedRange, U(&memory_pool), OUTPUT_OFF, OUTPUT_BYTES);
    // Re-adding this exact owned range retires the preceding recording only after its fence completed below.
    CALL(nvnCommandBufferAddControlMemory, U(&command), U(command_control), CONTROL_BYTES);
    CALL(nvnCommandBufferBeginRecording, U(&command));
    CALL(nvnCommandBufferBindProgram, U(&command), U(&program), NVN_SHADER_STAGE_COMPUTE_BIT);
    CALL(nvnCommandBufferBindTexture, U(&command), NVN_SHADER_STAGE_COMPUTE, 0, handle);
    for (unsigned phase = 0; phase < phases; phase++) {
        CALL(nvnCommandBufferSetTexturePool, U(&command), U(textures[phase]));
        CALL(nvnCommandBufferSetSamplerPool, U(&command), U(samplers[phase]));
        if(unused_image_handle) CALL(nvnCommandBufferBindImage,U(&command),NVN_SHADER_STAGE_COMPUTE,7,unused_image_handle);
        CALL(nvnCommandBufferBindStorageBuffer, U(&command), NVN_SHADER_STAGE_COMPUTE, 0,
             U(memory + OUTPUT_OFF + (phase + 1) * stride), 16);
        // SetPool alone changes descriptor identity: no handle/program bind or registration occurs between dispatches.
        for (unsigned repeat = 0; repeat < 2; repeat++) {
            CALL(nvnCommandBufferDispatchCompute, U(&command), 1, 1, 1);
        }
    }
    uint64_t commands = CALL(nvnCommandBufferEndRecording, U(&command));
    checks++;
    if (!commands) { printf("probe-vkpool: FAIL %s: no recording\n", name); failures++; return 0; }
    uint64_t fence = backend->submit(&commands, 1, rt_ticks());
    checks++;
    if (!backend->fence_wait(fence, UINT64_C(10000000000))) {
        printf("probe-vkpool: FAIL %s: fence did not complete\n", name); failures++; return 0;
    }
    backend->cpu_synced(fence);
    // The completion frontier publishes SSBO writes before fence_wait returns. Compare every word and untouched byte.
    unsigned before = failures;
    for (unsigned phase = 0; phase < phases; phase++) {
        const uint32_t *actual = (const uint32_t *)(memory + OUTPUT_OFF + (phase + 1) * stride);
        for (unsigned component = 0; component < 4; component++) {
            checks++;
            if (actual[component] != expected[phase][component]) {
                printf("probe-vkpool: FAIL %s phase %u component %u: %08x expected %08x\n",
                    name, phase, component, actual[component], expected[phase][component]);
                failures++;
            }
        }
    }
    int canary_ok = 1;
    for (size_t off = 0; off < OUTPUT_BYTES; off++) {
        size_t slot = off / stride;
        if (slot >= 1 && slot <= phases && off % stride < 16) continue;
        if (memory[OUTPUT_OFF + off] != 0xa5) { canary_ok = 0; break; }
    }
    checks++;
    if (!canary_ok) { printf("probe-vkpool: FAIL %s: output canary changed\n", name); failures++; }
    printf("probe-vkpool: %s: %s (%u pool selections, two dispatches each)\n", name,
        failures == before ? "passed" : "FAILED", phases);
    return 1;   // A semantic failure is accumulated; the following independent case still runs.
}

void vk_exec_draw_shutdown(void);
void vk_exec_xfer_shutdown(void);

// Native TEX.B and uniform-handle TEX must sample the same authored pattern as
// the Maxwell control, including a sampler-pool change with an unchanged handle.
static int run_warp_reductions(uint8_t *memory,void *command_control) {
    uint32_t native[][4]={
        {0x00007919,0,0x2100,0}, // R0 = local invocation X
        {0x00017802,0x80000001,0xf00,0},
        {0x00027824,0x10000000,0x078e0001,0}, // R2 = lane * 0x10000000 + R1
        {0x020073c4,0,0x10200,0}, // REDUX to UR0
        {0x00087c02,0,0x08000f00,0}, // R8 = UR0
        {0x00097202,2,0xf00,0}, {0x000a7202,0,0xf00,0},
        {0x000b7802,0xabcdef12,0xf00,0},
        {0x00047a02,0x400,0xf00,0}, {0x00057a02,0x500,0xf00,0},
        {0x00047825,16,0x078e0004,0}, // R4:R5 += lane * 16, disjoint stores
        {0x04007386,8,0x0010ad00,0}, {0x0000794d,0,0x03800000,0}
    };
    uint32_t ctl[0xd8/4]={0};
    ctl[0]=0x98761234; ctl[1]=0xc9; ctl[0x30/4]=sizeof ctl; ctl[0x38/4]=sizeof native;
    ctl[0x5c/4]=ctl[0x60/4]=1; ((uint8_t *)ctl)[0xb2]=1;
    const uint32_t modes[]={0xc000,0x10000,0x10200,0x14000,0x14200};
    const unsigned counts[]={7,17,32};
    const GfxBackend *backend=&gfx_vulkan_backend;
    for(unsigned m=0;m<5;m++) for(unsigned n=0;n<3;n++) {
        unsigned lanes=counts[n]; uint32_t mode=modes[m],operation=mode>>14;
        int sign=(mode&0x200)!=0;
        uint32_t want=operation==4?(sign?0x7fffffff:0xffffffff):operation==5&&sign?0x80000000:0;
        for(unsigned l=0;l<lanes;l++) {
            uint32_t v=l*UINT32_C(0x10000000)+UINT32_C(0x80000001);
            if(operation==3)want+=v;
            else if(operation==4) { if(sign?(int32_t)v<(int32_t)want:v<want)want=v; }
            else if(sign?(int32_t)v>(int32_t)want:v>want)want=v;
        }
        native[3][2]=mode; ctl[0x58/4]=lanes;
        NVNshaderData shader={U(native),(const uint8_t *)ctl};
        if(!(uint8_t)CALL(nvnProgramSetShaders,U(&program),1,U(&shader)))return 0;
        memset(memory+OUTPUT_OFF,0xa5,OUTPUT_BYTES);
        CALL(nvnMemoryPoolFlushMappedRange,U(&memory_pool),OUTPUT_OFF,OUTPUT_BYTES);
        CALL(nvnCommandBufferAddControlMemory,U(&command),U(command_control),CONTROL_BYTES);
        CALL(nvnCommandBufferBeginRecording,U(&command));
        CALL(nvnCommandBufferBindProgram,U(&command),U(&program),NVN_SHADER_STAGE_COMPUTE_BIT);
        CALL(nvnCommandBufferBindStorageBuffer,U(&command),NVN_SHADER_STAGE_COMPUTE,0,U(memory+OUTPUT_OFF),lanes*16);
        CALL(nvnCommandBufferDispatchCompute,U(&command),1,1,1);
        uint64_t commands=CALL(nvnCommandBufferEndRecording,U(&command));
        if(!commands)return 0;
        uint64_t fence=backend->submit(&commands,1,rt_ticks());
        if(!backend->fence_wait(fence,UINT64_C(10000000000)))return 0;
        backend->cpu_synced(fence);
        for(unsigned l=0;l<lanes;l++) {
            const uint32_t expected[]={want,l*UINT32_C(0x10000000)+UINT32_C(0x80000001),l,0xabcdef12};
            const uint32_t *got=(const uint32_t *)(memory+OUTPUT_OFF+l*16);
            for(unsigned k=0;k<4;k++) { checks++; if(got[k]!=expected[k]) {
                failures++; printf("probe-vkpool: FAIL REDUX mode %#x lanes %u lane %u word %u: %#x expected %#x\n",
                                  mode,lanes,l,k,got[k],expected[k]);
            } }
        }
        int canary=1; for(unsigned i=lanes*16;i<OUTPUT_BYTES;i++)if(memory[OUTPUT_OFF+i]!=0xa5)canary=0;
        checks++; if(!canary) { failures++; puts("probe-vkpool: FAIL REDUX output bounds"); }
    }
    return 1;
}

// Concurrent integer atomics through a uniform 64-bit address and byte offset.
// Check the atomic result and every untouched byte after a fence.
static int run_uniform_reductions(uint8_t *memory,void *command_control) {
    uint32_t native[][4]={
        {0x00007919,0,0x2100,0}, // local X
        {0x00017802,0x80000001,0xf00,0},
        {0x00027824,0x10000000,0x078e0001,0},
        {0x00027ab9,0x400,0xa00,0}, // ULDC.64 UR2,c0[0x10]
        {0xff00798e,2,0x0c90e302,0}, // RED.MIN.S32 [UR2],R2
        {0x0000794d,0,0x03800000,0}
    };
    uint32_t ctl[0xd8/4]={0};
    ctl[0]=0x98761234; ctl[1]=0xc9; ctl[0x30/4]=sizeof ctl; ctl[0x38/4]=sizeof native;
    ctl[0x58/4]=32; ctl[0x5c/4]=ctl[0x60/4]=1; ((uint8_t *)ctl)[0xb2]=1;
    const GfxBackend *backend=&gfx_vulkan_backend;
    for(unsigned sign=0;sign<2;sign++) for(unsigned op=0;op<3;op++) for(int offset=4;offset<=20;offset+=16) {
        uint32_t initial=op==1?(sign?0x7fffffff:0xffffffff):op==2&&sign?0x80000000:0;
        uint32_t expected=initial;
        for(unsigned group=0;group<4;group++) for(unsigned l=0;l<32;l++) {
            uint32_t v=l*UINT32_C(0x10000000)+UINT32_C(0x80000001);
            if(op==0)expected+=v;
            else if(op==1) { if(sign?(int32_t)v<(int32_t)expected:v<expected)expected=v; }
            else if(sign?(int32_t)v>(int32_t)expected:v>expected)expected=v;
        }
        native[4][1]=2|((uint32_t)offset&0xffffff)<<8;
        native[4][2]=0x0c10e102|(sign<<9)|(op<<23);
        NVNshaderData shader={U(native),(const uint8_t *)ctl};
        if(!(uint8_t)CALL(nvnProgramSetShaders,U(&program),1,U(&shader)))return 0;
        memset(memory+OUTPUT_OFF,0xa5,OUTPUT_BYTES);
        const unsigned target=offset;
        memcpy(memory+OUTPUT_OFF+target,&initial,4);
        CALL(nvnMemoryPoolFlushMappedRange,U(&memory_pool),OUTPUT_OFF,OUTPUT_BYTES);
        CALL(nvnCommandBufferAddControlMemory,U(&command),U(command_control),CONTROL_BYTES);
        CALL(nvnCommandBufferBeginRecording,U(&command));
        CALL(nvnCommandBufferBindProgram,U(&command),U(&program),NVN_SHADER_STAGE_COMPUTE_BIT);
        CALL(nvnCommandBufferBindStorageBuffer,U(&command),NVN_SHADER_STAGE_COMPUTE,0,U(memory+OUTPUT_OFF),32);
        CALL(nvnCommandBufferDispatchCompute,U(&command),4,1,1);
        uint64_t commands=CALL(nvnCommandBufferEndRecording,U(&command));
        if(!commands)return 0;
        uint64_t fence=backend->submit(&commands,1,rt_ticks());
        if(!backend->fence_wait(fence,UINT64_C(10000000000)))return 0;
        backend->cpu_synced(fence);
        uint32_t actual; memcpy(&actual,memory+OUTPUT_OFF+target,4);
        checks++; if(actual!=expected) {
            failures++; printf("probe-vkpool: FAIL uniform RED sign %u op %u offset %d: %#x expected %#x\n",
                              sign,op,offset,actual,expected);
        }
        int canary=1; for(unsigned i=0;i<OUTPUT_BYTES;i++)
            if((i<target||i>=target+4)&&memory[OUTPUT_OFF+i]!=0xa5)canary=0;
        checks++; if(!canary) { failures++; puts("probe-vkpool: FAIL uniform RED output bounds"); }
    }
    return 1;
}

static int run_feedback_views(void) {
    if(vk_ctx()->feedback!=VK_FEEDBACK_LAYOUT) {
        puts("probe-vkpool: feedback view cases unavailable on this device"); return 1;
    }
    const tex_t *textures[]={(const tex_t *)&red_texture,(const tex_t *)&srgb_texture,
                             (const tex_t *)&unused_depth_texture};
    const NVNcopyRegion region={0,0,0,2,1,1};
    const float depth[]={0.25f,0.75f};
    CALL(nvnTextureWriteTexels,U(&unused_depth_texture),0,U(&region),U(depth));
    for(unsigned n=0;n<3;n++) {
        uint8_t before[8],after[8];
        if(!vk_texture_read_image(textures[n],NULL,&region,before,8,8))return 0;
        const VkTexImage *img=vk_texture_get(textures[n]);
        if(!img||!img->fb_usage)return 0;
        VkImageView view=vk_exec_target_view(img,img->format,VK_IMAGE_VIEW_TYPE_2D,img->aspect,0,0,1,0);
        VkCommandBuffer cb=vk_upload_begin();
        VkImageMemoryBarrier2 barrier={.sType=VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER_2,
            .srcStageMask=VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT,.srcAccessMask=VK_ACCESS_2_MEMORY_WRITE_BIT,
            .dstStageMask=VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT,
            .dstAccessMask=VK_ACCESS_2_MEMORY_READ_BIT|VK_ACCESS_2_MEMORY_WRITE_BIT,
            .oldLayout=VK_IMAGE_LAYOUT_GENERAL,.newLayout=VK_IMAGE_LAYOUT_ATTACHMENT_FEEDBACK_LOOP_OPTIMAL_EXT,
            .srcQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,.dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,
            .image=img->image,.subresourceRange={img->aspect,0,1,0,1}};
        VkDependencyInfo dependency={.sType=VK_STRUCTURE_TYPE_DEPENDENCY_INFO,
            .imageMemoryBarrierCount=1,.pImageMemoryBarriers=&barrier};
        vkCmdPipelineBarrier2(cb,&dependency);
        VkRenderingAttachmentInfo attachment={.sType=VK_STRUCTURE_TYPE_RENDERING_ATTACHMENT_INFO,
            .imageView=view,.imageLayout=barrier.newLayout,.loadOp=VK_ATTACHMENT_LOAD_OP_LOAD,
            .storeOp=VK_ATTACHMENT_STORE_OP_STORE};
        VkRenderingInfo rendering={.sType=VK_STRUCTURE_TYPE_RENDERING_INFO,
            .renderArea={{0,0},{2,1}},.layerCount=1};
        if(n==2)rendering.pDepthAttachment=&attachment;
        else rendering.colorAttachmentCount=1,rendering.pColorAttachments=&attachment;
        vkCmdBeginRendering(cb,&rendering); vkCmdEndRendering(cb);
        barrier.oldLayout=barrier.newLayout; barrier.newLayout=VK_IMAGE_LAYOUT_GENERAL;
        vkCmdPipelineBarrier2(cb,&dependency);
        vk_upload_end(); vk_upload_flush(1);
        if(!vk_texture_read_image(textures[n],NULL,&region,after,8,8))return 0;
        checks++; if(memcmp(before,after,8)) {
            failures++; printf("probe-vkpool: FAIL feedback attachment format %u changed pixels\n",img->format);
        }
    }
    return 1;
}

static int run_native_textures(uint8_t *memory,void *command_control,uint64_t handle,size_t stride) {
    uint32_t native[][4]={
        {0x00007802,0x3fa00000,0xf00,0}, // R0 = 1.25
        {0x00017802,0x3f000000,0xf00,0}, // R1 = .5
        {0x00027a02,0x800,0xf00,0},     // R2 = c0[0x20] texture handle
        {0x00087361,0x28000002,0x008e0f0a,0}, // TEX.B unpacked 2D.LZ -> R8,R9 | R10,R11
        {0x00047a02,0x400,0xf00,0},     // R4/R5 = c0[0x10/0x14] storage address
        {0x00057a02,0x500,0xf00,0},
        {0x04007386,8,0x0010ad00,0},    // STG.E.128 [R4], R8..R11
        {0x0000794d,0,0x03800000,0},
    };
    uint32_t ctl[0xd8/4]={0};
    ctl[0]=0x98761234; ctl[1]=0xc9; ctl[0x30/4]=sizeof ctl; ctl[0x38/4]=sizeof native;
    ctl[0x58/4]=ctl[0x5c/4]=ctl[0x60/4]=1;
    ((uint8_t *)ctl)[0xb2]=1; ((uint8_t *)ctl)[0xb3]=1;
    const NVNtexturePool *tp[3]={&texture_a,&texture_a,&texture_a};
    const NVNsamplerPool *sp[3]={&sampler_repeat,&sampler_clamp,&sampler_repeat};
    const uint32_t expected[3][4]={{0x3f800000,0,0,0x3f800000},
        {0,0x3f800000,0,0x3f800000},{0x3f800000,0,0,0x3f800000}};
    for (unsigned variant=0;variant<2;variant++) {
        if (variant) {
            native[2][0]=0x00007ab9; native[2][2]=0x800; // ULDC.32 UR0,c0[0x20]
            native[3][0]=0x00087f60; native[3][1]=0x30000001; // uniform handle UR0, packed R0|R1
        }
        NVNshaderData shader={U(native),(const uint8_t *)ctl};
        if (!(uint8_t)CALL(nvnProgramSetShaders,U(&program),1,U(&shader))) return 0;
        if (!run_case(variant?"NVN2 uniform handle":"NVN2 per-lane handle",memory,command_control,
                      handle,tp,sp,expected,3,stride)) return 0;
    }
    return 1;
}

static int run_array_gather(uint8_t *memory,void *command_control,uint64_t handle,size_t stride) {
    uint32_t native[][4]={
        {0x00007802,0,0xf00,0}, // integer array layer
        {0x00017802,0x3f000000,0xf00,0}, {0x00027802,0x3f000000,0xf00,0},
        {0x00087b63,0xb0000802,0x000e0f0a,0}, // TLD4.R.2D.ARRAY, layer/X in R0:R1, Y in R2
        {0x00047a02,0x400,0xf00,0}, {0x00057a02,0x500,0xf00,0},
        {0x04007386,8,0x0010ad00,0}, {0x0000794d,0,0x03800000,0}
    };
    uint32_t ctl[0xd8/4]={0};
    ctl[0]=0x98761234; ctl[1]=0xc9; ctl[0x30/4]=sizeof ctl; ctl[0x38/4]=sizeof native;
    ctl[0x58/4]=ctl[0x5c/4]=ctl[0x60/4]=1; ((uint8_t *)ctl)[0xb2]=1; ((uint8_t *)ctl)[0xb3]=1;
    const NVNtexturePool *tp[3]={&texture_a,&texture_a,&texture_a};
    const NVNsamplerPool *sp[3]={&sampler_repeat,&sampler_repeat,&sampler_repeat};
    for(unsigned layer=0;layer<2;layer++) {
        native[0][1]=layer;
        const uint32_t expected[3][4]={{layer?0:0x3f800000,layer?0x3f800000:0,layer?0x3f800000:0,layer?0:0x3f800000}};
        NVNshaderData shader={U(native),(const uint8_t *)ctl};
        if(!(uint8_t)CALL(nvnProgramSetShaders,U(&program),1,U(&shader)))return 0;
        if(!run_case(layer?"native array gather layer 1":"native array gather layer 0",memory,
                     command_control,handle,tp,sp,expected,1,stride))return 0;
    }
    return 1;
}

static int make_array_texture(void) {
    CALL(nvnTextureBuilderSetDevice,U(&texture_builder),U(&device));
    CALL(nvnTextureBuilderSetDefaults,U(&texture_builder));
    CALL(nvnTextureBuilderSetTarget,U(&texture_builder),NVN_TEXTURE_TARGET_2D_ARRAY);
    CALL(nvnTextureBuilderSetSize3D,U(&texture_builder),2,1,2);
    CALL(nvnTextureBuilderSetLevels,U(&texture_builder),1);
    CALL(nvnTextureBuilderSetFormat,U(&texture_builder),NVN_FORMAT_RGBA8);
    CALL(nvnTextureBuilderSetStorage,U(&texture_builder),U(&memory_pool),0xd0000);
    uint64_t bytes=CALL(nvnTextureBuilderGetStorageSize,U(&texture_builder));
    if(!bytes || bytes>0x10000 || !(uint8_t)CALL(nvnTextureInitialize,U(&array_texture),U(&texture_builder)))return 0;
    const uint8_t pixels[16]={255,0,0,255,0,255,0,255,0,0,255,255,255,255,255,255};
    NVNcopyRegion region={0,0,0,2,1,2};
    CALL(nvnTextureWriteTexels,U(&array_texture),0,U(&region),U(pixels));
    return 1;
}

// Distinct texels and nonzero signed offsets expose gather order, FP16 packing
// and texel-fetch offset errors through real shader translation and GPU readback.
static int run_postprocess_fetches(uint8_t *memory,void *command_control,uint64_t handle,size_t stride) {
    uint32_t native[][4]={
        {0x00007802,0x3e800000,0xf00,0}, {0x00017802,0x3f000000,0xf00,0},
        {0x00027802,0,0xf00,0}, {0x00037802,0,0xf00,0},
        {0x000a7802,0xabcdef01,0xf00,0}, {0x000b7802,0xabcdef02,0xf00,0},
        {0x00087b63,0x30000802,0x000eaf09,0}, // TLD4.PTP.F16, R8/R9 hold four half results
        {0x000b7202,11,0xf00,0}, // retain the fourth output word
        {0x00287a02,0x400,0xf00,0}, {0x00297a02,0x500,0xf00,0},
        {0x28007386,8,0x0010ad00,0}, {0x0000794d,0,0x03800000,0}
    };
    uint32_t ctl[0xd8/4]={0};
    ctl[0]=0x98761234; ctl[1]=0xc9; ctl[0x30/4]=sizeof ctl; ctl[0x38/4]=sizeof native;
    ctl[0x58/4]=ctl[0x5c/4]=ctl[0x60/4]=1; ((uint8_t *)ctl)[0xb2]=1; ((uint8_t *)ctl)[0xb3]=1;
    const NVNtexturePool *tp[3]={&texture_a,&texture_a,&texture_a};
    const NVNsamplerPool *sp[3]={&sampler_repeat,&sampler_repeat,&sampler_repeat};
    for(unsigned variant=0;variant<7;variant++) {
        // PTP applies each offset to i0,j0, not to the four ordinary gather neighbors.
        // Four zero offsets therefore fetch the same red texel four times.
        uint32_t expected[3][4]={{0x3c003c00,0x3c003c00,0xabcdef01,0xabcdef02}};
        if(variant==1) {
            native[2][1]=0x00010001; native[3][1]=0x003f0000;
            expected[0][0]=0; expected[0][1]=0x00003c00; // green, green, red, green
        } else if(variant>=5) {
            const uint32_t amounts[]={31,32,33,0};
            for(unsigned k=0;k<4;k++) {
                uint32_t move[4]={0x00007802,amounts[k],0xf00,0};
                uint32_t funnel[4]={0xff007419|((8+k)<<16),0x80000001,
                                    variant==5?0x00010600:0x00010e00,0};
                memcpy(native[2*k],move,sizeof move); memcpy(native[2*k+1],funnel,sizeof funnel);
                expected[0][k]=variant==5 && amounts[k]>=32?0:UINT32_C(0x80000001)<<(amounts[k]&31);
            }
        } else if(variant==4) {
            const uint32_t shifts[][4]={
                {0x00017882,0x81234567,0,0}, // UMOV UR1
                {0x01117899,3,0x0800063f,0}, // USHF.L UR17,UR1,3,URZ
                {0x11167899,4,0x0800163f,0}, // USHF.R UR22,UR17,4,URZ
                {0x00007c82,22,0x08000000,0}, // UMOV UR0,UR22
                {0x00087c02,0,0x08000f00,0},
                {0x00097802,0,0xf00,0}, {0x000a7802,0xabcdef01,0xf00,0}
            };
            memcpy(native,shifts,sizeof shifts);
            native[7][0]=0x000b7802; native[7][1]=0xabcdef02;
            expected[0][0]=(UINT32_C(0x81234567)<<3)>>4; expected[0][1]=0;
        } else if(variant>=2) {
            native[0][1]=variant==2?0:1; native[1][1]=0;
            native[2][1]=variant==2?1:15; // signed four-bit X offset +1/-1
            native[6][0]=0x00087b66; native[6][1]=0x30000802; native[6][2]=0x008e1f0a;
            expected[0][0]=variant==2?0:0x3f800000;
            expected[0][1]=variant==2?0x3f800000:0;
            expected[0][2]=0; expected[0][3]=0x3f800000;
        }
        NVNshaderData shader={U(native),(const uint8_t *)ctl};
        if(!(uint8_t)CALL(nvnProgramSetShaders,U(&program),1,U(&shader)))return 0;
        const char *names[]={"half gather zero offsets","half gather signed per-texel offsets",
                             "texel fetch positive offset","texel fetch negative offset","uniform shifts through UR17 and UR22",
                             "clamped immediate funnel shifts","wrapped immediate funnel shifts"};
        if(!run_case(names[variant],memory,command_control,handle,tp,sp,expected,1,stride))return 0;
    }
    return 1;
}

static int run_sampled_component_types(uint8_t *memory,void *command_control,uint64_t handle,size_t stride,int ti) {
    uint32_t native[][4]={
        {0x00007802,1,0xf00,0},{0x00017802,0,0xf00,0},{0x00027802,15,0xf00,0},
        {0x00087b66,0x30000802,0x008e1f0a,0}, // TLDS.AOFFI: texel (1,0) plus (-1,0)
        {0x00287a02,0x400,0xf00,0},{0x00297a02,0x500,0xf00,0},
        {0x28007386,8,0x0010ad00,0},{0x0000794d,0,0x03800000,0}
    };
    uint32_t ctl[0xd8/4]={0};
    ctl[0]=0x98761234; ctl[1]=0xc9; ctl[0x30/4]=sizeof ctl; ctl[0x38/4]=sizeof native;
    ctl[0x58/4]=ctl[0x5c/4]=ctl[0x60/4]=1; ((uint8_t *)ctl)[0xb2]=1; ((uint8_t *)ctl)[0xb3]=1;
    NVNshaderData shader={U(native),(const uint8_t *)ctl};
    if (!(uint8_t)CALL(nvnProgramSetShaders,U(&program),1,U(&shader))) return 0;
    const int formats[]={NVN_FORMAT_RG16UI,NVN_FORMAT_RG16I,NVN_FORMAT_RG16F,NVN_FORMAT_RG16UI};
    const uint32_t values[][4]={{0x3c00,0xc000,0,1},{0x3c00,0xffffc000,0,1},
                              {0x3f800000,0xc0000000,0,0x3f800000},{0x3c00,0xc000,0,1}};
    const uint16_t pixels[]={0x3c00,0xc000,0x1234,0x5678};
    NVNcopyRegion region={0,0,0,2,1,1};
    CALL(nvnTextureWriteTexels,U(&typed_texture),0,U(&region),U(pixels));
    const NVNtexturePool *tp[3]={&texture_a,&texture_a,&texture_a};
    const NVNsamplerPool *sp[3]={&sampler_repeat,&sampler_repeat,&sampler_repeat};
    for(unsigned phase=0;phase<4;phase++) {
        NVNtextureView view;
        CALL(nvnTextureViewSetDefaults,U(&view));
        CALL(nvnTextureViewSetFormat,U(&view),formats[phase]);
        CALL(nvnTexturePoolRegisterTexture,U(&texture_a),ti,U(&typed_texture),U(&view));
        uint32_t expected[3][4]={0}; memcpy(expected[0],values[phase],sizeof values[phase]);
        if (!run_case("sampled uint/sint/float/uint views",memory,command_control,handle,tp,sp,expected,1,stride)) return 0;
    }
    return 1;
}

static int run_descriptor_format_alias(uint8_t *memory,void *command_control,uint64_t handle,size_t stride,int ti) {
    int live=0,ok=0;
    const VkFormat valid[][2]={{VK_FORMAT_B10G11R11_UFLOAT_PACK32,VK_FORMAT_E5B9G9R9_UFLOAT_PACK32},
        {VK_FORMAT_R16G16_UINT,VK_FORMAT_R32_UINT},{VK_FORMAT_R8G8B8A8_SRGB,VK_FORMAT_R8G8B8A8_UNORM}};
    const VkFormat invalid[][2]={{VK_FORMAT_R8_UNORM,VK_FORMAT_D32_SFLOAT},
        {VK_FORMAT_D32_SFLOAT,VK_FORMAT_R32_UINT},{VK_FORMAT_D32_SFLOAT,VK_FORMAT_D16_UNORM},
        {VK_FORMAT_R16_UINT,VK_FORMAT_R32_UINT},{VK_FORMAT_BC1_RGBA_UNORM_BLOCK,VK_FORMAT_R32G32_UINT}};
    for(unsigned i=0;i<sizeof valid/sizeof *valid;i++) {
        checks++; if(!tex_vk_color_view_compatible(valid[i][0],valid[i][1]))failures++;
    }
    for(unsigned i=0;i<sizeof invalid/sizeof *invalid;i++) {
        checks++; if(tex_vk_color_view_compatible(invalid[i][0],invalid[i][1]))failures++;
    }
    CALL(nvnTextureBuilderSetDefaults,U(&texture_builder));
    CALL(nvnTextureBuilderSetDevice,U(&texture_builder),U(&device));
    CALL(nvnTextureBuilderSetTarget,U(&texture_builder),NVN_TEXTURE_TARGET_2D);
    CALL(nvnTextureBuilderSetSize2D,U(&texture_builder),2,1);
    CALL(nvnTextureBuilderSetLevels,U(&texture_builder),1);
    CALL(nvnTextureBuilderSetStorage,U(&texture_builder),U(&memory_pool),0xf0000);
    CALL(nvnTextureBuilderSetFormat,U(&texture_builder),NVN_FORMAT_R11G11B10F);
    if(!(uint8_t)CALL(nvnTextureInitialize,U(&alias_r11_texture),U(&texture_builder)))goto done;
    live=1;
    // RGB9E5: exponent 16, mantissas 256/128/64 -> exactly 1/.5/.25.
    // Store these raw bits in the backing image, as a shader writing an R32UI view would.
    const uint32_t pixels[2]={0x81010100,0x81010100};
    NVNcopyRegion region={0,0,0,2,1,1};
    CALL(nvnTextureWriteTexels,U(&alias_r11_texture),0,U(&region),U(pixels));
    CALL(nvnTextureBuilderSetFormat,U(&texture_builder),NVN_FORMAT_RGB9E5F);
    if(!(uint8_t)CALL(nvnTextureInitialize,U(&alias_rgb9_texture),U(&texture_builder)))goto done;
    CALL(nvnTexturePoolRegisterTexture,U(&texture_a),ti,U(&alias_rgb9_texture),0);
    CALL(nvnTextureFinalize,U(&alias_rgb9_texture)); // descriptor survives its texture wrapper
    NVNshaderData shader={U(pool_probe_code),control};
    if(!(uint8_t)CALL(nvnProgramSetShaders,U(&program),1,U(&shader)))goto done;
    const NVNtexturePool *tp[3]={&texture_a,&texture_a,&texture_a};
    const NVNsamplerPool *sp[3]={&sampler_repeat,&sampler_repeat,&sampler_repeat};
    const uint32_t expected[3][4]={{0x3f800000,0x3f000000,0x3e800000,0x3f800000}};
    ok=run_case("RGB9E5 descriptor over live R11 backing",memory,command_control,handle,tp,sp,expected,1,stride);
done:
    if(live) CALL(nvnTextureFinalize,U(&alias_r11_texture));
    return ok;
}

static int run_native_wide(uint8_t *memory,void *command_control,uint64_t handle,size_t stride) {
    uint32_t native[][4]={
        {0x00047802,0xfffffff1,0xf00,0}, {0x000c7802,0xffffffff,0xf00,0},
        {0x000d7802,0x12345678,0xf00,0},
        {0x04087825,0x10001,0x078e000c,0}, // R8:R9 = R4 * 65537 + R12:R13
        {0x00087202,8,0xf00,0}, {0x00097202,9,0xf00,0}, // register control; changed to UR reads below
        {0x000a7802,0xabcdef01,0xf00,0}, {0x000b7802,0xabcdef02,0xf00,0},
        {0x00287a02,0x400,0xf00,0}, {0x00297a02,0x500,0xf00,0},
        {0x28007386,8,0x0010ad00,0}, {0x0000794d,0,0x03800000,0}
    };
    uint32_t ctl[0xd8/4]={0};
    ctl[0]=0x98761234; ctl[1]=0xc9; ctl[0x30/4]=sizeof ctl; ctl[0x38/4]=sizeof native;
    ctl[0x58/4]=ctl[0x5c/4]=ctl[0x60/4]=1; ((uint8_t *)ctl)[0xb2]=1;
    const NVNtexturePool *tp[3]={&texture_a,&texture_a,&texture_a};
    const NVNsamplerPool *sp[3]={&sampler_repeat,&sampler_repeat,&sampler_repeat};
    const uint64_t product=UINT64_C(0xfffffff1)*0x10001+UINT64_C(0x12345678ffffffff);
    const uint32_t expected[3][4]={{(uint32_t)product,(uint32_t)(product>>32),0xabcdef01,0xabcdef02}};
    for (unsigned variant=0;variant<2;variant++) {
        if (variant) {
            for (unsigned n=0;n<3;n++) native[n][0]|=0x80, native[n][2]=0; // UMOV
            native[3][0]|=0x80; native[3][2]|=0x08000000; // UIMAD.WIDE
            for (unsigned n=4;n<6;n++) native[n][0]=(native[n][0]&~0xfffU)|0xc02, native[n][2]=0x08000f00;
        }
        NVNshaderData shader={U(native),(const uint8_t *)ctl};
        if (!(uint8_t)CALL(nvnProgramSetShaders,U(&program),1,U(&shader))) return 0;
        if (!run_case(variant?"NVN2 uniform wide immediate":"NVN2 wide immediate",memory,command_control,
                      handle,tp,sp,expected,1,stride)) return 0;
    }
    return 1;
}

// A real NVN2 surface store through a UNORM view of an sRGB image. The values
// and instructions are authored here, so this exercises lowering, translation,
// descriptor selection and GPU readback without a game shader or dummy output.
static int run_srgb_store(uint8_t *memory, void *command_control, int ti) {
    static const uint32_t native[][4] = {
        {0x00007802, 0,          0xf00, 0}, // R0/R1: pixel (0,0)
        {0x00017802, 0,          0xf00, 0},
        {0x00047802, 0x3e800000, 0xf00, 0}, // R4..R7: .25, .5, .75, 1
        {0x00057802, 0x3f000000, 0xf00, 0},
        {0x00067802, 0x3f400000, 0xf00, 0},
        {0x00077802, 0x3f800000, 0xf00, 0},
        {0x00007b9b, 0x60000404, 0x00100f00, 0}, // SUST.P.2D c0[0x10], [R0,R1], R4..R7
        {0x0000794d, 0, 0x03800000, 0},
    };
    static uint32_t ctl[0xd8 / 4];
    memset(ctl, 0, sizeof ctl);
    ctl[0]=0x98761234; ctl[1]=0xc9; ctl[0x30/4]=sizeof ctl; ctl[0x38/4]=sizeof native;
    ctl[0x58/4]=ctl[0x5c/4]=ctl[0x60/4]=1;
    ((uint8_t *)ctl)[0xb6]=1;
    NVNshaderData shader={U(native),(const uint8_t *)ctl};
    if (!(uint8_t)CALL(nvnProgramSetShaders,U(&program),1,U(&shader))) return 0;
    NVNtextureView view;
    CALL(nvnTextureViewSetDefaults,U(&view));
    CALL(nvnTextureViewSetFormat,U(&view),NVN_FORMAT_RGBA8);
    CALL(nvnTexturePoolRegisterTexture,U(&texture_a),ti,U(&srgb_texture),U(&view));
    CALL(nvnCommandBufferAddControlMemory,U(&command),U(command_control),CONTROL_BYTES);
    CALL(nvnCommandBufferBeginRecording,U(&command));
    CALL(nvnCommandBufferSetTexturePool,U(&command),U(&texture_a));
    CALL(nvnCommandBufferBindProgram,U(&command),U(&program),NVN_SHADER_STAGE_COMPUTE_BIT);
    CALL(nvnCommandBufferBindImage,U(&command),NVN_SHADER_STAGE_COMPUTE,0,ti);
    CALL(nvnCommandBufferDispatchCompute,U(&command),1,1,1);
    uint64_t commands=CALL(nvnCommandBufferEndRecording,U(&command));
    const GfxBackend *backend=&gfx_vulkan_backend;
    uint64_t fence=backend->submit(&commands,1,rt_ticks());
    if (!backend->fence_wait(fence,UINT64_C(10000000000))) return 0;
    backend->cpu_synced(fence);
    NVNcopyRegion region={0,0,0,2,1,1};
    uint8_t pixels[8]={0};
    // Read the Vulkan image explicitly: a CPU-cached pool's ReadTexels path
    // intentionally reads its guest backing until it becomes GPU-owned.
    if (!vk_texture_read_image((const tex_t *)&srgb_texture,NULL,&region,pixels,8,8)) return 0;
    const uint8_t expected[8]={64,128,191,255,0,255,0,255};
    checks++;
    if (memcmp(pixels,expected,8)) {
        printf("probe-vkpool: FAIL sRGB storage view: %u %u %u %u; untouched pixel %u %u %u %u\n",
            pixels[0],pixels[1],pixels[2],pixels[3],pixels[4],pixels[5],pixels[6],pixels[7]);
        failures++;
    } else printf("probe-vkpool: UNORM storage view of sRGB image: exact GPU bytes and untouched texel passed\n");
    (void)memory;
    return 1;
}

// Copy pixel zero to pixel one through actual SULD/SUST. Re-registering one
// handle with UINT, SINT and FLOAT views must refresh the translator answers.
static int run_surface_atomic(void *command_control,int ti) {
    uint32_t native[][4]={
        {0x00007802,3,0xf00,0}, {0x00047802,0,0xf00,0}, {0x00057802,0,0xf00,0},
        {0x0400759f,0x60000400,0x0010e000,0}, // SURED.D.2D.ADD U32 [R4,R5],R0
        {0x0000794d,0,0x03800000,0}
    };
    uint32_t ctl[0xd8/4]={0};
    ctl[0]=0x98761234; ctl[1]=0xc9; ctl[0x30/4]=sizeof ctl; ctl[0x38/4]=sizeof native;
    ctl[0x58/4]=ctl[0x5c/4]=ctl[0x60/4]=1; ((uint8_t *)ctl)[0xb6]=1;
    for(unsigned phase=0;phase<2;phase++) {
    native[0][1]=phase?0x80000001:3;
    native[3][2]=0x0010e000|(phase?6u<<23:0);
    NVNshaderData shader={U(native),(const uint8_t *)ctl};
    if(!(uint8_t)CALL(nvnProgramSetShaders,U(&program),1,U(&shader)))return 0;
    const uint32_t initial[2]={phase?0x12:0xfffffffe,0xabcdef12};
    NVNcopyRegion region={0,0,0,2,1,1};
    CALL(nvnTextureWriteTexels,U(&typed_texture),0,U(&region),U(initial));
    NVNtextureView view;
    CALL(nvnTextureViewSetDefaults,U(&view)); CALL(nvnTextureViewSetFormat,U(&view),NVN_FORMAT_R32UI);
    CALL(nvnTexturePoolRegisterTexture,U(&texture_a),ti,U(&typed_texture),U(&view));
    CALL(nvnCommandBufferAddControlMemory,U(&command),U(command_control),CONTROL_BYTES);
    CALL(nvnCommandBufferBeginRecording,U(&command));
    CALL(nvnCommandBufferSetTexturePool,U(&command),U(&texture_a));
    CALL(nvnCommandBufferBindProgram,U(&command),U(&program),NVN_SHADER_STAGE_COMPUTE_BIT);
    CALL(nvnCommandBufferBindImage,U(&command),NVN_SHADER_STAGE_COMPUTE,0,ti);
    // Multiple workgroups contend for the same texel. Ordinary loads/stores cannot implement this sum.
    CALL(nvnCommandBufferDispatchCompute,U(&command),64,1,1);
    uint64_t commands=CALL(nvnCommandBufferEndRecording,U(&command));
    const GfxBackend *backend=&gfx_vulkan_backend;
    uint64_t fence=backend->submit(&commands,1,rt_ticks());
    if(!backend->fence_wait(fence,UINT64_C(10000000000)))return 0;
    backend->cpu_synced(fence);
    uint32_t pixels[2]={0};
    if(!vk_texture_read_image((const tex_t *)&typed_texture,NULL,&region,(uint8_t *)pixels,8,8))return 0;
    checks++;
    uint32_t expected=phase?0x80000013:190;
    if(pixels[0]!=expected || pixels[1]!=initial[1]) {
        printf("probe-vkpool: FAIL surface atomic %s: %08x %08x expected %08x abcdef12\n",phase?"OR":"ADD",pixels[0],pixels[1],expected);
        failures++;
    } else printf("probe-vkpool: surface atomic %s: 64 workgroups and untouched texel passed\n",phase?"OR":"ADD");
    }
    return 1;
}

static int run_typed_images(void *command_control,int ti) {
    static const uint32_t native[][4]={
        {0x00007802,0,0xf00,0}, {0x00017802,0,0xf00,0},
        {0x00047b97,0x60000400,0x001e0300,0}, // SULD.P.RG [R0,R1] -> R4,R5
        {0x00007802,1,0xf00,0},
        {0x00007b9b,0x60000404,0x00100f00,0}, // SUST.P [R0,R1] <- R4..R7
        {0x0000794d,0,0x03800000,0}
    };
    uint32_t ctl[0xd8/4]={0};
    ctl[0]=0x98761234; ctl[1]=0xc9; ctl[0x30/4]=sizeof ctl; ctl[0x38/4]=sizeof native;
    ctl[0x58/4]=ctl[0x5c/4]=ctl[0x60/4]=1; ((uint8_t *)ctl)[0xb6]=1;
    NVNshaderData shader={U(native),(const uint8_t *)ctl};
    if (!(uint8_t)CALL(nvnProgramSetShaders,U(&program),1,U(&shader))) return 0;
    const int formats[]={NVN_FORMAT_RG16UI,NVN_FORMAT_RG16I,NVN_FORMAT_RG16F,NVN_FORMAT_RG16UI};
    const uint16_t initial[4]={0x3c00,0xc000,0,0},expected[4]={0x3c00,0xc000,0x3c00,0xc000};
    NVNcopyRegion region={0,0,0,2,1,1};
    for (unsigned phase=0;phase<4;phase++) {
        CALL(nvnTextureWriteTexels,U(&typed_texture),0,U(&region),U(initial));
        NVNtextureView view;
        CALL(nvnTextureViewSetDefaults,U(&view));
        CALL(nvnTextureViewSetFormat,U(&view),formats[phase]);
        CALL(nvnTexturePoolRegisterTexture,U(&texture_a),ti,U(&typed_texture),U(&view));
        CALL(nvnCommandBufferAddControlMemory,U(&command),U(command_control),CONTROL_BYTES);
        CALL(nvnCommandBufferBeginRecording,U(&command));
        CALL(nvnCommandBufferSetTexturePool,U(&command),U(&texture_a));
        CALL(nvnCommandBufferBindProgram,U(&command),U(&program),NVN_SHADER_STAGE_COMPUTE_BIT);
        CALL(nvnCommandBufferBindImage,U(&command),NVN_SHADER_STAGE_COMPUTE,0,ti);
        CALL(nvnCommandBufferDispatchCompute,U(&command),1,1,1);
        uint64_t commands=CALL(nvnCommandBufferEndRecording,U(&command));
        const GfxBackend *backend=&gfx_vulkan_backend;
        uint64_t fence=backend->submit(&commands,1,rt_ticks());
        if (!backend->fence_wait(fence,UINT64_C(10000000000))) return 0;
        backend->cpu_synced(fence);
        uint16_t pixels[4]={0};
        if (!vk_texture_read_image((const tex_t *)&typed_texture,NULL,&region,(uint8_t *)pixels,8,8)) return 0;
        checks++;
        if (memcmp(pixels,expected,sizeof pixels)) {
            failures++;
            printf("probe-vkpool: FAIL typed image phase %u: %04x %04x %04x %04x\n",
                phase,pixels[0],pixels[1],pixels[2],pixels[3]);
        }
    }
    return 1;
}

int probe_vkpool(void) {
    const GfxBackend *backend = &gfx_vulkan_backend;
    checks = failures = 0;
    if (gfx_backend() != backend || !cfg_bool("TOTK_FIX_C0")) {
        printf("probe-vkpool: requires TOTK_GPU=vulkan and TOTK_FIX_C0=1\n");
        return 1;
    }
    uint64_t heap = 0;
    uint8_t *memory = NULL;
    void *command_control = NULL;
    int device_live = 0, pool_live = 0, program_live = 0, command_live = 0;
    unsigned textures_live = 0, samplers_live = 0, descriptor_pools_live = 0;
    uint64_t shader_failures = gfx_shader_failures();
    REQUIRE(!mem_set_heap_size(16ull << 20, &heap) && heap, "SetHeapSize");
    memory = (uint8_t *)(uintptr_t)heap;
    command_control = mem_kernel_alloc(CONTROL_BYTES, 16);
    REQUIRE(command_control, "owned command control allocation");
    CALL(nvnDeviceBuilderSetDefaults, U(&device_builder));
    REQUIRE((uint8_t)CALL(nvnDeviceInitialize, U(&device), U(&device_builder)), "DeviceInitialize");
    device_live = 1;
    CALL(nvnMemoryPoolBuilderSetDefaults, U(&memory_builder));
    CALL(nvnMemoryPoolBuilderSetDevice, U(&memory_builder), U(&device));
    CALL(nvnMemoryPoolBuilderSetStorage, U(&memory_builder), U(memory), POOL_BYTES);
    CALL(nvnMemoryPoolBuilderSetFlags, U(&memory_builder),
        NVN_MEMORY_POOL_FLAGS_CPU_CACHED | NVN_MEMORY_POOL_FLAGS_GPU_CACHED);
    REQUIRE((uint8_t)CALL(nvnMemoryPoolInitialize, U(&memory_pool), U(&memory_builder)), "MemoryPoolInitialize");
    pool_live = 1;
    static const uint8_t red[8] = {255, 0, 0, 255, 255, 0, 0, 255};
    static const uint8_t green[8] = {0, 255, 0, 255, 0, 255, 0, 255};
    static const uint8_t pattern[8] = {255, 0, 0, 255, 0, 255, 0, 255};
    REQUIRE(make_texture(&red_texture, 0x10000, red), "red texture"); textures_live = 1;
    REQUIRE(make_texture(&green_texture, 0x20000, green), "green texture"); textures_live = 2;
    REQUIRE(make_texture(&pattern_texture, 0x30000, pattern), "pattern texture"); textures_live = 3;
    REQUIRE(make_sampler(&repeat_sampler, NVN_WRAP_MODE_REPEAT), "repeat sampler"); samplers_live = 1;
    REQUIRE(make_sampler(&clamp_sampler, NVN_WRAP_MODE_CLAMP_TO_EDGE), "clamp sampler"); samplers_live = 2;
    int texture_reserved = 0, sampler_reserved = 0;
    CALL(nvnDeviceGetInteger, U(&device), NVN_DEVICE_INFO_RESERVED_TEXTURE_DESCRIPTORS, U(&texture_reserved));
    CALL(nvnDeviceGetInteger, U(&device), NVN_DEVICE_INFO_RESERVED_SAMPLER_DESCRIPTORS, U(&sampler_reserved));
    REQUIRE(texture_reserved >= 0 && texture_reserved < 2044 && sampler_reserved >= 0 && sampler_reserved < 2044,
        "bounded reserved descriptor counts");
    int ti = texture_reserved + 1, si = sampler_reserved + 1;
    REQUIRE((uint8_t)CALL(nvnTexturePoolInitialize, U(&texture_a), U(&memory_pool), TABLE_A, ti + 2), "TexturePool A");
    descriptor_pools_live = 1;
    REQUIRE((uint8_t)CALL(nvnTexturePoolInitialize, U(&texture_b), U(&memory_pool), TABLE_B, ti + 2), "TexturePool B");
    descriptor_pools_live = 2;
    REQUIRE((uint8_t)CALL(nvnSamplerPoolInitialize, U(&sampler_repeat), U(&memory_pool), TABLE_REPEAT, si + 2), "SamplerPool repeat");
    descriptor_pools_live = 3;
    REQUIRE((uint8_t)CALL(nvnSamplerPoolInitialize, U(&sampler_clamp), U(&memory_pool), TABLE_CLAMP, si + 2), "SamplerPool clamp");
    descriptor_pools_live = 4;
    CALL(nvnTexturePoolRegisterTexture, U(&texture_a), ti, U(&red_texture), 0);
    CALL(nvnSamplerPoolRegisterSampler, U(&sampler_repeat), si, U(&repeat_sampler));
    uint64_t handle = CALL(nvnDeviceGetTextureHandle, U(&device), ti, si);
    REQUIRE(handle == (uint64_t)ti + ((uint64_t)si << 20), "unchanged combined handle");
    uint32_t length = sizeof pool_probe_code, stage = NVN_SHADER_STAGE_COMPUTE, one = 1;
    memcpy(control + 0x700, &length, 4); memcpy(control + 0x704, &length, 4);
    memcpy(control + 0x714, &stage, 4);
    for (unsigned k = 0; k < 3; k++) memcpy(control + 0x748 + 4 * k, &one, 4);
    memcpy(control + 0x860, "DKC1", 4);
    control[0x866] = 1; control[0x867] = 1;   // storage buffers, texture handles; roots/shared remain zero
    REQUIRE((uint8_t)CALL(nvnProgramInitialize, U(&program), U(&device)), "ProgramInitialize"); program_live = 1;
    NVNshaderData shader = {U(pool_probe_code), control};
    REQUIRE((uint8_t)CALL(nvnProgramSetShaders, U(&program), 1, U(&shader)), "original ProgramSetShaders");
    REQUIRE((uint8_t)CALL(nvnCommandBufferInitialize, U(&command), U(&device)), "CommandBufferInitialize"); command_live = 1;
    CALL(nvnCommandBufferAddCommandMemory, U(&command), U(&memory_pool), COMMAND_OFF, 0x10000);
    size_t stride = vk_ctx()->props.limits.minStorageBufferOffsetAlignment;
    if (stride < 256) stride = 256;
    REQUIRE(!(stride & (stride - 1)) && stride <= OUTPUT_BYTES / 8, "bounded aligned output stride");
    static const uint32_t trip[3][4] = {{0x3f800000, 0, 0, 0x3f800000}, {0, 0x3f800000, 0, 0x3f800000},
                                       {0x3f800000, 0, 0, 0x3f800000}};
    const NVNtexturePool *tp[3] = {&texture_a, &texture_b, &texture_a};
    const NVNsamplerPool *sp[3] = {&sampler_repeat, &sampler_repeat, &sampler_repeat};
    REQUIRE(run_case("one-table red control", memory, command_control, handle, tp, sp, trip, 1, stride), "control completed");
    // No registration occurs between A -> B -> A. The handle and program stay unchanged.
    CALL(nvnTexturePoolRegisterTexture, U(&texture_b), ti, U(&green_texture), 0);
    REQUIRE(run_case("texture A/B/A", memory, command_control, handle, tp, sp, trip, 3, stride), "texture case completed");
    CALL(nvnTexturePoolRegisterTexture, U(&texture_a), ti, U(&pattern_texture), 0);
    CALL(nvnSamplerPoolRegisterSampler, U(&sampler_clamp), si, U(&clamp_sampler));
    tp[1] = &texture_a; sp[1] = &sampler_clamp;
    REQUIRE(run_case("sampler repeat/clamp/repeat", memory, command_control, handle, tp, sp, trip, 3, stride), "sampler case completed");
    REQUIRE(run_native_textures(memory,command_control,handle,stride),"native bindless texture cases completed");
    REQUIRE(run_postprocess_fetches(memory,command_control,handle,stride),"postprocess fetch modes completed");
    REQUIRE(run_native_wide(memory,command_control,handle,stride),"native wide immediate products completed");
    REQUIRE(make_texture(&srgb_texture, 0xb0000, pattern), "sRGB texture"); textures_live = 4;
    REQUIRE(run_srgb_store(memory, command_control, ti), "sRGB storage view case completed");
    REQUIRE(make_texture(&typed_texture,0xc0000,pattern),"typed image"); textures_live=5;
    REQUIRE(run_sampled_component_types(memory,command_control,handle,stride,ti),"sampled component types follow bound views");
    REQUIRE(run_typed_images(command_control,ti),"typed image load/store and view changes completed");
    REQUIRE(run_surface_atomic(command_control,ti),"surface atomic accumulation completed");
    REQUIRE(make_array_texture(),"array texture"); textures_live=6;
    CALL(nvnTexturePoolRegisterTexture,U(&texture_a),ti,U(&array_texture),0);
    REQUIRE(run_array_gather(memory,command_control,handle,stride),"array gather layer and texel ordering");
    REQUIRE(run_descriptor_format_alias(memory,command_control,handle,stride,ti),"descriptor format survives backing replacement");
    CALL(nvnTextureBuilderSetDefaults,U(&texture_builder));
    CALL(nvnTextureBuilderSetDevice,U(&texture_builder),U(&device));
    CALL(nvnTextureBuilderSetTarget,U(&texture_builder),NVN_TEXTURE_TARGET_2D);
    CALL(nvnTextureBuilderSetSize2D,U(&texture_builder),2,1);
    CALL(nvnTextureBuilderSetLevels,U(&texture_builder),1);
    CALL(nvnTextureBuilderSetFormat,U(&texture_builder),NVN_FORMAT_DEPTH32F);
    CALL(nvnTextureBuilderSetStorage,U(&texture_builder),U(&memory_pool),0xe0000);
    REQUIRE((uint8_t)CALL(nvnTextureInitialize,U(&unused_depth_texture),U(&texture_builder)),"unused depth image"); textures_live=7;
    CALL(nvnTexturePoolRegisterTexture,U(&texture_a),ti+1,U(&unused_depth_texture),0);
    unused_image_handle=ti+1;
    REQUIRE(run_native_wide(memory,command_control,handle,stride),"unused unsupported image does not abort an unrelated shader");
    unused_image_handle=0;
    REQUIRE(gfx_shader_failures() == shader_failures, "no shader translation failures");
    REQUIRE(run_warp_reductions(memory,command_control),"native warp reductions completed");
    REQUIRE(run_uniform_reductions(memory,command_control),"native uniform atomics completed");
    REQUIRE(run_feedback_views(),"feedback attachment views preserve pixels");
    REQUIRE(gfx_shader_failures() == shader_failures,"no warp translation failures");
done:
    if (pool_live) backend->finish();
    if (command_live) {
        if (command_control) CALL(nvnCommandBufferAddControlMemory, U(&command), U(command_control), CONTROL_BYTES);
        CALL(nvnCommandBufferFinalize, U(&command));
    }
    if (program_live) CALL(nvnProgramFinalize, U(&program));
    if (descriptor_pools_live >= 4) CALL(nvnSamplerPoolFinalize, U(&sampler_clamp));
    if (descriptor_pools_live >= 3) CALL(nvnSamplerPoolFinalize, U(&sampler_repeat));
    if (descriptor_pools_live >= 2) CALL(nvnTexturePoolFinalize, U(&texture_b));
    if (descriptor_pools_live >= 1) CALL(nvnTexturePoolFinalize, U(&texture_a));
    if (samplers_live >= 2) CALL(nvnSamplerFinalize, U(&clamp_sampler));
    if (samplers_live >= 1) CALL(nvnSamplerFinalize, U(&repeat_sampler));
    if (textures_live >= 7) CALL(nvnTextureFinalize, U(&unused_depth_texture));
    if (textures_live >= 6) CALL(nvnTextureFinalize, U(&array_texture));
    if (textures_live >= 5) CALL(nvnTextureFinalize, U(&typed_texture));
    if (textures_live >= 4) CALL(nvnTextureFinalize, U(&srgb_texture));
    if (textures_live >= 3) CALL(nvnTextureFinalize, U(&pattern_texture));
    if (textures_live >= 2) CALL(nvnTextureFinalize, U(&green_texture));
    if (textures_live >= 1) CALL(nvnTextureFinalize, U(&red_texture));
    if (pool_live) CALL(nvnMemoryPoolFinalize, U(&memory_pool));
    if (device_live) CALL(nvnDeviceFinalize, U(&device));
    vk_pipeline_shutdown();
    vk_exec_draw_shutdown();
    vk_exec_xfer_shutdown();
    vk_backend_shutdown();
    long errors = vk_validation_errors_total();
    printf("probe-vkpool: %s (%u checks, %u failures, %ld validation errors)\n",
        failures || errors ? "FAILED" : "passed", checks, failures, errors);
    printf("probe-vkpool: compute resources and typed storage views; graphics bind-skip is not covered\n");
    return failures || errors;
}
