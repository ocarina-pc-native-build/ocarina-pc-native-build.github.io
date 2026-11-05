# New-game integration investigation — 2026-11-05

## Current checkpoint: visible 3D cutscene, gameplay not verified

The regular New Game path now displays game-rendered scenery and the Deku Tree's
German dialogue. The scene is overexposed and incomplete. This is an in-engine
cutscene, not controllable gameplay. Video, menu, 3D rendering and successful
player control remain separate milestones.

The later work below supersedes the initial 1,195-failure checkpoint retained
in the historical notes. All game inputs, generated code, binaries, shader dumps,
render targets and test profiles remain private outside the repository.

### Proven black-scene causes

At frame 12000 before the final compute fixes, the actual 1280x720 scene target
already contained the Deku Tree. Native compute shader `fd029a317a9a4b94`
(program 109, dispatch 27x30x1, caller main+251bc0) failed to lower TLD4.PTP.F16.
It should write the 1706x960 scene target later used for dialogue composition and
presentation. That target instead contained only dialogue on black. Correct
translation made the actual 3D scene visible.

The preceding packing shader `6637ac1d052d22d4` writes RGB9E5 bits through an
R32UI view over R11G11B10 backing. Sampling the backing as R11G11B10 causes neon
colors. The RGB9E5 descriptor format was lost when its texture wrapper retired.
Preserving the compatible registered view fixes this; an authored GPU fixture
returns exactly 1/.5/.25 after failing all three components before the fix.
The actual game logs format 0x40 over backing 0x3f at 0x80003c0200, 1280x720.
Base-format debug readbacks of these packed bits can contain misleading NaNs.

Native compute shader `685adb41edc19de7` (program 99, indirect, caller
main+14e3a94) also failed at an offset texel fetch, then later shift, address and
atomic instructions. It now executes. This exposed a separate numeric-type
error: the translator declared all sampled textures float, and its compute
format query mixed the separate texture/image tables' overlapping slot numbers.

### Later source changes

| Commits | Change |
|---|---|
| e017bfd | Typed storage images, capabilities, stage metadata and active failure reporting |
| a5f88ca | Preserve extended-comparison predicate accumulators |
| dcdf132 | Native bindless texture samples, both handle forms |
| da8c33b | Immediate wide multiplication and compute UMOV/header handling |
| 37d7123 | Two-dimensional array gather and layer selection |
| 04ead43 | Exact post-link SPIR-V capture and precise semaphore errors |
| b017a75 | Reject unsupported bound-image formats only when actually queried |
| 5b2834b | Spill high vertex registers separately from uniform registers and scratch |
| c641873 | Preserve full handle kinds and packed constant-buffer slots |
| 3e951af | Log blocked compute dispatches and their resource contracts |
| fb8d698 | Offset texel fetch, packed-half per-texel gather and extended uniform shifts |
| 2d8b7fa | Retain aliased texture formats; clamped shifts and LEA.HI negative operands |
| 2d97f48 | Restrict inherited color-view compatibility; real contended surface ADD/OR atomics |
| c06dd80 | Match sampled component types to actual views and separate compute resource tables |

The first surface-reduction encoding was not recognized by this Ryujinx
frontend and generated no atomic operation. The GPU test caught unchanged
results. The corrected encoding produces real image atomics and passes
64-workgroup contended ADD/OR checks. No empty or dummy shader is accepted as
a correction.

Translator source/patch identity re-keys shader caches. Sampled component type
participates in the existing packed answer codec. Old caches are preserved.
Direct-pool metadata preservation does **not** implement Direct-pool replay.

### Comparable 12100-frame validation runs

| Run | Shader messages | Native distinct/repeated | Emitted Vulkan errors | Actual image |
|---|---:|---:|---|---|
| spill-render-validation | 311 | 308 / 0 | 10 x 06479 | Dialogue on black; internal scene target has 3D |
| postprocess-game-validation | 289 | 286 / 0 | 10 x 06479 | Neon-colored 3D |
| descriptor-format-game-validation | 288 | 286 / 0 | 10 x 06479; 2 x 01761; 2 x 12397 | Overexposed 3D, neon removed |
| surface-format-game-validation | 287 | 285 / 0 | 10 x 06479; 10 x 07753 | Overexposed 3D |
| sampled-game-validation | 287 | 285 / 0 | 10 x 06479 | Overexposed 3D; typed-sampler error removed |

Each process exited 0; the runner correctly records checkpoint-with-errors.
Validation caps duplicate messages at 10 per ID; these are emitted counts,
not every invalid use. The initially overbroad inherited-format fix introduced
01761/12397 for incompatible depth views; the compatibility check removes them.
The newly executed indirect dispatch then exposed 07753, float versus RG16_UINT.
Its authored regression reproduces six validation messages before c06dd80 and
zero after, including uint/sint/float/uint view changes and exact GPU values.

