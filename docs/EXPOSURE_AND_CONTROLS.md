# Rendering follow-up after the nonlocal continuation fix

This continues `e6125e6` and CPU fix `1a006ef`. The CPU regression and two
successful fresh replays are documented in `NONLOCAL_CONTINUATIONS.md`.
All captures, extracted shaders and test profiles remain outside the repository.
The user's original profile is not an experimental save.

## Two independently reproduced graphics defects

Native compute shader `600f56f6eda37a83` was selected in the captured 3D path
but rejected at `+0x260` (`native warp sum mode`). It requires REDUX.MIN.S32.
After implementing signed/unsigned warp minimum and signed maximum, its next
failure was `+0x290` (`native global reduction mode`): signed minimum through a
uniform 64-bit address. The existing uniform-address branch accepted U32 only.
Bits 90/91 select the address representation, not the arithmetic operation.
The fix preserves the signed type in the Maxwell global reduction.

Signed warp order is mapped to unsigned order by XORing the sign bit before
comparison and after reduction. Inactive lanes contribute the correct identity.
Unsupported instruction modes still fail explicitly. Authored tests exercise
partial/holed lane masks, sign boundaries, predicates, byte offsets and RZ.
No game instruction sequence is included in a test.

The same 8,344 locally captured stages were lowered with the baseline and fixed
headers: 7,963 to 7,964 accepted, exactly the shader above newly accepted, no
new rejection. The generated module passes `spirv-val --target-env vulkan1.3`.
In real run `exposure-fixed-abc`, frame 4200, pass 134 is now an actual 1x1x1
dispatch of this shader (SPIR-V `f044fcdbb510235d`), with an RGBA16F 640x360
input and the game's bound 64-byte storage buffer. The prior capture recorded
a blocked dispatch at the corresponding position. This establishes integration;
it does not establish that the operation caused the excessive brightness.

The new 3D reload path also reports `VUID-VkRenderingAttachmentInfo-imageView-10780`.
The image already had feedback-loop and sampled usage, but
`vk_exec_target_view` replaced its inherited usage with attachment-only usage.
The fix retains sampled/feedback usage for images created with that contract,
while still excluding STORAGE from sRGB attachment views. A production-view GPU
test reproduces three errors before the fix (UNORM, sRGB and depth), then zero
after it; load/store preserves all eight bytes of each authored test image.

## Diagnostics and interpretation

`TOTK_SHOTS` and `--shot` read the game's presented texture **before** the PC
runtime colour adjustment, FSR/bilinear and overlay. They cannot measure FSR's
output. `TOTK_PRESENT_SHOTS=lo-hi:step` and `TOTK_PRESENT_SHOTS_DIR` now capture
the actual swapchain image after those stages, using the existing fenced GPU
readback. A failed fence never produces a claimed valid capture. The filename
uses the guest presentation-request counter; dropped/minimized presentation is
not silently counted as a screenshot.

`TOTK_DUMP_RAW=1`, together with the existing `TOTK_DUMP`, preserves tightly
packed readback bytes before PNG conversion. Raw files retain their format and
dimensions in the filename. Image aliases still require the actual sampled-view
interpretation; RGB9E5 bits viewed as base R11G11B10 must not be reported as
uninitialized/NaN scene data.

In the Kokiri Forest reload capture, frame 4200, the active scene is 1280x720,
followed by the game's 1706x960 upscale and a 1706x960 viewport into a
2560x1440 sRGB target. The PC window is 1920x1080. The overlay's 1600x900 figure
comes from its configured resolution table, rather than this capture's target.

HDR pass 130 has luminance median 23.96 and 97.77% of pixels with all RGB above
0.98. This is **not** the completed scene: opaque geometry in pass 132 changes
the median to 0.02179 and that fraction to 2.66%. Calling pass 130 the first
bad pass from its clipped PNG would be incorrect. Before tone mapping, pass 143
has median 0.03453 and maximum 35.608. The tone-mapped pass 160 has median
0.20973, maximum 1 and 1.96% of pixels above 0.98 in every channel. These
measured ranges do not by themselves prove physically correct lighting.

The original Deku Tree dialogue capture remains a separate camera/phase, and
is visibly washed out. Neither this HDR analysis nor the new reduction support
is a demonstrated repair of that defect. Direct-pool shadow descriptors remain
an independently observed resource problem: metadata currently declares 32
entries while the game texture pool has 33,068; replay still uses bound slots.
This produces `VUID-vkCmdDrawIndexed-None-06479` (colour views sampled as depth).
Suppressing the validation or replacing required shaders is not a solution.

## Validation so far

- 9,765 authored warp/global reduction checks: zero failures.
- Existing render regression suite: 16,161,412 checks, zero failures.
- 1,411 Vulkan pool checks, including the original 245: zero failures and zero
  core validation errors. The new atomic cases contend across four workgroups.
- All 51 shader modules generated by those GPU tests pass Vulkan 1.3 validation.
- All 15 host probes and 17 project tests pass after the graphics changes.

The hardware is AMD Radeon RX 7900 XTX, driver 26.10.1 (LLPC), API 1.4.359;
the runtime requests Vulkan 1.3. Validation uses the local 1.4.363.0 core layer,
without GPU-assisted or synchronization validation. Runtime caches use the
lowered code identity, and the integration run uses a separate `cache-redux`.

CPU-only reload B reached 5000 requests and exited 0; it logged 375 unique
native lowering failures, four translator failures, 43 active failed native
shaders, and ten logged errors for each of the two VUIDs above. The layer caps
duplicates at ten, so this is not a count of all invalid draws.
Reload C exited 70 near request 4934 with
`vkWaitSemaphores failed (VkResult -3; target 34539, last completed 34538)`.
Its diagnostic reported process commit 20,312 MB and system commit 48,499 of
49,451 MB; it is a separate resource-pressure failure, not the old return-PC
failure. The raw-capture integration run used validation off and exited 0 at
5600 requests, with 374 native plus four translator failures. Validation-off
zero counters are not evidence of a clean Vulkan game path.

