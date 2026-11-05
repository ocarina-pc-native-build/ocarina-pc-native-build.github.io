# Engineering status — 2026-11-05, native boot checkpoint

**The existing project now links and executes the supplied Zelda code on Windows.
It is not yet a playable port.** The latest validated run reached 600 presented
frames and exited normally, but its captured preview is black. It reported 464
shader failures and two Vulkan validation errors. No title screen, gameplay,
working game saves, audible game audio or performance target is verified.

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

All 551 generated translation units plus 113 runtime objects are linked into
`oot2026.exe` (664 objects, approximately 308.4 MiB). The 548 generated chunks
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
  and read as NV12 through approximately 6.4 seconds of video. GPU presentation of
  those pictures remains unverified. Only 8-bit I420 output and one shown picture
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
- Final Vulkan validation run: 600 frames, 95 guest threads, 756,596 SVCs,
  3,273,484 host calls; process exit 0. A 960x540 preview is 3,570 bytes and has
  zero nonblack pixels. The original 2560x1440 capture remains local.
- No controller is connected. Controller behavior, game audio, saves, scene
  transitions and sustained frame timing are not verified.

## Remaining blockers

1. **Shader support:** 464 rejected stages: 255 texture-dimension query modes,
   79 native opcodes, 56 stage-buffer read modes, 41 texture-gather modes,
   26 byte-to-float conversions, six scratch-register conflicts and one texel
   fetch/descriptor mode. These need semantically correct lowering and regression
   fixtures, not skipped instructions. The captured output remains black.
2. **GPU memory limits:** a 2,550,136,832-byte guest pool becomes one Vulkan
   buffer/allocation, exceeding this GPU's 2,147,483,648-byte limits. Validation
   reports `VUID-VkBufferCreateInfo-size-06409` and an oversized allocation.
   Pool storage needs splitting with correct address/binding/transfer translation.
   Ignoring validation or falsifying reported limits is not a fix.
3. **Complete runtime compatibility:** the exercised boot path is integrated;
   unsupported later services, traps, codec formats and gameplay paths remain.
   No playability or general completion claim is made.

The local source checkpoint, [incremental commands](FULL_RUNTIME.md) and compact
machine-readable report preserve the next starting point. Raw game files, generated
C, objects, screenshots and the linked game EXE stay outside committed source.
Nothing was published or pushed remotely.
