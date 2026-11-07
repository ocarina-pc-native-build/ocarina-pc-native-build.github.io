# Visible title and menu checkpoint — 2026-11-05

Continuation of `13c6c0e`, preserving the PACGA implementation, linked Zelda
functions, generated objects, toolchain, RomFS and existing profile. The black
screen is fixed on the exercised path: the actual game displays its opening
video, title/main menu and options screen. Scripted menu navigation opens
Options and returns to the main menu. Gameplay, saves, audible audio and a
rendered 3D game world have **not** been verified. There are still 203 rejected
shader stages; the runner correctly retains `checkpoint-with-errors`.

## Reproduction and hardware

The original `work/run_native.py run --timeout 40 --frames 600 --preemption 2
--screenshot` was repeated before fixes. It reached 600 guest present requests,
exited with process code 0 in 17.281 seconds, and produced a completely black
preview with 464 shader failures and two Vulkan validation errors. No extraction,
lifting or generated C was repeated or edited. Later builds reused 551 generated
translation units and 113 runtime objects; only changed host objects were rebuilt.

All paths below are relative to the preserved workspace
`C:/Users/Pascal/Documents/Codex/2026-11-05/du-h/`. The baseline log and metadata
are `work/logs/render-fix/baseline-600.log` and `baseline-600.json`. The subsequent
instrumented baseline, including full error messages and per-shader identities,
is `work/logs/render-fix/capture/boot-1793857537519512100.log` (EXE SHA-256
`93656d86d270a273b0c349b15d630d66373dd18ee7ce6ffc42483be55ac28101`).

Actual local device, selected by the runtime:

| Item | Observed value |
|---|---|
| GPU | AMD Radeon RX 7900 XTX, device 0, vendor `1002`, device `744c` |
| Driver | AMD proprietary driver `26.10.1 (LLPC)`, ID 1, version 2.0.416 / `0x8001a0` |
| Vulkan | Requested target 1.3; physical device supports 1.4.359 |
| Validation | `VK_LAYER_KHRONOS_validation` enabled; warnings/errors and full message IDs captured |
| Subgroups | Native 64, size control 32–64, required stages `0xf0`; translator VS/FS/CS/GS 64/32/32/64 |
| Features | shaderInt64, shaderFloat64, geometryShader, timelineSemaphore, dynamicRendering, synchronization2 supported and enabled |
| Descriptor limits | Storage buffer offset alignment 4; uniform alignment 16; maxPushDescriptors 32 |
| Host-import ceilings | maxBufferSize and maxMemoryAllocationSize both 2,147,483,648 bytes |

The queried feature chain is passed to `vkCreateDevice`; diagnostic lines now
record the actual enabled values before releasing that chain. No GPU-assisted
validation or additional synchronization-validation setting was enabled. Ordinary
validation being clean is not proof of every synchronization or shader semantic.

Configuration stayed docked, with the same local game version 1.1.1, modules,
RomFS and profile, no `totk.ini`, `TOTK_GPU=vulkan`, and
`TOTK_ASYNC_PREEMPT=2`. The runtime logs its own resolution and selected GPU.
Validation uses `TOTK_VK_VALIDATION=1`, `VK_LAYER_PATH=work/validation/ucrt64/bin`
and that directory on PATH. Diagnostic captures additionally used `TOTK_DUMP=550`,
`TOTK_DUMP_UBO=1`, `DKB_SHADER_DUMP` and, where needed, `TOTK_TRACE=gfx,perf`.
The menu input test alone enables `TOTK_INPUT_SCRIPT` and `TOTK_SHOTS`.

## What each counter proves

`g.frames` advances in the guest `QueuePresentTexture` path. It counts guest
presentation requests, not game updates, GPU completion or visible content.
The checkpoint now drains replay/GPU work. A separate counter increments only
after `vkQueuePresentKHR` returns success or suboptimal; the 600-request run
records 600 accepted presentations, and the menu run 3,000.