The subsequent `graphics-validation` run used the same build with core validation
enabled and exited 0 at 4200 requests, with 4200 actually presented. The feedback
view VUID is absent. Ten capped messages for `VUID-vkCmdDrawIndexed-None-06479`
remain (example: set 1, binding 23, `fp_t2ds_cb0_40000000`, RGBA8_UNORM sampled
with depth comparison). There are 374 native and four translator failures,
43 of the failed native stages actually selected in this path. All 772 SPIR-V
modules in this run's shared graphics cache pass Vulkan 1.3 validation; that
does not validate descriptor selection or the resulting lighting.

## Controlled presentation comparison and inputs

Run `post-and-controls` uses one process, a cloned Kokiri Forest save, a static
camera until request 5600 and 1920x1080 actual swapchain captures. Foliage, idle
animation and time still advance. Settings change live without rewriting INI.
The overlay area is excluded from the following encoded RGB measurements:

| Request | Setting | Mean encoded luminance | Pixels with all RGB > 250/255 |
| --- | --- | --- | --- |
| 4200 | FSR, sharpness 80 | 0.44813 | 1.77146% |
| 4600 | FSR, sharpness 0 | 0.44540 | 1.79092% |
| 5000 | Bilinear, sharpness 0 | 0.44695 | 1.67310% |
| 5400 | FSR, sharpness 80 restored | 0.44661 | 1.75837% |

The excessive highlights exist before PC scaling and survive every setting.
This rules out FSR/sharpening as the sole source; encoded PNG measurements are
not HDR radiance or evidence that the game lighting itself is correct.

Left-stick inputs visibly change the character/view position; right-stick
input changes the camera, making much of the scene almost completely white.
PLUS opens the game's inventory. An A/"Open" prompt is visible, but a completed
interaction and collision response have not been established. The regular load
screen successfully loads the test autosave. At this checkpoint manual save/reload
was still pending; the later regular-save check below completes that check.
The run exits 0 at 7600 requests; actual presentation and postprocessing captures
are present. It records 374 native and five translator failures, 56 active failed
native stages, with validation disabled. This is visible 3D and responsive game
UI, not a declaration of correct rendering or full playability.

## Uniform floating predicates and ordered comparison folding

The native FSETP source form `0xc0b` was missing from the opcode switch even
though `operand()` already handles uniform registers and their modifiers.
Routing that form through the existing floating predicate lowering accepts
97 additional captured stages: on the same 8,363 inputs, 7,983 become 8,080
accepted, with no newly rejected stage. `uniform_fsetp.cpp` has 688 passing
checks including UR27/URZ, invalid registers and invalid predicate combinations;
the old lowering fails 240 support checks.

The authored GPU cases revealed a separate translator defect: constant-folded
ordered NE returned true for NaN. The existing dynamic comparison was correct.
Patch 0020 explicitly excludes NaNs from NE, preserving NEU's unordered result
and generic IR inequality semantics. The exact same GPU fixture fails four
output checks with translator `b089e95ac8ceb109`, then none with the rebuilt
translator `49346371a5435278`. It tests all 16 comparisons, abs/neg, both predicate
outputs, signed zero, infinities, NaNs and unchanged memory outside the outputs;
96 cases use immediates and 96 load their values from a storage buffer on the GPU.

The final pool suite passes 2,372 checks with zero core validation errors.
All 326 modules in its cache pass Vulkan 1.3 validation (this includes both
translators used for the controlled before/after test). The 16,161,412 existing
render checks, 15 host probes, 17 project tests and six translator-build option
tests also pass. No vendor source file was edited: patch 0020 is applied to the
build copy. The translator was rebuilt from the complete current patch set;
the game uses a separate `cache-fsetp-verified`. An earlier incomplete incremental
translator build and its contaminated diagnostic cache are retained and marked
invalid locally, excluded from these results.

Real run `fsetp-camera` uses EXE SHA256
`86d1b9492c0379f85390132e66c6a674db8a9c3a99609e9c168a3eef23fc75ec`
and translator SHA256
`8e3035cf53eb13a757fe47ffb2f7f3ab056ea25cebb6e043a171f5f539095d8c`.
The static scene remains overlit. Native failures fall from 374 to 278; none is
a repeated native error message. At the interruption, 34 failed native stages
had actually been selected. The feedback VUID remains absent, with ten capped
06479 messages. At request 4875, it exits 70:

```
FATAL: vk: vkWaitSemaphores failed (VkResult -3; target 34130, last completed 34129)
[host] fatal: memory commit: this process 20564 MB, the system 47590 of 48236 MB
```

This is a real failure under near-exhausted system commit, not a successful
6400-frame run. A separate camera capture without the validation layer is used
to investigate lighting; validation-off counters cannot establish Vulkan validity.

## Masked gradient samples and missing geometry

The frame-4200 `foliage-system` trace records 71 draws rejected before GPU
recording, all missing the fragment stage. The older `draws_skipped` summary
does not count this early return. The new opt-in dump records targets, native
shader identities and registered handles without resolving or uploading textures.
Bound handles include stale/unused entries and alone do not identify a material.

| Fragment native hash | Blocked draws | First unsupported operation |
| --- | ---: | --- |
| `859e6ad18a68f3a9` | 32 | TXD channel mask |
| `d51a0cab472e0768` | 24 | TXD channel mask; third destination R53 |
| `c0773d89e2e9b960` | 7 | TXD channel mask |
| `78e6bf688b49647c` | 5 | TXD channel mask, then SR_VARIABLE_RATE |
| `ce62c81dd5a4d9b0` | 1 | Texture gather mode |
| `abf7e88b35aa1ce4` | 1 | SR_VARIABLE_RATE |
| `c07fa58bcd4e2298` | 1 | SR_VARIABLE_RATE |

