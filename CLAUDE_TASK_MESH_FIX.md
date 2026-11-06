# Task for Claude: build and verify the mesh/foliage fix

Paste this file into Claude Code in your OoT2026-PC-Recomp checkout, or tell it: "Read CLAUDE_TASK_MESH_FIX.md and do it."
Reply to the user in their language.

## Context

Branch `fix/mesh-foliage` in <repo-url> is based on `oot2026-pc-recomp` at
`68f5d8e` ("Lower Ocarina's blocked compute programs with Lichii v13's lowering"). It changes only two host files.
**Nobody has compiled it yet.** It was written by review, without a compiler.

Symptom being addressed (AMD RX 7900 XTX): tree foliage missing outdoors and a strong white haze. Per
`docs/EXPOSURE_AND_CONTROLS.md` ("Confirmed foliage execution gap"), foliage is 52 mesh and 5 task stages. The haze
rises in the full-screen fog composite (pass ~180). Working hypothesis, not proven: without the leaves, depth shows
sky or far distance, so the fog integrates over the full range and the haze appears. Fix foliage first, then measure
brightness again.

Changes in the branch (`git diff 68f5d8e..fix/mesh-foliage`):

1. `runtime/vk_exec_draw.c` `c0_info()`: task stages used to hit
   `rt_fatal("synthetic c0 is unavailable for stage 6")`. They now get their own c0 bank (`k = 3`, arrays
   `c0`/`c0_buf`/`c0_off`/`c0_valid`/`c0_in` grown from 3 to 4). `vk_c0_fill` already had the task table at 0x670.
2. `runtime/vk_pipeline.c` `create_graphics()`: a mesh pipeline whose fragment stage reads a varying the mesh stage
   does not write was silently dropped (`if (missing && mesh) return VK_NULL_HANDLE;`). Now the missing locations
   are added as zero-initialised per-vertex output arrays (`spirv_add_outputs_arrayed`, length from
   `OpExecutionMode OutputVertices`, helper `spirv_output_vertices`). If that is impossible, a log line explains why.
3. `runtime/vk_exec_draw.c` `op_draw_mesh()`: every early return now goes through `mesh_skip()`. It counts
   `draws_skipped` and logs `mesh: draw skipped: <reason>` (32 lines at most). A failed `prepare_draw` logs
   `mesh: draw not prepared ...`.
4. `runtime/vk_pipeline.c`: a log line when a task/mesh stage uses subgroup operations but cannot be pinned to 32 lanes.

5. **Branch `test2` only:** translator patch `tools/xlate/patches/0025-shadow-samples-stay-float.patch`
   (`build_xlate.py` now expects 25 patches). Patch 0019 typed every sampled image by the descriptor's format,
   depth-compare (shadow) samplers included. A shadow slot whose descriptor reports an integer format (the
   open `VUID-vkCmdDrawIndexed-None-06479` case, RGBA8 sampled with depth comparison) then produced an integer Dref image
   type, which is invalid SPIR-V. Shadow samples now always stay FP32, as before 0019. Behavioural reference: Lichii PR
   #273 ("keep depth-compare images floating-point even when a texture descriptor reports an integer format"); the
   code is written independently, nothing copied. Requires rebuilding the translator
   (`third_party/dkb/tools/build_xlate.py`) and a **new `TOTK_SHADER_CACHE` directory**. The translator id changes
   anyway. Checked here only with `git apply` against the full patch chain, with and without 0014.

6. **Branch `test2` only:** translator patch `0026-small-global-store-compare-and-swap.patch`
   (`build_xlate.py` now expects 26 patches). Patch 0023 stored 8/16-bit global fields with an `AtomicAnd` and then
   an `AtomicOr`. Two invocations storing different values to the same field ended up ORed together, and readers
   could see the field cleared in between. Patch 0026 uses one 32-bit compare-and-swap loop and re-reads the word
   atomically on every try, as patch 0024 does. Affected: the vegetation-culling/sky-ambient compute programs that
   the Lichii fallback lowers. Checked only with `git apply` against the full chain, with and without 0014.

