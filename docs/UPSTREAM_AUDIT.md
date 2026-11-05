# Upstream audit — 2026-11-05

All three requested public repositories were cloned locally with their tracked
trees and Git history (partial clones fetch historical blobs on demand). The
inspected revisions are pinned in `upstream-lock.json`. This is a targeted
architecture/build/license audit, not a line-by-line audit of every historical
commit or every issue. “Latest observed” is distinguished from “tested working.”

| Project | Branches observed | Pinned HEAD | Finding |
|---|---|---|---|
| DKB | `bananza` | `8c76e84af43d70d8d98b2398272d38d368039149` | Best Windows/Switch-2 starting point. Its content-guard workflow passed at this SHA, which is not a gameplay/build proof. |
| TotK | `main`, `dev`, same HEAD | `101132a6c8d9654c88838c57b934b4b79636ea90` | Windows/Linux ARM64-to-C host, Vulkan, SDL3. Latest commit repairs Linux release build after a changed build_sources signature. Switch-1/game-specific assumptions remain. |
| nxnative | `main` | `84dea69835414b18a4351cd45054bb611e0e3185` | Original ARM64 code on Apple hardware with rewriting and Metal, not an x64 recompiler. Useful generic NSO reader, profiles and service semantics. Latest lint-python run failed; tests/lint-c were pending when queried. |

## Reusable infrastructure and boundaries

DKB's `recomp/lifter.py` and `simd_c.py` translate ARM64 to C; `module.py` and
`gen.py` discover functions from unwind/symbol/relocation information and branch
targets. `layout.py` assigns module bases below the IPC address limit. This
project actively reuses these components and adds narrowly tested SIMD lowering.
The upstream NSO reader assumes LZ4; an independent nxnative preprocessing step
was required for the supplied module's ZBIC data. Normalization leaves virtual
addresses unchanged and preserves the decoded memory image.

`runtime/cpu.h`, `simd.h`, and `simd_fp.h` supply CPU state and generated-code
helpers. The whole upstream host is much larger than these headers: `kernel.c`,
`memory.c`, `svc.c`, `ipc.c`, `loader.c` and `hostfn.c` cover memory, threads,
dispatch and selected Horizon/SDK services. `romfs.c`/`fs_host.c`, `audren.c`,
`audio_mixer.c`, `ov_input.c`, `ov_system.c`, `ov_movie.c` and `ov_codec.c` cover
filesystem, audio, input, system and video functionality. Their presence in the
source snapshot is **not** evidence that those functions work for this game.

DKB's `runtime/nvn_api_nvn2.c` adapts NVN2 calls; its logging macros explicitly
accept some calls without recording them. These cannot be silently adopted as
successful implementations. `runtime/nvn2_lower.cpp` and the GPL shader-lowering
sources convert Ampere to Maxwell-shaped shader data. `tools/xlate/` uses a
.NET 10 / Ryujinx shader translator for Maxwell-to-SPIR-V. The GPU backend spans
`vk_device.c`, `vk_memory.c`, `vk_sync.c`, `vk_pipeline.c`, `vk_texture.c`,
`vk_exec*.c`, `vk_astc.c` and associated files. The complete backend and translator
have not been linked into the new diagnostic host or tested on OoT shaders.

The upstream build is Python-generated Ninja, not CMake. It requires Clang GNU C
extensions, SDL3, Vulkan, Vulkan Memory Allocator, Opus, libvpx and zstd; the shader
translator adds .NET and Ryujinx. This project supplies its own CMake Debug/Release
entry point for the independent components. The requested complete game host is
still an integration task.

Game-specific parts that must not be carried over blindly include
`recomp/patches-dkb100.txt`, TotK patch files, expected hash tables, `frame_rate.c`,
RomFS overlays, hard-coded shader identities and `vk_exec_draw.c`'s light-quad
workarounds. No such patch set is passed to the OoT generation command. NVIDIA
skip behavior is not enabled in the independent AMD test.

## Issue and evidence review

- [DKB roadmap #10](https://github.com/Lucas-blip-png/dkb-pc-recomp/issues/10)
  reports title/tutorial rendering and remaining terrain, texture and stability
  issues. Those are upstream author reports, not locally reproduced gameplay.
- [DKB #3](https://github.com/Lucas-blip-png/dkb-pc-recomp/issues/3) requests
  other-GPU testing; [#6](https://github.com/Lucas-blip-png/dkb-pc-recomp/issues/6)
  tracks unrecorded NVN2 commands; [#45](https://github.com/Lucas-blip-png/dkb-pc-recomp/issues/45)
  concerns terrain/indirect geometry. Open issues also include sound and shader
  lowering. Consequently no “latest fully working” DKB release was established.
- Recent TotK issues include graphics effects disappearing in the scope (#747),
  installation (#745), Linux aspect ratio (#744) and input changes (#751–753).
  They do not establish compatibility with OoT or Switch 2.
- [nxnative #1265](https://github.com/seedds/nxnative/issues/1265) names exactly
  title `0400486024DEC000`, version 1.1.1, and reports missing game-profile support
  for an update-only NUP. No successful OoT gameplay is established by that issue.
  Recent nxnative work also shows ongoing Switch-2 shader/controller integration.

## License conclusion

DKB is GPL-3.0-or-later as an aggregate because of its Ampere lowering; inherited
MIT files retain their original terms. TotK and nxnative use MIT for their own
code. Full upstream notices are preserved. The optional GPLv2 ZBIC package is
installed externally for a separate preprocessing utility, not bundled or linked
into the runtime. No Nintendo keys, extracted modules, RomFS data or generated
game functions belong in the project archive.