TXD now forwards every nonempty channel mask and writes only selected packed
results, including a single odd third destination and discarded high results.
The first three shaders now run: blocked draws drop from 71 to 8. Their targets
are 128x128 color/depth auxiliary images, not established foliage/shadow passes.
On an unchanged 8,375-stage census, 8,091 become 8,101 accepted with no newly
rejected stages. The fourth shader now reaches a later unsupported instruction.
This distinction prevents counting a moved first error as a fully fixed shader.

`gradient_texture.cpp` passes 1,262 checks; the old lowering fails 66 support
checks with the same fixture. The GPU probe adds 300 cases covering all masks,
2D and both array layers, distinct source channels, contiguous/split/discarded
destinations and untouched output bytes. Its first draft incorrectly supplied
the TLD4 coordinate layout to TXD; layer-1 checks exposed that fixture mistake.
TXD uses X/Y followed by its packed layer. Corrected fixtures pass 4,473 total
checks with zero core validation errors. All 476 cached probe modules pass
`spirv-val --target-env vulkan1.3`. The 16,161,412 render checks, 15 host probes
and 17 project tests pass again.

Real run `gradient-foliage`, EXE SHA256
`d95f8b76f4682cca3d8423c8314ed8ca65bc2d7339a85fc8a6f647e30522d4d4`,
exits 0 at 6,400 guest requests after 184.312 seconds. It reports 268 distinct
native failures and four downstream translation failures. Validation is off.
The unchanged test save/input sequence still produces overexposure before PC
scaling, especially after the camera turns. Restoring those 63 auxiliary draws
has not fixed the image, nor proven the suggested missing-foliage explanation.
The dump option accepts one frame: the supplied `4200,6200` was parsed as 4200;
only that frame's intermediate targets were captured, while screenshots exist
through 6400. No second raw dump is claimed.

## Regular manual save

`manual-save-confirm` uses an isolated clone of the gameplay checkpoint, opens
System / Save, explicitly moves from Cancel to Save, and confirms. Screenshot
5800 shows the game's "Gespeichert" confirmation; filesystem commits grow the
save from four to six files, adding the manual slot's caption and progress.
The process exits 0 at 6800 requests. The original profile is never selected.
`manual-reload` then starts a second clone of that saved profile. The regular
load screen at request 1400 selects the manual slot (19:10), above the older
autosave (17:30); request 4200 shows the restored 3D scene at Link's house.
It exits 0 at 4400 requests after 120.719 seconds. All five original-profile
file hashes still match the pre-test record. This establishes this manual
save/reload path, not arbitrary save compatibility or all scene transitions.

## Full-rate reads, shadow gather and capture layout

