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
screen successfully loads the test autosave. Manual save/reload is still pending.
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