7. **Branch `test2` only, after the 2026-11-06 run:** the Eglantine lowering now maps UR28 and up
   (`eglantine/.../ampere/lower_to_maxwell.h`, `LowerToMaxwell` wraps `LowerToMaxwellWith`). Mesh and task stages never
   take the Lichii fallback (`nvn2_lower.cpp`), so the 41 vegetation mesh stages rejected with
   `native uniform arithmetic register` (e.g. ULOP3 into UR28) and `native register-to-uniform mode` (R2UR into UR29)
   stayed unlowered. As in Lichii v13, a program that touches UR28+ is lowered again with that many registers
   reserved directly below R216, and native GPRs from there up are rejected as scratch. It is not combined with
   the native register spill path (that fails with `native register spill with uniform registers above UR27`).
   Lichii's register shadowing (`register_pressure.h`) is **not** ported. A stage whose native code also uses those
   GPRs now fails with `native program uses lowering scratch registers` instead.
   **Verify first with your offline `tools/lower_probe.cpp` over all 8,382 dumped shaders:** count newly lowered
   stages, and confirm 0 lost and 0 changed among stages that lowered before. Then rebuild, use a new shader cache,
   and repeat the outdoor run (Kokiri Forest, frames 3600/3900). Report the rejection-reason counts again and say
   whether the canopy and the light shafts change.

8. **Next task (not implemented, analysis only): light shadow maps come from wrong textures. Likely cause of the
   brightness and of `VUID-06479`.** All 20 `VUID-...-06479` messages come from one fragment resource,
   `fp_t2ds_cb0_40000000` (set 1, binding 23, a 2D shadow array). `game.log` reports it as
   `vk_exec: unresolved direct-pool resource: stage 1 binding 23 type 0x403 handle 0x40000000 cbuf 0 array 32`. Its
   sampler array is binding 55, same handle.
   - Handle kind 4 is Ryujinx `TextureHandleType.Direct`, from `BindlessElimination.cs`. The shader reads the handle
     from memory (a light table) and indexes the array with `min(handle & 0xfffff, 31)`: the **texture pool index**,
     clamped to the array length that `tools/xlate/Program.cs` `QueryTextureArrayLengthFromPool()` gives (32). The
     sampler index is `min(handle >> 20, 31)`. The texture pool has ~33,000 entries.
   - `runtime/vk_exec_draw.c` `bind_resources` fills element k from **bound slot** `r->slot + k`, and for kind 4
     `r->slot` is -1 (`gfx_shader.c` `handle_slot`). Element 0 is the dummy, and element k is bound slot k-1. These
     are unrelated colour textures (RGBA8, BC1, BC4, RGBA32F), and every light's shadow test compares against them.
     The result on AMD is undefined, and probably "lit". Lichii PR #354 found the same thing (a green tint on an
     RX 7900 XTX for them). Its fix: descriptor arrays over the handle-table entries, and the null image for
     depth-compare samples of formats that cannot be compared.
   - **Step A, a quick experiment that proves or disproves the brightness link.** Create a 1x1 `D32_SFLOAT` dummy
     (sampled, depth aspect). For elements of a shadow (`type & 0x400`) array whose image cannot be depth-compared,
     bind that dummy instead, in draws as well (the existing depth twins are dispatch only, see `tex_info`). Run
     the forest replay twice, once with the dummy cleared to 1.0 and once to 0.0 (env switch). Compare the fog
     composite luminance and screenshots. If the haze and the light shafts change strongly, this resource drives
     the brightness. Either way, `VUID-06479` should disappear.
   - **Step B, the real fix:** kind-4 elements must come from the **texture pool** (element k = pool id k, sampler
     element k = sampler pool id k), not from bound slots. The array also has to cover the pool indices the game
     uses: a larger `QueryTextureArrayLengthFromPool`, with a persistent descriptor set per pool (descriptor
     indexing, update-after-bind), or Lichii #354's approach of binding the entries the handle table names. The
     descriptor-set reuse key in `vk_exec_draw.c` (the `rs_add` loop over `r->slot + k`) must then include the
     pool identity, or sets go stale. First measure which pool indices the light table actually holds.
   - Checked here and fine: patch 0014 makes FMNMX and `.SAT` NaN-safe. `FSETP` comparisons match Maxwell. Not
     matched: F2I to S32/U32 with NaN or out-of-range input (raw `OpConvertFToS`), `.FTZ` is ignored, and no float
     controls are declared. These have lower priority.

