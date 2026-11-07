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

10. **Next task: the crown draws run but draw nothing. Suspect the blocked GPU culling chain.** Point 9 got the
    crown mesh stages lowered, and their draws now run in pass 113/114 and in the shadow cascades. They still
    change 0 depth pixels. In the frame-3900 dump of `run-p9-dump-233330`, ten **indirect compute dispatches** at
    the very start of the frame are `blocked dispatch ... reason shader translation`:
    - **The blocked dispatches:** progs 13594, 13610, 13394, 13613-13617, 13426 and 13431, with indirect args at
      `0x29bb4c000`/`+0x10`/`+0x20`, `0x29bb8a000`/`+0x10`/`+0x20`, `0x29f6c2000`, `0x29f9aa000`, `0x2a18ce000`.
      Their native shaders are `44511d69b52282ad`, `4247f1b4c3ce6cf3`, `6344c53d07706e30`, `3de6d86ec7e6720e`,
      `102f5b0abb0f1e63`, `abccf81b45c5eb50`, `7650519f88e59b19`, `cb2e06ddfb9d7d27`, `f0fed2bbccae7bdc` and
      `383a566958350efe`. Most are lowered by the Lichii fallback.
    - **Why they matter:** the crown draws read their indirect arguments at `0x29bc50000`, `0x29bc68000` and
      `0x29bd6c000`, in the same arena. This looks like the GPU-driven culling that writes those arguments. If it
      never runs, the crowns get 0 groups.
    - **Why they fail:** these shaders fail in the translator's storage-candidate path (patch 0015/0023): 30x
      unaligned/odd-size loads, 20x non-32-bit atomics, 12x descriptor limit, 9x no cbuf pair. The old messages did
      not say what the shader asked for.
    - **New patch `0027-storage-candidate-failure-details.patch`** (`build_xlate.py` expects 27): the messages now
      name the load/store `LsSize`, the atomic `type`/`op`, the candidate count and failing cbuf slot/offset, and
      the operation for the cbuf-pair case. It changes messages only, no behaviour. Checked here with `git apply`
      over the full chain. Note: the lowerings only emit LDG sizes 0-6, so if the load failures really report
      `UB128` (7), check where a size-7 LDG comes from.
    - **Do:**
      - Rebuild the translator and use a new cache.
      - In the runtime, log the native hash and program for every failed translation (today
        `vk: a stage 5 shader of program N failed to translate` is logged once only).
      - Map the ten blocked dispatches to their exact failure messages.
      - Read back the crown draws' indirect buffers after GPU execution (`TOTK_DUMP_BUF`). Are the group counts 0?
      - Then extend the storage-candidate path for exactly the forms these shaders need. For example, if
        the atomics are 64-bit or INC/DEC, add a CAS loop as patch 0024 does. Raise the limit for the descriptor
        cases. `0` lost and `0` changed in `lower_probe` does not cover this, so check the translation-failure count
        instead.

11. **Next task: let the culling shaders translate (patch 0028), then look at the white image again.**
    Point 10 proved that every indirect mesh draw gets 0 groups on the GPU, and 7 of the 8 blocked culling dispatches
    fail with `Storage candidates exceed the descriptor resource limit` (19 to 103 candidates).
    - **The limit was a hard-coded array in the translator** (`ResourceManager.cs`, `_sbSlotToBindingMap = new
      SetBindingPair[32]`, patch 0012). It is no device limit: every guarded candidate takes one storage slot, and
      guarded and unguarded slots share that one array.
    - **Patch `0028-two-hundred-fifty-six-storage-slots.patch`** (`build_xlate.py` expects 28):
      - The array grows to 256 slots.
      - `_sbSlotWritten` was a 32-bit mask (`1u << slot`). Past 32 it would have aliased slot n with slot n % 32 and
        wrongly marked buffers as written or not written. It is now one `bool` per slot.
      - Checked here with `git apply` over the full chain; not compiled.
    - **Runtime:** `MAX_BINDINGS` 128 -> 512 (`vk_exec_draw.c`, `vk_pipeline.c`), `MAX_DESC` 1024 -> 2048
      (`vk_exec_draw.c`). The same constants are mirrored in `tests/descriptor_empty_set.c` and
      `tests/geometry_replay_test.py`. The descriptor pools hold 2048 storage buffers each, so one set of 256 fits.
      Not checked: device `maxPerStageDescriptorStorageBuffers` (large on desktop AMD). Log it once.
    - **Test:** `tests/xlate_storage_candidates_test.py` `test_descriptor_limit_rejects_instead_of_truncating` now uses
      255/256 candidates (256 slots accepted, 257 rejected). Not run here.
    - **Do:**
      - Rebuild the translator (28 patches) and the runtime, and use a new cache.
      - Run the storage-candidate tests and the render regressions.
      - Forest run:
        - How many translation failures remain?
        - Do the 7 culling dispatches run?
        - Read back the crown indirect args again (`DKB_MESH_TRACE_INDIRECT`). Are the groups non-zero?
        - Are crowns visible?
        - What is the fog luminance?
    - **White image with 0024:** patch 0024 itself looks right: a CAS loop for `RED/ATOM.ADD.F32`, returning the old
      value. Likely mechanism: before 0024 the sky-ambient and light-accumulation shaders failed translation and never
      ran. With 0024 they accumulate, but whatever clears or normalises those buffers (or the counts they divide by)
      may sit in the still-blocked shaders, so values grow without bound. Re-check the white image **after** 0028.
      If it is still white:
      - Find the accumulation buffer the 0024 shaders write (by its dispatch).
      - Check whether a clear or divide pass for it is skipped. Dump the buffer over a few frames: does it grow every
        frame?