Full private safe-diagnostics.json files group first failures by processing
step, reason, opcode and stage with all hashes, active hashes and full examples.
At surface-format-game-validation, 285 native failures are unique; two additional
translator errors report Storage candidates exceed the descriptor resource
limit. 33 failed native shaders are actually selected on that path. Counts from
this New Game path are not interchangeable with the original 600-frame or
3000-frame menu path.

### Latest authored checks

- 15 default runtime checks and 17 project Python tests pass.
- CPU instruction regression suite: 16,161,412 checks, zero failures.
- Sampled/storage/atomic/alias GPU probe: 245 checks, zero Vulkan errors.
- Its 66 SPIR-V modules pass spirv-val --target-env vulkan1.3.
- 1,206 cached game modules pass the same validator at the 12100-frame checkpoint.
- After the longer run, 1,750 collected game-cache modules pass it.
- After the final Options regression, all 1,765 collected game-cache modules pass it.
- Translator compute-table probe: 13 checks.
- Descriptor pool cache seam: 60 checks at each of O0 and O2.
- Geometry pipeline seam: 6,289 checks, CPU spies only.
- Translator patch preparation: six tests, including both float modes.

These are distinct test scopes. Passing authored fixtures does not establish
complete game shader semantics or full rendering.

The final validation checkpoint uses source c06dd80, executable SHA-256
`3b332be94b9d36aa07e4747430ef9cb86827994d74f4858ae893337fe6188710`,
translator SHA-256
`21a0d2fe1bb267602682434c69f3df7413b2f6ba8673cc652bd01e849bb36c3f`
and translator identity
`b089e95ac8ceb1092f89feee42ba4ae43404647d970f0cf65b680c85730297ca`.
It exits 0 after 361.468 seconds and 12100 guest presentation requests.
The separate presentation log confirms 12000 accepted calls at its last
600-call reporting boundary.

The actual device is AMD Radeon RX 7900 XTX (1002:744c), driver
26.10.1 LLPC / raw 0x8001a0 / 2.0.416, Vulkan API 1.4.359.
The shader target is Vulkan 1.3. Validation uses local 1.4.363.0 MSYS UCRT
layers with core validation, without synchronization or GPU-assisted validation.
Enabled features include shaderInt64, shaderFloat64, geometryShader,
timelineSemaphore, dynamicRendering, synchronization2, storageImageExtendedFormats
and storageImageReadWithoutFormat. GPU breadcrumbs use VK_AMD_buffer_marker.

The final sampled-menu-validation regression repeats 3000 frames with core
validation enabled: exit 0 in 109.094 seconds, 111 distinct native failures,
no later translator errors and zero Vulkan errors. Opening video, actual title
and main menu, opened Options, and return were visually inspected in captures.
The input script uses Plus at 900, Down at 1400, A at 1600 and B at 2000.
The last presentation boundary confirms all 3000 presentations. These results
do not imply that the longer cutscene/gameplay path is valid.

The original profile still has exactly five files, all matching its recorded
SHA-256 values. No original save or option file was changed.

### Remaining known blockers

Direct-pool resources are still unresolved: arrays are declared with length 32
while the actual texture pool contains 33068 entries and the sampler pool 4096.
Replay still uses bound slots. The diagnostic states this explicitly.
VUID-vkCmdDrawIndexed-None-06479 reports RGBA8_UNORM bound to a fragment shadow
sampler at binding 22. Correct pool indexing, sampler-only descriptors, device
limits and specialization remain required. Neither increasing every array nor
silencing the error is a correction.

The longer pre-fix deferred-format-long run reached frame 23264 then exited 70:
`rt_dispatch: no function at guest pc 0x7001661690 (main+0x1661690): not a function start (lr 0x7001661690 (main+0x1661690))`.
Inspection traces this return address to the SDK setjmp/longjmp path. Resuming
inside a function cannot be handled as an ordinary function entry. It remains
unfixed; a later run must separately establish whether it reaches this blocker.

The repeated sampled-game-long run on c06dd80 confirms the same fatal at
main+1661690 after its last logged frame 23250 (last presentation boundary
22800), exiting 70 after 467.438 seconds. Validation was **disabled** on this
longer run; its zero validation-message count is not a validity result. It
reports 288 distinct native failures and four later translator failures, total
292, with 65 active failed native shaders.

The input log confirms left-stick commands at 18000, 18500 and 20000,
right-stick at 19000, A at 19500/21000, Plus at 22000 and B at 22500. Images
at 18600/19200 remain overexposed scenery; frame 21600 shows Navi's dialogue
about the Deku Tree. No image proves a controllable character or an input-caused
world/camera response. The sequence does not prove that Plus caused the later
CPU failure. Only account/profile files exist in the test save area; regular
game saving, restart/loading, collisions, interactions and room transitions
remain unverified.

Earlier logs also contain vkWaitSemaphores result -3 (initialization failed,
not device lost), and one Windows event records a validation-layer access
violation. Those are preserved findings, not a classification of every stop.
Movement, camera response, collision, interaction, saves/reload and audible
gameplay audio are not proved by video or a cutscene. Account/options files
do not establish a gameplay save.