| Step | Evidence |
|---|---|
| Game code executes | Loaded/relocated modules, `nnMain`, guest SVC/host-call activity, game-created menus |
| Commands recorded | NVN command recording and frame-550 dispatch/draw capture |
| Commands submitted/executed | GPU timeline fences, timestamp results, readback of intermediate compute outputs |
| Image presented | Successful `vkQueuePresentKHR` counter; actual game window observed locally |
| Visible game content | Reviewed video, title and options captures; scripted selection changes |

The automated JSON's `rendering_verified=false` remains conservative: it does
not inspect image semantics. Human/visual evidence is recorded separately, outside the repository. Nonblack pixels alone, a counter,
or the synthetic regression's pixels are never treated as a Zelda boot.

## Two buffer errors

The complete baseline messages were:

```text
[host] vk validation error [VUID-VkBufferCreateInfo-size-06409, -332260500]: vkCreateBuffer(): pCreateInfo->size (2550136832) is larger than the maximum allowed buffer size VkPhysicalDeviceMaintenance4Properties.maxBufferSize (2147483648).
The Vulkan spec states: size must be less than or equal to VkPhysicalDeviceMaintenance4Properties::maxBufferSize (https://docs.vulkan.org/spec/latest/chapters/resources.html#VUID-VkBufferCreateInfo-size-06409)
[host] vk validation error [UNASSIGNED-vkAllocateMemory-maxMemoryAllocationSize, -1649273453]: vkAllocateMemory(): pAllocateInfo->allocationSize (2550136832) is larger than maxMemoryAllocationSize (2147483648). While this might work locally on your machine, there are many external factors each platform has that is used to determine this limit. You should receive VK_ERROR_OUT_OF_DEVICE_MEMORY from this call, but even if you do not, it is highly advised from all hardware vendors to not ignore this limit.
```

Both came from the CPU_CACHED|GPU_CACHED guest pool at `0x1bf470000`, length
`0x98000000`, flags `0x24`, imported as one oversized buffer/allocation. They
occurred during resource creation, before any descriptor access; validation did
not supply object entries for these creation failures. The callback now preserves
object information when available. These were size-limit failures, not evidence
of a use-after-free, bad usage flag or out-of-bounds descriptor in this run.

`vk_memory.c` now represents such a pool as an address range and imports bounded,
aligned views on demand. Each requested buffer access fits wholly in one view,
including an access crossing an earlier view's boundary. Views alias the original
host allocation; no oversized shadow/mirror or unrelated larger buffer is made.
The parent owns the views through its last GPU fence. Existing buffer usages,
host-coherent memory type selection, binding at offset zero, memory requirement
checks and fence retirement remain in force. Descriptor selection resolves the
complete requested length, rather than truncating it at a previous view's edge.
Virtual pools still report only their contiguous mapped span. A single requested
access that cannot fit the actual device limit fails explicitly.

Regression coverage lowers the import ceiling to 64 KiB **only inside the probe**
and checks overlapping views of a 256 KiB pool, complete crossing ranges, actual
GPU writes visible through another view and host memory, retirement and address
reuse. Pure range tests cover real >2 GiB arithmetic, invalid alignment, overflows
and rejected lengths. Both validation messages disappear after this fix. The
buffer-only run still remained black, separating this correction from the visual
root cause.

## Shader failure census and fixes

The instrumented baseline captured 2,837 native stages. All 464 failure messages
refer to **464 distinct shader hashes, zero repeated failure messages**. Every
first failure occurs in Ampere-to-Maxwell instruction lowering, before SPIR-V
generation, SPIR-V validation or Vulkan pipeline creation. No downstream failures
were reported for the exercised render path. This is not a claim that every
successfully lowered stage was subsequently compiled or used.