Three remaining fragment shaders read SR_VARIABLE_RATE (132). The renderer
does not enable a fragment-shading-rate extension/feature or supply a rate
state in `vk_device.c` / `vk_pipeline.c`. The lowering now reports its actual
1x1 fragments, packed as `0x00010100`; this invariant must change if coarse
shading is implemented. See the [Vulkan rasterization specification](https://docs.vulkan.org/spec/latest/chapters/primsrast.html).
The same census accepts 26 more stages, 8,127/8,375, without new rejections.
The authored register test passes 154 checks (old implementation: 30 failures).
The hardware probe checks both ordinary/uniform results and a disabled read.

`fragment-rate-scene` reaches 4400 requests, exits 0 after 243.297 seconds, and
reduces the captured blocked draws from 8 to 1. It still reports 245 distinct
native failures and four downstream failures. Its core validation reports ten
capped 06479 messages and ten `VUID-vkCmdCopyImageToBuffer-srcImageLayout-00189`
messages: capture claimed GENERAL while the image was actually in
ATTACHMENT_FEEDBACK_LOOP_OPTIMAL_EXT. Capture now temporarily transitions the
specific subresources to GENERAL and restores their prior layout after copying,
preserving executor tracking. The existing GPU feedback regression now invokes
the production capture-copy helper on UNORM, sRGB and depth images and checks
unchanged pixels plus subsequent layout use. No diagnostic is suppressed.

The last rejected fragment shader, `ce62c81dd5a4d9b0`, uses scalar 2D TLD4.DC
at +0x1650. Native X/Y and depth reference now map to Maxwell's coordinate pair
and comparison operand, with the DC flag and split four-result destinations.
CPU checks cover source/result overlap; GPU checks use real depth .25/.75,
LESS/GREATER samplers, three references and overlapping/non-overlapping layouts.
The old CPU lowering fails all 27 support checks; the corrected one passes
243 checks. Census: 8,128/8,375, one additional stage, no new rejects.

The combined pool suite passes 4,569 checks with zero core validation errors;
all 483 cache modules pass Vulkan 1.3 validation. The 16,161,412 render checks,
15 host probes and 17 project tests pass again. No translator rebuild was
needed: changed lowered code changes the cache key; translator identity remains
`49346371a5435278` from the complete patch-0020 build.

The first combined real validation run crashes near request 2798, process exit
`0xc0000005`, before producing a screenshot. Windows Application event 1000 at
2026-11-05 19:30:56 identifies `VkLayer_khronos_validation.dll`, offset
`0x8cfec2`, as the faulting module. This identifies the fault location, not
the cause or proof that all application calls were valid. The regular path
already reports the unresolved 06479 depth-comparison descriptors.

`depth-gather-no-vvl` uses the same EXE, SHA256
`50f2904947ae0653caccc36fc8d1fd98df726ce4972ebddc8cb52d7f2de9200c`,
with validation disabled. It exits 0 at 6400 requests after 174.453 seconds,
244 distinct native failures plus four downstream translation failures.
The frame-4200 dump has zero blocked draws, but 17 blocked compute dispatches
remain in this path. The new pass 116, fragment SPIR-V `5fbfa3290a581bc0`, samples
the real 1600x1600x3 and 12288x12288 D16 shadow images and writes a 1280x720
RGBA8 result. Shadows visibly return around Link's house; this is a concrete
lighting-path correction, without changing exposure or adding substitute output.
The same camera-turn sequence still yields a largely white image at 6200.
Missing foliage is not yet established as the remaining cause, and this is not
a declaration of visually correct or fully playable gameplay.

`depth-validation-monolithic` repeats the 4400-request capture with the same
EXE, core validation enabled and diagnostic `TOTK_GPL=0`. It exits 0 after
205.0 seconds, with accepted presentations through 4200. It has ten capped
06479 messages, but no 00189 capture-layout or 10780 attachment-view messages.
Using complete pipelines avoided the observed validation-layer crash in this
bounded run. This is a diagnostic comparison, not a permanent settings change
or proof of the crash's root cause. The remaining depth descriptors are invalid.

## Negative min/max immediates and spilled comparisons

IMNMX immediate form `0x817` rejected negative values, including -1, despite
Maxwell's signed 20-bit immediate encoding. The lowering now checks the actual
[-524288, 524287] range and writes the 19 payload bits plus the separate sign
bit. Signed/unsigned operation selection and min/max selection are preserved.
`constant_minmax.cpp` passes 56 checks; the same fixture against the old header
fails 12 support checks. One hundred authored GPU cases cover signed/unsigned
min/max, positive and negative boundaries, and unchanged output bytes. Three
additional captured stages lower successfully. The originally investigated
compute shader advances to a later unsupported multiply; it is not counted as
fully repaired.

At request 5200 of `minmax-camera-only`, two vertex stages still prevented draws:
`3c18ee4ecd8da239` (count 2364) and `249f15f0cc8e0976` (count 12). Their spill
plans did not recognize constant-buffer FSET (`0xa0a`) and immediate FSETP
(`0x80b`). The fix classifies only the actual GPR operands; constant offsets,
immediates and predicate outputs remain untouched. Authored tests simulate
spill/restore with all low registers live, aliased source/result registers,
disabled writes and distinct high-register values. The complete render suite
passes 16,180,780 checks; the old header fails 200 checks in the same fixture.
This is CPU spill-plan coverage; the arithmetic GPU probe does not exercise
this vertex-only spill path.

On the same 8,375 native inputs, support progresses as follows. These are native
lowering results, not counts of fully translated, validated or rendered shaders:

| Revision | Accepted | Newly accepted | Newly rejected |
| --- | ---: | ---: | ---: |
| Before masked TXD | 8091 | — | — |
| Masked TXD | 8101 | 10 | 0 |
| Full-rate register | 8127 | 26 | 0 |
| Depth gather | 8128 | 1 | 0 |
| Negative IMNMX immediate | 8131 | 3 | 0 |
| Spill operand classification | 8143 | 12 | 0 |

`minmax-camera-only` exits 0 at 6200 requests after 163.391 seconds, with
241 distinct native failures and 11 downstream failures. `spill-camera-only`
replays the same small right-stick turn and return from the same cloned save,
with EXE SHA256
`56e403b4b24087e2297edff2eabad69c6ec08f08533405bbb1377835b783c6c9`.
It exits 0 after 163.625 seconds, with 229 distinct native failures (no repeated
native messages), 11 downstream failures and 23 actively selected failed native
stages. The 5200 dump has zero rejected draws, versus two before, but still 17
blocked compute dispatches. It records a real pipeline using vertex shader
`3c18ee4ecd8da239`, SPIR-V `97444487a5e284b9`. The second formerly rejected
shader is accepted by lowering but is not present in this frame's pipeline list.
This distinction matters when scene visibility differs. Captures after PC FSR
exist through 6200; the last periodic accepted-presentation report is 6000.
Validation is disabled for these image comparisons, so their zero validation
counters are not a clean-Vulkan claim.

The small camera turn shows shadowed 3D scenery and a responsive view. It does
not reproduce the earlier larger movement-and-turn sequence. Neither restored
draws nor bound texture handles identify the affected material as tree foliage.
The suggested foliage explanation remains a hypothesis. Missing compute work
and direct-pool descriptor resolution remain concrete rendering blockers.

After these source changes the pool probe passes 5,270 checks with zero core
validation errors. All 583 probe cache modules and 1,009 game cache modules
pass `spirv-val --target-env vulkan1.3`; this checks structure, not image
semantics or descriptor contents. All 15 host probes and 17 project tests pass.
Translator SHA256 remains
`8e3035cf53eb13a757fe47ffb2f7f3ab056ea25cebb6e043a171f5f539095d8c`.
Lowered instruction changes select new cache entries; no old result is forced
onto a repaired shader. No game-derived inputs, modules, saves or captures are
committed.


## Larger camera movement and visibility counters

The continuation preserves all 551 generated game objects. The signed
zero-product IMAD-with-carry form now accepts the same narrow identity as its
unsigned form. The original CPU fixture passes 18,432,103 checks; the extended
pool probe passes 5,991 checks with zero validation errors. Native lowering
accepts one additional shader, but the downstream translation of that program
still fails in the camera capture. This arithmetic correction is not presented
as the camera fix.

`carry-movement-camera` and `camera-large-only` reproduce the white scene.
The depth prepass contains scenery, while the main opaque color pass draws only
73 objects in the first capture. A diagnostic forcing the material depth test
passes more geometry but gives incorrect occlusion. It is not retained.
A separate diagnostic replacing zero sample counts with one restores 973 opaque
draws with their normal depth test. The user's manual camera-test executable is
a preserved copy of that diagnostic, with an isolated cloned save and automatic
input enabled. It is a workaround, not proof of correct counter semantics.

The first production correction keeps samples-passed counting active after a
report. Reports snapshot a cumulative counter; they do not stop or reset it.
The original GPU triangle fixture verifies consecutive reports, pass/submission
boundaries, resets, an empty scissor, repeated reports and surrounding canaries.
It fails before the correction and passes afterward (2,674 checks, zero failures
and zero Vulkan validation errors). `camera-counter-fixed` exits normally after
8,000 requests but still shows whitening. This genuine defect was not sufficient
to resolve the game symptom.

`camera-query-trace` records 1,918 sample reports at request 6200, including 863
with no contributing query. The old pending-report ring held only 256 entries.
Eviction could make a conditional draw consult stale host memory for a report
that had not completed. An original GPU regression records a visible triangle's
sample report, then 1,025 other reports, and conditionally draws the triangle
in the same submission. The old ring suppresses all 288 covered pixels. The
replacement retains all unfinished reports and discards only completed entries
in submission order. This regression and the preceding geometry/counter tests
pass together (4,728 checks, zero failures and zero validation errors).

Opt-in `TOTK_QUERY_TRACE=first-last` diagnostics correlate draw state, report
recording and completion, and conditional host reads by presentation request.
These traces do not change query results. Normal operation performs no trace
logging. Gameplay verification of the pending-report correction follows below.

The separate `camera-condition-trace` run aborted while loading gameplay, before
its target frames, with a host-import range error for a 2.375 GiB memory pool.
It produced no camera evidence and is excluded from image comparisons.


The retention regression also checks completed true and false comparisons and
a later timestamp report overwriting an earlier sample report at the same
address. The resulting geometry suite passes 6,781 checks with zero failures
and zero Vulkan validation errors. The broader `probe-vkexec` command cannot
run its draw/xfer suite in this workspace because its separate legacy shader
census (`build/v*/shaders/jobs.json`) is absent; this is not recorded as a pass.

`camera-pending-fixed` reaches request 6200 and captures the main passes, but
hits the runner's 350-second timeout while completing that capture. This run
therefore provides frame evidence, not a successful 8,000-request completion.
Its main color pass contains 935 draws (versus 70 with only cumulative counting
fixed). At request 5800 the large white washout is gone. At 6200, 1,700 of
921,600 main-pass pixels still have all RGB components above 2.0; every one is
unchanged from the sky pass, despite non-clear depth at those pixels. These
remaining narrow gaps are investigated separately from lighting and shadows.
The trace contains 1,802 conditional reads with an unfinished sample result,
which are now retained as unknown rather than read from stale host memory.

The checkpoint seed's 16 file hashes still exactly match the pre-test manifest.


`camera-pending-lequal` completes 8,000 requests normally in 394.078 seconds.
Its temporary diagnostic changes only the main opaque comparison from EQUAL to
LEQUAL. The selected main pipeline confirms compare=4, but 1,750 bright pixels
remain unchanged from the sky pass, versus 1,700 in the preceding capture.
The changed comparison is not retained in source or the canonical executable.
This comparison does not support a simple strict-equality-only fix.

`camera-depth-rebuild` completes 6,400 requests normally in 367.375 seconds.
For request 6200 only, a diagnostic clears the main color pass's copied depth
image and rerenders those materials with LESS and depth writes. No bright
RGB>2 pixels remain in that main pass. Depth equals the original prepass at
910,554 of 921,600 pixels. Color geometry is nearer at 8,716 pixels and farther
at 2,330; the latter differences span 15 to 658,252 positive float ULPs.
This demonstrates a localized disagreement between the two passes, not a
uniform one-bit rounding error. Rebuilding depth would bypass the game's
prepass masking contract and is not retained as a production fix. The next
trace correlates actual draw arguments, vertex input state and CPU-visible
object matrices within a single normal frame.


The first `camera-geometry-inputs` run stayed in the title menu: the PC settings
menu was open during its scripted load inputs. Its 8,000-request exit is not a
gameplay result. Earlier `camera-pending-lequal` logs also contain PC-menu opens,
so its exact motion timing is not a controlled comparison; the surviving gaps
are still directly observed. `camera-pending-fixed` and `camera-depth-rebuild`
have no PC-menu-open entries. Automatic runs now use the existing
`TOTK_BACKGROUND_WINDOW=1` option and the geometry trace is repeated with early
checkpoint screenshots to verify that the save actually loaded.

The corrected `camera-geometry-inputs-background` run completes 8,000 requests
in 297.204 seconds with process exit 0. Its 241 known shader failures keep the
runner's diagnostic status nonzero. Resized captures at 6200 and 7800 show
narrow bright edges without the earlier large washout. The trace correlates
919 depth/color draw keys (vertex buffer/state, index buffer, count, instances,
base vertex/instance, and the first 12 object-matrix words). Other depth passes
are included in the raw trace and must not be confused with the main prepass.
The depth copy is bit-exact in `camera-pending-fixed`: all 921,600 original
prepass depth values equal the main color pass's copied depth values.

The updated manual launcher uses the real counter fixes without forced
visibility or altered depth tests. The user's `manual-31698` test reports no
camera flashes after leaving the house, but remaining rendering errors.
Its largest measured stalls are predominantly graphics pipeline compilation:
frame 19970 takes 3449.0 ms, including 3345.1 ms pipeline construction and
48.1 ms shader translation. This explains that measured stall, not every
possible performance dip. The manual test profile and recorded input remain
separate from the original save. Further diagnosis targets the indoor gaps.

### Local-memory load ordering in the shader optimizer

The temporary `camera-depth-ids` capture identifies all 1,700 bright main-pass
pixels with two house meshes (1,679 and 21 pixels). Both use the same native
color vertex shader. Its translated position expression incorrectly contains
lighting values: expression propagation moved a private-memory load past a
later store to the same register-spill slot. The depth-only shaders do not have
that expression, so the two passes disagree about the house surface positions.
The annotation experiment completes 6,400 requests with process exit 0; its
draw-state modifications are removed after the capture.

Translator patch `0021-preserve-local-memory-load-order.patch` keeps assignments
from local-memory loads at their original statement. Arithmetic propagation and
unused-load removal remain enabled. The vendored Ryujinx tree is unchanged.
An original Maxwell GPU fixture stores a color, loads it, overwrites the same
private slot, then uses the loaded color. The old translator fails all covered
triangle pixels (3 failed assertions). With the patch, the geometry suite passes
6,781 checks with zero failures and zero Vulkan validation errors, including the
cumulative-counter and pending-report regressions. Both default and optional
translator preparation modes pass the six existing build-option checks.

The corrected `camera-local-order-fixed` game run completes 8,000 requests in
425.562 seconds with process exit 0. The selected 1280x720 main pass now has
zero pixels with all RGB components above 2.0, compared with 1,700 before the
patch. Resized captures at 6000, 6200 and 7800 also show the indoor cracks gone.
The normal EQUAL depth test and the game's prepass are preserved. All 807 SPIR-V
modules from the run pass `spirv-val --target-env vulkan1.3`. Validation layers
were disabled for this game run; the existing 241 shader failures keep its
diagnostic exit status nonzero. No active graphics-stage lowering failure or
PC-menu-open event appears in this run. These are bounded results, not a claim
that every remaining graphics defect is fixed.

The native high-register geometry probe separately passes 6,781 checks and the
compute/resource probe passes 5,991 checks, both with zero failures and zero
Vulkan validation errors. The compute probe requires `TOTK_FIX_C0=1`; an initial
invocation with the geometry probe's setting was rejected before running tests.
The final post-capture camera segment averages 58.4 fps; its largest stall is
555.3 ms, including 396.4 ms pipeline construction and 64.4 ms translation.

The canonical and manual test executables now match the game-tested binary
(`60f7e9c7cd6e87d25b8404fc0d0c44786089fdb0ac8580100c693831687c1066`).
Both use the corrected translator beside the executable. Normalizing the new
patch's line endings after the game capture changed only the source identity
from `1fcc36455f5523eb` to `9b1980b46ad9e750`; the translator binary is unchanged.
The launcher preserves the user's separate manual profile. All 16 checkpoint
seed files still match the pre-test hash manifest. Shadows remain deferred.

### Outdoor atmosphere and fragment-depth exports

The user confirmed the remaining overexposure is mainly outdoors and closed
the manual test. `outdoor-manual-replay` replays the first 40 seconds of the
recorded inputs against a copy of that profile. It completes 8,000 requests
with process exit 0 and 242 known shader failures. At capture frame 6500,
the main scene's median linear luminance is 0.020825 after pass 178; the
fullscreen fog composition in pass 180 raises it to 0.37872. This locates the
large lift before the PC presentation/color controls. Those controls remain
at their defaults.

The requested Lichii review found commit
[`f26ad432ae0a09da4b888b297afa67d7f4e2a9c2`](https://github.com/zortos293/Lichii/commit/f26ad432ae0a09da4b888b297afa67d7f4e2a9c2):
query-cache/DMA ordering, sky-ambient buffer pointers and uniform-buffer
refreshes address related rendering symptoms in its emulator architecture.
Its own sky-ambient diagnosis explicitly leaves the outdoor haze unresolved.
Our `outdoor-clear-trace` records 68 clears and no clear whose condition
depends on an unknown sample count, so its stale-query clear explanation is
not established for this capture. No upstream renderer implementation was
copied into the MIT runtime.

An independently authored pending-counter fixture nevertheless demonstrates
that treating an unfinished sample report as visible can execute a false
conditional clear. Replay now resolves the recorded GPU prefix when required,
keeping callback ordering and avoiding double accumulation. The fixture fails
before the change and passes afterwards; additional cases cover multiple
prefixes, interleaved timestamps, repeated writes and resets. The
`outdoor-pending-exact` run completes 4,800 requests, process exit 0, but the
excessive haze remains. The last measured 60-frame interval averages 60.1 fps;
the raw frame capture itself causes a large diagnostic stall.

A separate concrete translator defect explains the all-zero half-resolution
depth image. Shader `954261b81af3be1e` has color mask `0x10f`, reserving two
four-register color groups, followed by sample-mask and depth slots. Ryujinx's
color export already uses those groups, but `GetDepthRegister` counts enabled
components and reads unwritten R6 instead of R9. The generated SPIR-V therefore
stores literal zero to `FragDepth`. Patch
`0022-count-fragment-output-register-groups.patch` derives the depth register
from the number of enabled targets, keeping the vendor tree unchanged.

This agrees with Lichii and Eglantine's `ExitFragment` behavior in
[`exit_program.cpp`](https://github.com/Djihads80/Eglantine/blob/0ca2032bffc5f1a3fca75427f7d4a4718adda660/src/shader_recompiler/frontend/maxwell/translate/impl/exit_program.cpp),
consulted as a behavioral reference. The patch is an original correction to
the MIT translator. Six original Maxwell depth-export fixtures cover no color,
full RGBA, partial components, nonadjacent targets and all eight targets.
Three fail with the old translator; all pass with patch 0022. The extended
geometry/visibility suite passes 15,000 checks with zero failures and zero
Vulkan validation errors. Six translator-build preparation checks pass.

The requested [Eglantine v0.1.0-rc1 release](https://github.com/Djihads80/Eglantine/releases/tag/v0.1.0-rc1)
is explicitly marked broken by its maintainer, who directs users to Build 212.
Its binary was not installed. Repository code was inspected for relevant
behavior; no blanket upstream update was made.

### Rejected expansion and supplied shader-cache reference (2026-11-06)

The broad lowering experiment enabled expensive title/movie upscaler kernels:
two calls of one kernel took approximately 83–94 ms each, and another took
45–52 ms each. Removing the additional UIMAD form restored approximately
60 fps in the subsequent focused outdoor capture, but the scene still had
excessive haze and incomplete tree crowns. Supporting float reduction then
caused the user's reported all-white regression despite passing arithmetic
fixtures. That experiment is rejected. Its binaries and patch 0023 are
quarantined outside the source tree; the production lowering header and pool
probe were restored, dispatch timing instrumentation removed, and the restored
pool suite passed 5,991 checks with zero failures and validation errors.
The normal and manual camera executables remain SHA256 `60f7e9c7cd6e87d25b8404fc0d0c44786089fdb0ac8580100c693831687c1066`;
the installed translator remains `10346ad4cff0e2bc0a12fbb797c94fb12af80b61da5b33f6c8bfa4d0076486f1`.

The user's RAR contains only `vulkan.fork-v50.bin` and its usage index. The main
file is an emulator pipeline cache with `yuzucach` magic and version 50, not
native `.spv`/resource metadata. A complete, boundary-checked parse consumes
all 439,490,523 bytes: 10,946 pipelines, 20,752 environments, 9,841 unique code
blobs, and 1,140 compute records. The code retains native instruction address
maps, constant-buffer observations and pointer classifications. It remains
outside the public repository and was not copied into the installed cache.
The desired screenshot was downscaled before inspection; it shows dense
foliage and localized lighting rather than the observed pale outdoor blanket.

Seven of fourteen selected captured compute stages have strong ordered-code
matches in the archive (90–99.6% identical ordered Maxwell instructions).
Native instruction count alone is insufficient: the apparent count match for
`3de6d86ec7e6720e` is unrelated and was discarded. Record 1480 closely matches
`383a566958350efe` (97.7%, matching workgroup size and shared-memory allocation).
These matches aid diagnosis but do not establish ownership of tree foliage.

The isolated translator candidate handles a dynamically indexed constant-bank
pointer by considering the driver's declared buffer ranges, retaining the
existing runtime address and extent checks. Its candidate traversal excludes
select conditions, comparison inputs and floating arithmetic inputs from
pointer-base discovery; treating numeric camera parameters as pointer origins
had exhausted the descriptor limit. This is independently authored MIT code,
kept outside the installed bundle. The candidate uses no cached emulator
addresses or shader-specific allowlist.

Original GPU fixtures exercise three buffer selections, direct driver-table
and indirect user-UBO pointers, padded root tables, 64 floating inputs used to
compute an address offset, invalid pointers, misalignment and range ends.
The old translator reports 19 failures (18 expected data mismatches plus its
translation-failure check). The candidate passes the complete extended pool
suite: 6,076 checks, zero failures, zero Vulkan validation errors. Four captured
compute stages translate and validate with Vulkan 1.2 SPIR-V rules:
`383a566958350efe`, `3de6d86ec7e6720e`, `4247f1b4c3ce6cf3`, and `f0fed2bbccae7bdc`.
Their jobs include the actual control-block shared-memory size. The other
selected stages still require float atomics or subword global loads.

The prepared manual test pairs the previously game-tested focused lowering
executable (`4e127055cab364eb7c1dace9d0967e3cc46a9505444edf567f4ccc091fc68f4a`)
with the isolated translator (`0f21202685135c38820f25d9e06895b240dba1d45f157707ac944dc4821b6518`).
It excludes the rejected float-reduction experiment, uses a separate shader
cache and a verified copy of all 25 files in the manual test profile, and has
no scripted inputs. The user completed this test and reported stable frame
rates but unchanged excessive outdoor brightness, then confirmed the game
was closed. The manual log ends normally on window close and its last interval
reports 59.8 fps. Foliage correctness is still unverified and this candidate
does not solve the reported lighting defect.

The bounded `light-composition-trace` run subsequently completed 4,200 requests
with process exit 0 and reproduced the excessive haze. Its capture records
the full-screen atmosphere composition at pass 180. Comparison with the user's
archive finds all 805 substantive lowered instructions of the composition
shader and all 155 of the volume integration shader identical, apart from
padding/termination. This narrows the investigation but does not establish
correct backend translation, resource bindings or shader input values.

The user now explicitly requests continuation without creating another build.
Further investigation therefore uses the existing executables, shader archive
and captures. The already prepared `oot2026-fog-diagnostic.exe` isolates the
atmosphere draw for frames 3400–3699 and records its CPU-side uniform buffers;
it is a diagnostic executable, not an installed visual fix.

### Confirmed foliage execution gap (2026-11-06)

The user explicitly redirected the investigation to tree foliage. Offline
analysis of the existing RomFS index and Foliage shader package now connects
the missing vegetation to concrete unsupported stages and command entry points.
No new build was made after the user's prohibition, and no production code or
installed cache was changed by this analysis.

The package `Shader/Foliage.Product.110.product.Nin_Ounce_NVN2.bfsha.zs`
decompresses to 3,493,224 bytes. Its 14 shader-model records point to bounded
BNSH sections and name groups including `leaf`, `leaf_near`, `forest`,
`low_tree_impostor` and `low_tree_shootleaf_impostor`. Comparison requires the
entire captured code, not just a shared prologue. It finds 109 exact stage
matches. The NVN2 control byte at offset `0x56` distinguishes 52 mesh stages
(7), 5 task stages (6), and 52 fragment stages (1). All 57 task/mesh stages
fail in `manual-light-buffer-29584/game.log`; 14 fragment stages also fail.
Shared short fragment code is present in multiple groups, so its presence in
a graphics pass does not establish that the foliage geometry rendered.

| Foliage group | Captured task/mesh stages | Rejected in manual log |
| --- | ---: | ---: |
| leaf | 4 | 4 |
| leaf_near | 4 | 4 |
| forest | 4 | 4 |
| low_tree_impostor | 4 | 4 |
| low_tree_shootleaf_impostor | 4 | 4 |

For example, `leaf` mesh shader `60dbd7f60c759472` fails on its ISBERD input
buffer access at native offset `0x10`; `forest` task shader
`f0212fc90ccb6d10` fails at offset zero. The current lowering infers conventional
graphics stages from SPH bits and does not preserve the control block's task/mesh
identity. Consequently log labels such as "stage 1" or "stage 3" describe SPH
fields here, not proof that these are ordinary vertex or tessellation programs.

Independently of shader translation, manual log lines 292 and 451 state that
`nvnCommandBufferDrawMeshTasks` and `nvnCommandBufferDrawMeshTasksIndirect` are
accepted but not recorded. Both are `NVN2_NOT_RECORDED` stubs in
`runtime/nvn_api_nvn2.c`. The runtime therefore has no mesh draw to replay.
The reported zero ordinary draws skipped does **not** include these discarded
mesh calls. Improving a compute translator or adjusting brightness cannot
complete this missing rendering path.

The Lichii source at commit `27226d2568c99c70cf78aa37adaf98b60457b2e5`
provides a relevant reference: its
[stage model](https://github.com/zortos293/Lichii/blob/27226d2568c99c70cf78aa37adaf98b60457b2e5/src/shader_recompiler/stage.h)
contains Task and Mesh; its
[Ampere lowering](https://github.com/zortos293/Lichii/blob/27226d2568c99c70cf78aa37adaf98b60457b2e5/src/shader_recompiler/frontend/ampere/lower_to_maxwell.h)
preserves ISBERD/ISBEWR as special task/mesh operations; and its
[SPIR-V emitter](https://github.com/zortos293/Lichii/blob/27226d2568c99c70cf78aa37adaf98b60457b2e5/src/shader_recompiler/backend/spirv/emit_spirv.cpp)
emits TaskEXT and MeshEXT execution models. These are a coordinated frontend,
intermediate-representation and backend feature, not an isolated opcode patch.
The current Ryujinx-based translator enum has neither Task nor Mesh. No upstream
implementation was copied or installed in this investigation.

The repair must preserve NVN2 task/mesh identity, record direct and indirect
mesh commands and their ordering, translate stage-buffer/payload/output
operations, and create a compatible Vulkan mesh pipeline (or a verified
equivalent fallback). Required verification includes payload/index output,
indirect parameters, visibility ordering, actual leaf coverage in color and
depth, and a controlled outdoor comparison with the user's reference. The
rejected float-reduction experiment remains rejected; fragment reduction is
a separate blocker to retest after the geometry path works. The share of
overexposure caused by missing foliage remains unmeasured.

Local reproducible evidence lives outside the public repository in
`work/identify_foliage_shaders.py` and `work/foliage-investigation/` in the
continuation workspace. The script reads the existing asset image, validates
container bounds, compares full code, and links matches to the completed manual
log. It neither builds nor launches the game. The existing diagnostic run has
ended; no game is left running.

### Branch `test2` build and outdoor verification (2026-11-06)

The translator was rebuilt from `third_party/dkb/tools/build_xlate.py` with all
26 patches present; 0001-0013 and 0015-0026 applied (0014 stays optional), giving
translator identity `f4c6681855057144`. The runtime was linked incrementally
from the existing game objects into a separate `oot2026-test2.exe`, so the
regular executable and translator stay untouched. The build had no errors.

Checks of that build:

| Check | Result |
| --- | --- |
| `test_full_runtime.py` default modes | 14 of 15 passed; `probe-kernel` failed once with `plat_cond_wait_ns timeout` and then passed 3 of 3 repeats, as the previous executable did |
| `--probe-vkmesh`, validation on | passed, 16419 checks, 0 validation errors |
| `--probe-vkexec`, validation on | failed: `no build/v0/shaders/jobs.json above the exe`; the previous executable fails identically, so the fixture is missing here |
| `render_regressions.cpp` | 16180778 checks, 0 failures |

The outdoor replay ran with a copied profile and a new, empty shader cache.
With `TOTK_VK_VALIDATION=1` the run aborted near frame 1800 on an uncaught
`std::system_error` (`Invalid argument`). The terminate message is libstdc++'s,
while the runtime uses libc++; the only libstdc++ component in the process is
the MSYS2 validation layer, so the abort is attributed to the layer, not to the
fix. Up to that point the layer reported no task or mesh message. It reported 10
`VUID-vkCmdDrawIndexed-None-06479` errors (depth comparison on RGBA8, BC and
RGBA16F views in fragment shaders), so 0025 does not remove that VUID. The same
replay without validation ran to completion.

Log lines without validation: `vk: enabled task/mesh features: task 1 mesh 1`;
`requiredSubgroupSizeStages 0xf0, pinning 32 on 0xf0`; no `is recorded but not
executed`, no `graphics pipeline not built`, no `mesh stage lacks fragment
inputs`, no task/mesh subgroup-pin message. `mesh: draw skipped: mesh stage
was not lowered` reached its 32-line limit, with 8 `mesh: draw not prepared`.

The white image seen earlier the same day with patches 0023 and 0024 does not
occur with `test2` (mean 8-bit screenshot brightness 159-165 against 155-172
for the previous executable). 0023's AND-then-OR small stores are the likely
cause, with 0024 only making the affected compute programs translatable; 0026
replaces those stores.

Fog composite at frame 3900, linear Rec. 709 luminance of target
`0x80003c0200` from raw R11G11B10F dumps:

| Build | Before composite, median / mean | After composite, median / mean |
| --- | --- | --- |
| previous executable and translator | 0.059 / 0.198 | 0.298 / 0.419 |
| `test2` | 0.025 / 0.167 | 0.274 / 0.383 |
| `test2` with the lowering forms below | 0.048 / 0.205 | 0.303 / 0.444 |

The composite still multiplies the median several times. The haze remains, and
no tree crowns are visible in the frames 3200-4000.

Following the skip reason, the Eglantine lowering gained Lichii v13's forms for
SHF.R.U64 with an immediate or register amount, USHF.R.U64, USHF.HI with an
immediate source, UPOPC, and UMOV, UFLO and UBREV from any mapped uniform
register. On the 8382 dumped stages, 35 more lower, none is lost and no
previously lowered stage changes. The `uniform shift` and `funnel-shift`
rejections in the game log fall from about 75 to 2, the task stages that now
lower run without the former `synthetic c0` abort, and vegetation mesh shader
`5cb142ded77487e9` executes. The next rejection for 21 vegetation mesh stages
is `native uniform arithmetic register`: they write UR28 and above, which
Lichii maps through its dynamic high-uniform register range. Thin bluish
streaks appear in frame 3900 only in the runs with these extra lowerings; they
may be a new artifact of the newly executed mesh shaders and are not resolved.