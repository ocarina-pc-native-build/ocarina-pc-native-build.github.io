# Engineering status — 2026-11-06, outdoor lighting investigation

**Outdoor overexposure remains unresolved.** The user reported an all-white
regression in an isolated float-reduction experiment. That experiment was
rejected; the installed executable, translator and original manual launcher
remain at the earlier verified hashes. Following a later manual test, the user
confirmed that the game was closed and allowed diagnostic work to continue.
The supplied emulator shader archive is used only as an offline
reference, not installed as a native shader cache.

**The missing foliage now has a confirmed implementation blocker.** Exact
full-code comparison with the game's Foliage archive identifies 52 mesh and
5 task stage captures; all 57 fail in the user's last manual-test log. The
archive groups include `leaf`, `leaf_near`, `forest`, `low_tree_impostor` and
`low_tree_shootleaf_impostor`. That same log confirms that direct and indirect
mesh draws are accepted but not recorded. These entry points remain no-ops in
`nvn_api_nvn2.c`, and the translator has no task/mesh stage model. Asset/shader
availability is therefore not sufficient to render the foliage. This is an
identified cause of missing vegetation, not yet a fix or proof of how much
outdoor overexposure it explains. The user requests foliage as the priority
and explicitly prohibits another build. No build was created after that
instruction; the last diagnostic used an executable prepared earlier.

A separate indexed-buffer translator candidate passes 6,076 GPU checks with
zero failures and zero Vulkan validation errors; the prior translator fails
19 checks in the same new reproducer. Four previously rejected captured
compute stages now translate and pass SPIR-V validation. These tests establish
specific shader translation defects, not a visual lighting or foliage fix.
A separate manual test with a verified 25-file profile copy has now completed.
The user reports stable performance but unchanged excessive outdoor brightness;
the indexed-buffer candidate is therefore not a demonstrated lighting fix.
The subsequent bounded capture reproduces the white haze. On the user's latest
instruction, no further build is to be created; investigation uses existing
executables and captures. See the archive-assisted investigation
in [exposure and controls](EXPOSURE_AND_CONTROLS.md).

**The existing build reaches controllable 3D gameplay and reloads a regular
save. The tested camera washout and indoor bright cracks are corrected;
other rendering defects remain and the port is not fully verified as playable.** Tests continue from cloned
profiles and the existing generated game objects. Shadow rendering is deferred
at the user's request. Audible audio remains unverified.

The camera investigation found visibility-counter defects: reporting a sample
count stopped subsequent counting, and a 256-entry ring could forget unfinished
reports before their conditional draws. Original GPU fixtures reproduce both
failures and pass after their respective corrections. The cumulative-count
correction alone did not resolve the game symptom. A separate shader-optimizer
bug moved a local-memory load across a later store to the same spill slot,
corrupting house vertex positions. Keeping the load in place removes all 1,700
bright gap pixels in the selected main-pass capture. The corrected game run
completes 8,000 requests, and the original GPU reproducer, native high-register
geometry suite and compute/resource suite pass with Vulkan validation enabled.
The run still records 241 known shader failures; its successful process exit
does not mean every rendering path is supported. See the current evidence and
bounded gameplay results in [exposure and controls](EXPOSURE_AND_CONTROLS.md).
The earlier [new-game investigation](GAMEPLAY_BRINGUP.md) remains historical
evidence for the cutscene checkpoint, not the current failure count.

The earlier [video/title/menu checkpoint](RENDERING_BRINGUP.md) fixed the sRGB
storage-view issue and reduced its shorter path from 464 to 203 shader failures
and two to zero Vulkan errors. Those counts do not describe the longer New Game
path. PACGA and generated game compilation are preserved.

## Preserved compilation and PACGA

Continuation reused the normalized modules, generated C, existing object cache,
RomFS image, toolchain and prior results. Runtime fixes were incremental builds;
no reset, fresh extraction or full regeneration was used for this continuation.

| Module | Discovered functions | Lifted instructions | Unsupported instructions |
|---|---:|---:|---:|
| main | 249,960 | 15,800,436 | 0 |
| sdk | 45,907 | 2,226,708 | 0 |
| subsdk0 | 1,547 | 135,644 | 0 |

All 58 former PACGA sites call the implemented authentication primitive. The
existing PACGA commit is retained: 2,050 QARMA5 differential cases, 512 lifted
register/flags cases, 1,000 concurrent calls and 12 tampered contexts pass.
PACGA is not replaced by a zero return or no-op.

All 551 generated translation units plus 114 runtime objects are linked into
`oot2026.exe` (665 objects, approximately 308.8 MiB). The 548 generated chunks
and three function tables remain local game-derived material. The text scan still
contains 394,261 / 63,478 / 2,224 trap sites in main/sdk/subsdk0; padding and data
are included and universal reachability/correctness has not been established.