12. **Findings from another OoT2026 recomp (NVIDIA-tested notes `oot-lighting-fixes-amd-test.md`), mapped to ours.**
    Reference: the Lichii emulator on the same RX 7900 XTX renders Kokiri Forest correctly, with a dark forest, the
    canopy present and little haze. So driver and hardware are fine.
    - **Ballot folded into a one-lane branch: missing canopy and too bright (their fix 1). Present here, patched:**
      - Our translator runs the AST optimizer, because the runtime sends `"debug":false` (`gfx_shader.c`), and
        `AstOptimizer.Optimize` propagates single-use temporaries.
      - The culling shaders do `m = VOTE.ALL`, then add `POPC(m)` to a counter from the first lane only. Folding the
        ballot into that use moved it inside `if (lane == first)`, where it counted 1 lane, so the visible lists kept
        about 1 entry in 32. They measured 138-181 workgroups before and ~4580 after, with the canopy back.
      - New **`0029-keep-votes-where-they-run.patch`** (`build_xlate.py` expects 29): a temporary whose expression
        contains Ballot, Vote* or Shuffle* is never propagated. Checked with `git apply` over the chain; not compiled.
      - **Use a new shader cache:** every shader with a vote or ballot changes.
      - After 0028 and 0029, check that the crown/foliage indirect groups (`DKB_MESH_TRACE_INDIRECT`) are in the
        thousands.
    - **Subgroup size (their main AMD risk):** the compaction assumes 32 lanes. Confirm in the log that every compute
      pipeline with votes/ballots is pinned to 32 (`subgroup pin 32 on stages 0xf0`, compute 32). Report any that is not.
    - **Pointers loaded from memory (their fix 2):**
      - Our 9 `No bounded cbuf-pair candidate found for global operation (Load, GlobalMemory)` failures, including
        the culling shader `383a566958350efe`, are this case: the address comes from a pointer that was itself
        loaded from memory, not from a cbuf pair.
      - Their fix follows such pointers, each access guarded by a bound length. They cover four shapes:
        - a word of a uniform block
        - an entry of an indexed uniform array
        - a one-hop holder behind a `c[0]` descriptor
        - a phi of `c[0]` descriptors plus a constant
      - Extend `GlobalToStorage` the same way, and port the behaviour, not their code.
    - **Exposure meter range (their fix 3):** the exposure compute reads baked light probes ~121 MiB into a table
      behind a stored pointer. Their 64 MiB read cap left the sum at 0 and pre-exposure at 2^-10. Check our guarded and
      pointer storage range cap (`bind_range` `max`, `vk_exec_draw.c` `ssbo_info`/`guarded_storage_binding`) for a
      similar limit. Raise it to 512 MiB, still bounded by the mapping. Credit: seedds/nxnative (MIT).
    - **Conditional clears (their fix 6):** the engine sets a report record to 1 from the CPU, then clears under a
      condition on it. A known report value may stand only until its submission completes. After that, read memory.
      Check our conditional-render/report path (`vk_sync.c`, visibility records). Credit: seedds/nxnative b1d7c707 (MIT).
    - **Read-only dispatches writing back (their fix 7, a white flash):** applies only if guest memory is mirrored.
      The sky light block is zeroed by the CPU every frame and summed by compute atomics; dispatches that only read it
      copied old bytes back over the zero. This may also be the patch-0024 white image: check after 0028/0029.
    - **TLD4 `.F16.RN`, bits 79-80 (their fix 8):** bars/black picture above 953x536 in the upscaler networks. Check
      that our TLD4 lowering and decoding keep the F16 field as TEX does.
    - **Do not** scale fog or exposure to hide the fault.
    - **Fragment depth register (their fix 5):** already ours, adapted from our patch 0022.
    - **Licensing:** these notes describe behaviour, so write our own code. Where a fix credits a project, name it in
      the commit and in `THIRD_PARTY_NOTICES.md` if code is reused.

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
     `third_party/dkb`, run `python tools/build_xlate.py`. It must apply all 27 patches (0014 optional) and produce
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
