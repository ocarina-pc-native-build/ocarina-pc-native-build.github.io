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