| First failure class | Before | After | Affected baseline stages | Representative hash |
|---|---:|---:|---|---|
| Texture dimension query | 255 | 0 | 250 fragment, 5 vertex | `d142fb7f23fcac9f` |
| Unsupported native opcode | 79 | 79 | 62 compute, 1 vertex, 16 fragment | `ec6e8682fb5fdeae` |
| Stage buffer read mode | 56 | 56 | 44 vertex, 12 tessellation evaluation | `60dbd7f60c759472` |
| Texture gather mode | 41 | 41 | 22 compute, 19 fragment | `a584b3ac9aafc26c` |
| Byte-to-float conversion mode | 26 | 0 | 20 fragment, 6 vertex | `4b740172b74fbc0e` |
| Lowering scratch-register conflict | 6 | 6 | 6 vertex | `ba7a591244e5ed3b` |
| Texel fetch mode / descriptor binding | 1 | 1 | 1 compute | `685adb41edc19de7` |
| Funnel shift immediate mode (newly exposed) | 0 | 20 | 20 fragment after I2F correction | `4b740172b74fbc0e` |
| **Total** | **464** | **203** | **261 fewer rejected stages** | |

Native SPH stage labels in these messages are 0=compute, 1=vertex,
3=tessellation evaluation, 5=fragment. Complete representative messages:

```text
[host] nvn2: shader d142fb7f23fcac9f stage 5 Ampere lowering failed at +0xb0: native texture dimension query mode
[host] nvn2: shader ec6e8682fb5fdeae stage 0 Ampere lowering failed at +0x100: unsupported native opcode
[host] nvn2: shader 60dbd7f60c759472 stage 1 Ampere lowering failed at +0x10: native stage buffer read mode
[host] nvn2: shader a584b3ac9aafc26c stage 0 Ampere lowering failed at +0x3f0: native texture gather mode
[host] nvn2: shader 4b740172b74fbc0e stage 5 Ampere lowering failed at +0x950: native byte-to-float conversion mode
[host] nvn2: shader ba7a591244e5ed3b stage 1 Ampere lowering failed at +0x320: native program uses lowering scratch registers
[host] nvn2: shader 685adb41edc19de7 stage 0 Ampere lowering failed at +0xad0: native texel fetch mode or descriptor binding
[host] nvn2: shader 4b740172b74fbc0e stage 5 Ampere lowering failed at +0xc20: native funnel shift immediate mode
```

The unsupported-opcode group is `0x8a5` (8), `0xc11` (7), `0x825` (48),
`0x361` (13), `0xc0b` (3). Mode groups are `0x923` (stage read), `0xb63`
(gather), `0x419` (shift) and `0xb66` (fetch). Scratch conflicts remain explicit;
their guards were not disabled.

Targeted Eglantine backports accept TXQ component masks by component count,
including Z-only output and split destinations, and implement signed byte and
halfword I2F selection. A separate TEX FP16 result-packing correction places the
first component in the low halfword and the second in the high halfword. Authored
fixtures check masks/destinations, signed values/selectors and unequal known half
values; they contain no game shader. The 20 shift failures become visible only
after the earlier I2F failure is fixed. No dummy shader or skipped instruction
is introduced as a solution.

Private native inputs/control blocks are preserved in
`work/game/oot111/render-captures/native/`; representative lowered outputs,
SPIR-V, pass images and descriptor/UBO traces stay under `render-captures/`.
The full private census includes instruction words; committed reports contain
only counts, hashes, stage labels and diagnostic text. None of these extracted
shader binaries or images are committed or published.

## Proven cause of the black image

Frame 550 follows the real movie/composite path:

1. AV1 decoder supplies NV12 luma/chroma; compute shader `54b0fc2b1c8fbfc7`
   produces a nonblack 1920x1080 RGBA image.
2. `753f8ab880fe7923` handles intermediate buffers; `13cab66ee383c4f4`
   produces a nonblack RGB10A2 image.
3. `3f6f2b1d671badcd` writes the output through an **RGBA8 UNORM storage view**
   (NVN `0x25`) of an **RGBA8 sRGB image** (NVN `0x38`, Vulkan format 43).
4. Two graphics passes composite the intermediate image into the presented target.