9. **Next task: the tree crowns are blocked by CALL lowering (from the frame-3900 pass dump of
   `run-r2-shdoff-230911`).** Point 8 step A ruled the shadow arrays out as the brightness cause. In the dump, the
   only mesh draws blocked in the forest are `blocked mesh ... reason task/mesh pipeline missing`, 10 of them:
   - **Where they are blocked:**
     - pass 112, the 1280x720 scene: progs 4095 and 4070
     - passes 130 and 135, the **1600x1600 shadow cascades**: progs 4094 and 4090
     - plus passes 141, 164 and 167
   - **Their untranslated mesh stage (native-control-stage 7):** `907e1e206a9b2c8d` (4x), `10eff7e5af4f0329`,
     `be221d3fcf0326ab` (2x), `c049e63027bf4000` (2x), `d5f3434dcddac7cf`. The first three are rejected with
     `native call linkage mode` (e.g. `907e1e206a9b2c8d` at +0x7e0, insn `00007944 000011d0 03c00000 000fea00`).
   - **Why this matters:** these indirect multi-draws are the canopy, in the scene pass **and in the shadow maps**.
     Missing canopy in the shadow cascades also explains why the sun shafts and the lit haze go everywhere. This is
     now the main suspect for both symptoms.
   - **Cause:** Eglantine's `case 0x944` (`lower_to_maxwell.h`) accepts CALL.REL.NOINC only when the return-PC MOV
     (`MOV Rlink, (index+1)*16`) is directly before the CALL (only local stores 0x387 may come between) and the CALL
     comes before the main EXIT. These stages set the link earlier or call from a callee.
   - **Lichii v13 lowers these:** `lichii/lower_to_maxwell.h`, the `bounded_control` pre-pass before the main loop
     (`write_count`, `control_entries`, `bounded_links`, `checked_returns`, `dead_instructions`) and its `case 0x944`.
     It walks back to the return-PC MOV through instructions that do not overwrite the link, checks that no
     control-flow entry lies between, and checks that every callee returns through the link. Port that pre-pass
     into the Eglantine lowering. Mesh stages never take the Lichii fallback, so it has to live there. Adapt it to
     Eglantine's `high_uniform_base`.
   - **Already in this commit:** `c049e63027bf4000` failed with `native register spill operand shape` on R2UR
     (`000873c2 ...`): `NativeRegisterSpill::Prepare` did not list opcode 0x3c2. It now reads Ra at bit 24, like 0x3c4.
     Its destination is a uniform register, so there is no GPR to spill. Check it with `lower_probe` too.
     `d5f3434dcddac7cf` fails the mesh metadata check in `nvn2_lower.cpp` (threads/vertices/primitives). Log its
     values to see which limit it breaks.
   - **Then:** `lower_probe` (gained, 0 lost, 0 changed), and print the next rejection of `907e1e206a9b2c8d`,
     `10eff7e5af4f0329`, `be221d3fcf0326ab`, `c049e63027bf4000` and `d5f3434dcddac7cf`. Rebuild, run the forest
     again and dump the passes. Are pass 112/130/135 mesh draws still blocked? Are crowns visible? What is the fog
     luminance now?

Known and not fixed: an indirect mesh draw's group count is not clamped to `maxMeshWorkGroupCount[0]`/
`maxTaskWorkGroupCount[0]`. A GPU-side clamp would need a small compute pass.

## Steps