## Historical initial investigation

Continuation of `3555ea1` and `5971bd8`, using the existing generated game,
toolchain, RomFS, host architecture and incremental build. No generated game
code was changed. The original profile is separate from every gameplay test.
The investigation is ongoing; this document does not claim controllable gameplay.

## Reproduction

Private evidence is under the preserved workspace's `work/gameplay-20261105/`.
The helper `work/gameplay_run.py` invokes `tools/run_full_runtime.py` with the
existing `work/game/oot111/native/oot2026.exe`. Each run records the executable
SHA-256, environment and exact controller script. All profiles used for these
runs are below `work/gameplay-20261105/profiles/`.

The original profile's five files were hashed before work in
`original-profile-sha256.json`. Existing `totk.ini` sets `perf_overlay = fps`;
unlike the previous rendering checkpoint, this configuration file now exists.
The physical keyboard/controller is disabled for scripted runs with
`TOTK_INPUT=none`. Vulkan validation is enabled on the RX 7900 XTX, using the
same Vulkan 1.3 target and driver as the preceding checkpoint.

`menu-baseline` repeated title, main menu, Options and return for 3,000 guest
presentation requests: process exit 0, 203 shader lowering failures, no Vulkan
validation errors. Screenshots were reviewed. The new-game script presses Plus
at tick 900 and A at tick 1200. The longer script allows the movie to play and
adds ordinary A presses from tick 9000 onward. Later movement/camera commands
are only planned inputs until a visible scene demonstrates their effect.

## Decoder output ownership

The original New Game attempt aborted around frame 1330. The trace showed two
filled decoder outputs followed by Flush, then the movie event thread polling
a completion fence whose slot had incorrectly been changed from filled to
waiting. Flush must discard queued input while preserving output already
completed for the client until Release. This was compared with Eglantine's
`INx2VideoSession::Flush`; the implementation here is original host C.

Commit `a756ba1` retains these completed outputs and adds a codec regression.
The regression failed before the fix with
`codec probe: FAIL flush revoked a completed output fence`, then passed.
The game subsequently played the actual new-game intro through the tapestry,
sleeping Link and nightmare sequence. These are video images, not 3D gameplay.

## Fatal termination

The initial abort also hung during Windows CRT shutdown, requiring the runner's
timeout. Commit `f2ecc07` routes fatal exits through the existing platform
termination primitive and identifies SVC 0x26 as the SDK's Break. It preserves
the diagnostic, guest stack and nonzero exit code. The real Vulkan-device fatal
probe exited with code 70 in 0.438 seconds. Later game failures also exited 70
without the former termination hang.

## Asynchronous play reports

At the movie's end, around frame 10700, the game called PlayReport::Send and
failed with `FATAL: sm: service "prepo:u" is not implemented`. The existing
offline telemetry sink covered Save only. Send has a different ABI: it returns
an AsyncContext through x8. An initial uncommitted attempt treating Send like
Save failed in `AsyncContext::GetCompletionEvent`; it is not the final fix.

Commit `119a5b5` returns the SDK's completed-context representation: null
interface and success result. The SDK itself creates and signals the local
completion event, reads the result, and destroys it. No report is transmitted
or persisted. The new `--probe-prepo-async` invokes the real main-module PLT
entry and the real SDK event/result/destructor functions for 16 lifecycles,
including repeat waits and memory-boundary canaries. It passes alongside the
13 existing host probes. This regression is now part of the default runner.

## Extended integer comparisons

Loading New Game exposes 1,195 distinct first-stage lowering failures, compared
with 203 on the menu-only path. They are not repeated log lines. Commit
`ccf05aa` selectively backports ISETP.EX from the pinned Eglantine reference.
Authored tests evaluate the emitted high/low predicate sequence against signed
and unsigned 64-bit comparisons, including equal high words, low-word ordering,
sign boundaries, inverted predicates and destination aliasing. The baseline
header fails 48 fixtures; the corrected header passes 47,293 total checks.
The existing EXIT-capture suite also passes all 2,822 checks.

The runtime census remains 1,195 failures: 357 shaders pass the former comparison
failure and now stop at a later unsupported `0xf60` texture instruction. Another
91 use extended-comparison modes that remain rejected. This is progress inside
translation, not evidence that these shader programs now render correctly.
The new dedicated cache `render-captures/cache-isetp-ex` preserves earlier caches.
All 28 SPIR-V modules checked at the initial movie checkpoint passed
`spirv-val --target-env vulkan1.3`; later modules require their own validation.

## Evidence boundaries

Game instructions, decoded video, native shader dumps, translated shader binaries,
render-target captures and test saves remain private outside the repository.
Only source changes, authored tests and diagnostic summaries belong in commits.
Frame counts are guest presentation requests; visible video, GPU presentation
and controllable 3D gameplay remain separate observations.
