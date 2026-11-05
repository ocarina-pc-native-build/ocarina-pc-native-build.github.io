# Third-party provenance and distribution

The project aggregate is GPL-3.0-or-later. Original notices and permissive licenses
remain in their respective files. The independent preprocessing script
`tools/normalize_nso.py` is MIT-licensed. No Nintendo code, assets, keys or generated
game functions are included in the distributable archive.

| Component | Revision / version | License and location | Use |
|---|---|---|---|
| dav1d | 1.5.4-1 MSYS2 UCRT64; package SHA-256 `ccf26c6f29fd36f5692d57fd5e0fe3becec492e0b875fd5e04f47a9582eb8b37` | BSD-2-Clause; `licenses/dav1d-COPYING.txt`, `licenses/dav1d-PATENTS.txt` | AV1 video decoding in the native runtime; unmodified DLL from [MSYS2](https://packages.msys2.org/packages/mingw-w64-ucrt-x86_64-dav1d). |
| QEMU QARMA5 | `ba93f3ae5cbe9bace0a8163843f0d678f08a3e6e` | LGPL-2.1-or-later; `licenses/QEMU-LGPL-2.1.txt` | Arithmetic helpers from `target/arm/tcg/pauth_helper.c` adapted in `third_party/dkb/runtime/pacga.c`; process key supplied by Windows BCrypt. |
| DKB Recomp | `8c76e84af43d70d8d98b2398272d38d368039149` | GPL-3.0-or-later aggregate, MIT inherited portions; `third_party/dkb/LICENSE`, `LICENSE-MIT`, `THIRD_PARTY_NOTICES.md` | Full tracked snapshot. Its Horizon, NVN2, Vulkan, audio, input and shader runtime is linked into the private native game build, with local compatibility fixes and tests. The smaller diagnostic remains separate. |
| nxnative NSO reader | `84dea69835414b18a4351cd45054bb611e0e3185` | MIT; `third_party/nxnative/LICENSE` | `dm/tools/nso.py` copied unchanged as `nso_reader.py` for a separate normalization tool. |
| nxnative runtime semantics | `84dea69835414b18a4351cd45054bb611e0e3185` | MIT; `third_party/nxnative/LICENSE` | `dm/gfx/nvn/hle_nvn.c`, `dm/gfx/nvn/nvn_obj.h`: independent row/image copy pitch recording adapted to the Vulkan backend; `dm/host/hle_thread.c`: 64-bit address wait comparison; `dm/host/hle_net.c` and `dm/host/hle_hid.c`: offline transport and host gyro configuration reference. Copyright (c) 2026 seedds and nxnative contributors; original MIT terms retained. |
| Eglantine runtime reference | `23f383cab532bf3834ea55f3488b48841f3c727b` | GPL-3.0-or-later; read-only reference, no source copied in these host additions | Protocol checks for thread-local current handle, audio notifications/device manager, NIFM, BSD and SSL library initialization. Original C implementations here use the existing DKB kernel/IPC framework. |
| libnx CMIF/BSD reference | `switchbrew/libnx`, `nx/include/switch/sf/cmif.h`, `nx/source/services/bsd.c`, consulted 2026-11-05 | ISC; wire format reference, no source copied | Domain message framing, object transfer/copy controls and BSD initialization/socket response layouts. |
| SDL3 | 3.4.18 | zlib; `licenses/SDL3-LICENSE.txt` | Controller enumeration; distributed SDL3.dll from the pinned development archive. |
| Vulkan Headers | SDK 1.4.363.0 | Apache-2.0 / MIT; upstream package notices retained in `licenses/` | Compiling the Vulkan diagnostic; Vulkan loader comes from the installed GPU driver. |
| LLVM-MinGW | 20261104, Clang 23.1.5 | LLVM Apache-2.0 with exceptions and component licenses | Build tool, downloaded separately; not bundled. |
| zbic | 1.0.1.post1 | PyPI reports GPLv2; external optional package, not vendored or linked | Used only by the separate MIT normalization utility. No decoder binaries are redistributed here. |
| Unicorn | 2.1.4 | GPL-2.0; external Python dependency | Development-only differential reference. Not linked or launched by oot-runtime.exe. |

The upstream DKB notices enumerate LASRecomp, MacNativeGames, Ryujinx, Dear ImGui,
Eglantine shader lowering and other inherited components with revisions and terms.
Those notices and files are preserved. Eglantine shader lowering and the native
Ryujinx translator helper are built and integrated. No emulator is launched.

Source URLs: [DKB](https://github.com/Lucas-blip-png/dkb-pc-recomp),
[TotK](https://github.com/valentderah/totk-pc-recomp),
[nxnative](https://github.com/seedds/nxnative),
[SDL](https://github.com/libsdl-org/SDL),
[Vulkan Headers](https://github.com/KhronosGroup/Vulkan-Headers),
[zbic](https://github.com/kinnay/zbic).
