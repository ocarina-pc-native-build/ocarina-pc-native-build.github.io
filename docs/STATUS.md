# Engineering status — 2026-11-05

**Development build, not a playable game port.** No title screen, gameplay,
game audio, game save or 60 FPS claim is made. The independent native runtime
does not execute the supplied game's code yet.

## Verified locally

- Clang 23.1.5, CMake 4.4.4 and Ninja 1.13.2 built Windows x64 Debug and Release
  diagnostic executables. SDL3 3.4.18 is used for controller enumeration.
- Host memory allocation/release, TLS isolation, native thread join, monotonic
  time and explicit unsupported-service errors pass the host selftest. These are
  host primitives, not a complete Horizon service implementation.
- Twelve parser/normalizer tests pass, including truncated/bad headers, segment
  bounds/overlap, hash mismatch, LZ4, ZBIC roundtrip and unchanged source files.
- 3,370 integer/flags and 5,200 SIMD differential cases pass against Unicorn.
  SIMD cases cover signed/unsigned vector dot products, half-float negation,
  aliases, upper-lane clearing, overflow and special half-float bit patterns.
- The upstream SIMD regression ran 2,000 encodings / 15,992 comparison cases with
  no failures. Two SDOT encodings are outside that harness's older Unicorn CPU
  model; they were reported as lifter-only. The dedicated new tests use Unicorn's
  MAX CPU and independently cover dot-product execution.
- AMD Radeon RX 7900 XTX: Vulkan API 1.4.359, successful device creation,
  command submission, 4096-byte fill/readback, transfer-to-host barrier and fence.
  The same diagnostic passes with Khronos validation layer 1.4.363 enabled,
  with no validation callback errors reported. This does not exercise NVN2,
  shader translation, swapchains, graphics pipelines or game rendering.
- SDL3 initializes and reports zero connected gamepads. Actual DS4/Xbox input
  could not be tested in this run.

## Supplied file and local recompilation

The supplied NUP is 25,020,741,061 bytes. Its verified table of contents reports
one standalone update package, display version 1.1.1, internal title ID
`0400486024DEC000`. The name supplied in the path contains a different title ID;
container metadata is used for identification. The package contains five ExeFS
files and 186,587 RomFS entries. RomFS contents have not been extracted or
validated; the update package's completeness for gameplay is not established.

The five extracted ExeFS files passed the NUP per-file SHA-256 checks. Four are
NSOs: `main`, `subsdk0`, `sdk`, `rtld`; the fifth is `main.npdm`. Segment checks and
ZBIC normalization passed, with the original files left untouched. Original and
normalized module hashes are in the local normalization report. This establishes
content identity and internal consistency, not title authenticity.

The generator, with no inherited game patches, emitted:

| Module | Function candidates emitted | C chunks | Unsupported instructions |
|---|---:|---:|---:|
| main | 249,960 | 488 | 0 after the UDOT patch |
| subsdk0 | 1,547 | 3 | 0 |
| sdk | 45,907 | 57 | 58 PACGA sites |

Total: 297,414 discovered functions, 548 chunks, approximately 1.225 GB of local
generated C. “Function” here means an upstream discovery candidate, not a proven
original source-level function. `rtld` is analyzed but omitted from lifting
because the planned host will link modules itself.

The generator additionally emits 394,261 / 2,224 / 63,536 trap sites respectively.
Text scans include padding and literal data, but reachability has not been proven;
these traps must not be dismissed as harmless. Indirect dispatch and function
boundaries still require runtime verification. PACGA remains an explicit
unsupported trap; there is no fabricated success value or no-op replacement.

All 551 translation units (548 chunks plus three function tables) compiled
successfully into native Windows x64 COFF objects using Clang. The result is
recorded in `logs/native-compilation-summary.json`. Object compilation does not
prove that modules link or that their guest behavior is correct.

## Milestones

| Requested milestone | Status |
|---|---|
| F0 — Windows runtime builds | Independent diagnostic host builds and passes tests; full Horizon host integration remains open. |
| F1 — ARM64 game translation | Partial: all three modules emitted, but 58 SDK PACGA sites remain unsupported and trap reachability is unverified. |
| F2 — game modules linked | Not achieved. All generated native objects compile; no linked game EXE. |
| F3–F4 — initialization/data mounting | Not reached. |
| F5–F8 — game graphics/menu/3D | Not reached. Standalone Vulkan buffer operations are not this milestone. |
| F9–F11 — gameplay/saves/audio/progression | Not reached or measured. |

## Open work, in dependency order

1. Implement and validate PACGA semantics and guest key/state handling; audit
   reachable traps, function boundaries, TLS, atomics and indirect dispatch.
2. Integrate the actual Horizon host from the pinned sources with a new game
   profile, load/link these exact modules and expose unsupported services clearly.
   Identify SDK services from imports; do not reuse TotK/DKB fixed addresses.
3. Validate the full RomFS/update contents and implement local data/save mounting.
4. Connect NVN2 recording, Ampere-to-Maxwell-to-SPIR-V and Vulkan submission;
   test actual game shaders and GPU memory layout on AMD with validation enabled.
5. Validate audio, controllers, movies, game saves and scene transitions, then
   measure frame timing at 2560×1440. None has a current performance guarantee.
6. Extend the launcher beyond folder selection/diagnostics: persisted resolution,
   window mode, GPU/controller choice, VSync, shader cache and real game FPS. The
   current GUI has been compiled but not visually inspected in this run.

No remote GitHub repository was published. The local repository and checked
archive provide source, notices, a diagnostic EXE, build scripts, tests and logs.
No game-derived C, objects, modules, keys or assets are in that archive.