## Windows host and data

- The integrated host loads and relocates all three modules, initializes guest
  threads/TLS, domain IPC, filesystem mounts, audio-device and offline network
  service paths, NVN2 command recording and Vulkan presentation.
- The saved RomFS packing report records per-file SHA-256 verification of 186,587
  files into a 26,237,712,396-byte image. The runtime filesystem probe independently
  compared 64 sampled files, including 56 above 4 GiB, plus the largest file's
  ends. This is not proof that every gameplay path has sufficient content.
- The package metadata says version 1.1.1 and title ID `0400486024DEC000`.
  Metadata identity is not an independent authenticity assessment.
- AV1 decoding now uses pinned dav1d 1.5.4 with the supplied SDK's exact exported
  signatures, output properties, direct event-pointer ABI and sync-point wait.
  The real guest movie demuxer supplied AV1 packets; 1920x1080 pictures were decoded
  and read as NV12; the rendering continuation now verifies GPU conversion and
  visible video presentation. Only 8-bit I420 output and one shown picture
  per input sample are implemented; other cases fail explicitly.
- NVN2 property `0x67` returns the reference value 256. Unknown properties retain
  explicit errors and now include the guest caller in the diagnostic.

## Failures reproduced and fixed during boot

The asynchronous SDK crashes led to a new cross-thread fiber regression. The
pre-fix host crashed with access violation `0xc0000005`. The host retained the old
thread pointer after a Windows fiber migrated. Resumption and host-call depth now
use the resumed Cpu's thread. The regression passes 64 migrations between two
threads, preserving registers, stack, TLS and differing nested host-call depths;
the existing 10,000-switch test also passes. Three subsequent 600-frame runs
reached their checkpoint without the earlier SDK access violation. This is a
bounded regression result, not a long-duration stability guarantee.

The validated run then hung after reporting its final frame. The existing
immediate process-exit path used `ExitProcess` while guest/GPU threads were still
active. Windows documents a DLL-detach deadlock in this situation. The path now
uses self-termination after the callers' explicit save/cache/log flushes, matching
its existing immediate-exit contract. The repeated validation run exited in
17.437 seconds instead of timing out after 45 seconds. This does not validate
game save semantics. Reference: [Microsoft ExitProcess remarks](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-exitprocess).

Shader rejection statistics previously missed the NVN2 lowering stage and read an
unused counter. They now include both lowering and downstream translation errors;
a malformed-stage regression checks the public boot statistics. Reaching a frame
target is labeled a checkpoint, and graphics errors are explicitly reported.
The bounded runner returns diagnostic exit code 2 for a checkpoint with errors,
even when the game process exits with code 0.

## Current verification

- 13 linked-runtime probes pass: selftest, loader, kernel (including migration),
  IPC lifetime/domains, system core, audio device, NIFM, BSD, filesystem, graphics
  ABI, NVN and codec.
- 17 parser/normalizer/runtime-input unit tests pass.
- PACGA differential and concurrency checks pass as above. Earlier integer/SIMD
  results remain preserved; they were not represented as newly rerun here.
- New regressions: 301 shader/range checks, 2,822 existing native EXIT-capture
  checks, 49 GPU memory checks and 63 descriptor/storage-view checks pass.
  All 46 runtime-cache SPIR-V modules pass validation for Vulkan 1.3.
- Real rendering runs reach opening video at 600 guest presentation requests,
  title/main menu in longer runs, and open/close Options during a 3,000-request
  script. Successful Vulkan presentations are now counted separately from guest
  requests. GPU validation reports zero errors; processes exit normally.
- Captures honor the presented 1706x960 crop of the larger backing texture.
  The original black captures and logs are retained for before/after comparison.
- No controller is connected. Controller behavior, game audio, saves, scene
  transitions and sustained frame timing are not verified.

## Remaining blockers

1. **Shader support:** 203 rejected stages: 79 native opcodes, 56 stage-buffer
   reads, 41 gathers, 20 funnel-shift immediate modes, six scratch-register
   conflicts and one texel-fetch/descriptor mode. They remain explicit errors;
   title/options rendering does not establish correctness of later scenes.
2. **Unexercised rendering:** 3D gameplay and broader texture readback/shader
   semantics remain unverified. The two reported oversized pool errors are fixed
   through bounded host imports with GPU regression coverage.
3. **Complete runtime compatibility:** the exercised title/menu path is integrated;
   unsupported later services, traps, codec formats and gameplay paths remain.
   No playability or general completion claim is made.

The local source checkpoint, [incremental commands](FULL_RUNTIME.md) and compact
machine-readable report preserve the next starting point. Raw game files, generated
C, objects, screenshots and the linked game EXE stay outside committed source.
Nothing was published or pushed remotely.
