# Third-party provenance and distribution

The project aggregate is GPL-3.0-or-later. Original notices and permissive licenses
remain in their respective files. The independent preprocessing script
`tools/normalize_nso.py` is MIT-licensed. No Nintendo code, assets, keys or generated
game functions are included in the distributable archive.

| Component | Revision / version | License and location | Use |
|---|---|---|---|
| DKB Recomp | `8c76e84af43d70d8d98b2398272d38d368039149` | GPL-3.0-or-later aggregate, MIT inherited portions; `third_party/dkb/LICENSE`, `LICENSE-MIT`, `THIRD_PARTY_NOTICES.md` | Full tracked source snapshot, modified only in `recomp/simd_c.py`; CPU lifter and headers actively used. Horizon/NVN2 sources retained for integration, not linked into the diagnostic executable. |
| nxnative NSO reader | `84dea69835414b18a4351cd45054bb611e0e3185` | MIT; `third_party/nxnative/LICENSE` | `dm/tools/nso.py` copied unchanged as `nso_reader.py` for a separate normalization tool. |
| SDL3 | 3.4.18 | zlib; `licenses/SDL3-LICENSE.txt` | Controller enumeration; distributed SDL3.dll from the pinned development archive. |
| Vulkan Headers | SDK 1.4.363.0 | Apache-2.0 / MIT; upstream package notices retained in `licenses/` | Compiling the Vulkan diagnostic; Vulkan loader comes from the installed GPU driver. |
| LLVM-MinGW | 20261104, Clang 23.1.5 | LLVM Apache-2.0 with exceptions and component licenses | Build tool, downloaded separately; not bundled. |
| zbic | 1.0.1.post1 | PyPI reports GPLv2; external optional package, not vendored or linked | Used only by the separate MIT normalization utility. No decoder binaries are redistributed here. |
| Unicorn | 2.1.4 | GPL-2.0; external Python dependency | Development-only differential reference. Not linked or launched by oot-runtime.exe. |

The upstream DKB notices enumerate LASRecomp, MacNativeGames, Ryujinx, Dear ImGui,
Eglantine shader lowering and other inherited components with revisions and terms.
Those notices and files are preserved. Including source from Eglantine for future
shader translation does not integrate or launch an emulator.

Source URLs: [DKB](https://github.com/Lucas-blip-png/dkb-pc-recomp),
[TotK](https://github.com/valentderah/totk-pc-recomp),
[nxnative](https://github.com/seedds/nxnative),
[SDL](https://github.com/libsdl-org/SDL),
[Vulkan Headers](https://github.com/KhronosGroup/Vulkan-Headers),
[zbic](https://github.com/kinnay/zbic).