Previously, image creation checked storage support only on the sRGB base format
and omitted STORAGE usage. `get_view` rejected that image and the existing
fallback bound a stand-in. It also ignored the requested NVN view format. The
real destination stayed all zero while earlier compute outputs contained video.

Image creation now queries the compatible UNORM format, adds STORAGE with
MUTABLE_FORMAT/EXTENDED_USAGE when supported, and resource views honor the requested
format. Storage, sampled and attachment views have explicit, appropriate usage;
storage/sampled variants have separate cache keys. This follows the Vulkan
[mutable/extended image usage rules](https://docs.vulkan.org/spec/latest/chapters/resources.html)
and [image-view usage contract](https://docs.vulkan.org/refpages/latest/refpages/source/VkImageViewUsageCreateInfo.html).
The authored NVN2 surface-store GPU regression checks exact `.25,.5,.75,1`
output bytes through a UNORM view of sRGB storage and an untouched neighboring
texel. It reads the actual Vulkan image, not the CPU-cached guest backing.

The corrected frame capture shows nonblack data through pass 3 and both final
draws, followed by real presentation. The active shaders translated successfully
even before the bulk shader corrections, so the shader count alone did not explain
the black screen. The FP16 correction by itself also did not restore the image.
No AV1 change was necessary in this continuation: its output was already valid.

The game presents crop `0,0,1706,960` from a 2560x1440 backing texture. Early
screenshots included the unused remainder and appeared bordered; the actual
window was correctly filled. Captures now honor the same crop as presentation.

## Cache, SPIR-V and verified outcome

The process-local lowering cache is recreated on each run. Persistent shader
keys hash lowered code, control data, translator identity and host answers;
changed lowering therefore changes the key. Tests additionally used the new
`render-captures/cache-pack-fix/` directory, preserving the original cache.
Pipeline keys include shader identities. No old result was renamed as a fix.
All **46** SPIR-V modules accumulated in that dedicated runtime cache through the
title/options path passed `spirv-val --target-env vulkan1.3`. This validation is
supplemented by GPU regression readback and actual game images; it does not prove
general shader semantic correctness, including unexercised instruction modes.

| Run | Shader failures | Vulkan errors | Visible result | Process |
|---|---:|---:|---|---|
| Baseline 600 | 464 | 2 | Black | Exit 0 |
| Bounded buffer imports, 600 | 464 | 0 | Black | Exit 0 |
| TXQ/I2F corrections, 600 | 203 | 0 | Black | Exit 0 |
| TEX halfword packing, 600 | 203 | 0 | Black | Exit 0 |
| Correct image/view usage, 600 | 203 | 0 | Opening video | Exit 0 |
| Longer 3,600 / 7,200 requests | 203 | 0 | Title / main menu | Exit 0 |
| Scripted 3,000 requests | 203 | 0 | Main menu → Options → main menu | Exit 0 |

The script uses the existing merged-input test path, holding each input for eight
ticks: `900 PLUS 8`, `1400 DOWN 8`, `1600 A 8`, `2000 B 8`.
Series captures at requests 1,000, 1,800 and 2,200 show main menu, options and
return with Options selected. This verifies those game menu actions; no connected
controller, arbitrary keyboard mapping or gameplay input claim is made. The
background is video and the menu is game-rendered UI, not proof of 3D gameplay.

Final regression results: 13 host/runtime probes, 17 Python unit tests, 301
shader/range checks, 2,822 existing native EXIT-capture checks; GPU memory probe
49 checks and descriptor/storage-view probe 63 checks, both zero validation
errors. Existing PACGA/lifter results were preserved, not presented as newly run.
See the machine-readable report for executable hashes, exact logs and captures.

The remaining 203 lowering failures need semantic implementations and fixtures
when their render paths are reached. CPU-cached texture readback behavior,
unexercised services/traps, broader codec formats, audio, saves and sustained
gameplay remain open. No black checkpoint is described as a successful visible
boot, and no title/menu result is described as complete playability.