1. Get the branch and read the diff:
   ```
   git remote add oot-test <repo-url>.git
   git fetch oot-test fix/mesh-foliage
   git checkout -b fix/mesh-foliage oot-test/fix/mesh-foliage
   git diff 68f5d8e..HEAD
   ```
   For all fixes (0025/0026 included), use branch `test2` instead: `git fetch oot-test test2` and
   `git checkout -b test2 oot-test/test2`. The user wants `test2` built and tested.
   Check the changes against the surrounding code. Two points need extra care:
   - Are mesh output variables with an `OpVariable` initializer valid for MeshEXT?
   - Is `binding_span`/`fs_off` still correct when a task stage is present?
2. **Build a new executable. The user explicitly wants a fresh build of this branch**, even if earlier notes in
   the repo say not to rebuild. Use the existing local artifacts and do not re-extract, re-lift or regenerate
   anything:
   - **Branch `test2` only:** rebuild the translator first, because patches 0025/0026 live there. In
     `third_party/dkb`, run `python tools/build_xlate.py`. It must apply all 26 patches and produce
     `build/xlate/totk_xlate.exe`. If a patch fails to apply, stop and report which one.
   - Then do an incremental runtime build: `tools/build_full_runtime.py ...` as in `docs/FULL_RUNTIME.md`, or the
     existing `work/build_native.py`, with `--translator` pointing at the rebuilt translator.
   - Fix compile errors with the smallest change and keep the intent of each fix.
   - **Use a new shader cache.** Without one, old SPIR-V from before 0025/0026 can be reused. The cache directory
     is `TOTK_SHADER_CACHE`, defaulting to `shader-cache` next to the executable (`runtime/gfx_shader.c`).
     Do not delete the old cache, because it is needed for comparison. Either rename it
     (`Rename-Item shader-cache shader-cache-before-test2`) or set the variable for the run, e.g.
     `$env:TOTK_SHADER_CACHE = "<work>\cache-test2"`, using a new empty directory. An environment variable
     overrides `totk.ini`. The first run is slower because every shader is translated again. Afterwards, validate a
     sample of the new `.spv` files with `spirv-val --target-env vulkan1.3`.
3. Checks:
   - `tools/test_full_runtime.py <native>/oot2026.exe --logs <logs>/host-probes`
   - The authored mesh probe `--probe-vkmesh` and `--probe-vkexec`, with Vulkan validation enabled.
   - `third_party/dkb/tests/render_regressions.cpp` as described in `docs/FULL_RUNTIME.md`.
4. Bounded outdoor run: a **copy** of the test profile, the existing outdoor replay inputs, a new
   `TOTK_SHADER_CACHE` directory and `TOTK_VK_VALIDATION=1`. In `game.log`, collect:
   - `vk: enabled task/mesh features` and `requiredSubgroupSizeStages`
   - `mesh: executed native shader`, every `mesh: draw skipped:` reason, `mesh: draw not prepared`
   - `mesh: nvnCommandBuffer... is recorded but not executed`: names a mesh command form (3D/multi/count) that
     the game uses but the runtime does not execute yet. Report the logged name, args and caller, because that form
     is the next thing to implement.
   - `graphics pipeline not built`, `mesh stage lacks fragment inputs`
   - `Ampere lowering failed` for foliage shaders, e.g. `60dbd7f60c759472` (leaf) and `f0212fc90ccb6d10` (forest)
   - any `Vulkan validation:` message that mentions mesh/task
5. Compare with the earlier `outdoor-manual-replay` capture: are the leaves visible? What is the median linear
   luminance before and after the fog composite (the passes earlier measured as 178/180)?
6. If mesh draws are still skipped, fix the reason the log names. Prefer an exact fix over a workaround.
   Record results in `docs/EXPOSURE_AND_CONTROLS.md` in the existing style.

## Rules

- Game data, generated C, captures and shader caches stay out of git (`third_party/dkb/AGENTS.md`).
- Never use the user's original profile for tests. Always use a copy.
- Commit only on `fix/mesh-foliage`, and push only after the user agrees.
- Report what was actually verified, and say what was not.
