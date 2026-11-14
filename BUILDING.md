# Building Ocarina Reborn v1.0.8

This checkout contains the actual launcher and patched engine source used by the v1.0.8 installer. It contains no game executable, extracted game filesystem, saves or private signing material. A game build still requires your own supported game file.

## Layout

- `engine/`: the shipped engine source, based on Hookshot v2.2.0-rc.1, with Ocarina Reborn changes already applied. Do not apply the patch scripts to this directory again.
- `tools/alpha/launcher/`: the Python launcher, native window procedure and interface assets.
- `tools/alpha/exe/`: the native Windows launcher entry point and version resource.
- `tools/alpha/hud/`: custom gameplay hooks, renderer additions and their injection scripts.
- `tools/alpha/tests/`: Ocarina Reborn regression tests.
- `tools/alpha/engine_v21.py`, `hud_v21.py`, `stage_alpha.py`: original patch-generation/packaging recipes. The historical filename `engine_v21.py` also covers the current v2.2 port.
- `tools/alpha/licensing-server/server.py`: the earlier activation-server implementation, without production keys, licenses or its database. The released launcher uses the public-release path.
- `data/`: public configuration only; voice recordings and tag files are not distributed.
- `SOURCE-MANIFEST.json`: hashes tying the engine source to the released installer.

## Build a Windows installer

The source archive deliberately excludes compiler binaries, Python distributions, dependency SDK binaries and caches. The reproducible entry point below takes those build dependencies from an existing Ocarina Reborn distribution; it takes the launcher and host/GPU engine code from this checkout.

1. Install the [Ocarina Reborn v1.0.8 distribution](https://github.com/misterrageguy-cyber/OoT2026-PC-Recomp/releases/tag/v1.0.8) to provide its pinned Python, llvm-mingw, Vulkan/FFmpeg SDKs and SDL runtime. You do not need to supply a game file or build the game to use its tools.
2. Install [Inno Setup 6](https://jrsoftware.org/isinfo.php) if you want a setup executable.
3. Open PowerShell in this source checkout and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_from_source.ps1
```

Use `-Runtime 'D:\Ocarina Reborn'` for a nonstandard distribution location and `-Iscc 'D:\Inno Setup 6\ISCC.exe'` for a different Inno compiler path. `-StageOnly` builds the launcher and assembles a runnable distribution without creating an installer. Its output is `build/source-stage`; use a fresh `-Out` directory for another build. The script refuses to delete or overwrite an existing staging directory.

The installer is written to `build/dist/Ocarina-Reborn-Alpha-Setup.exe`. Building it does not launch or install it. The native launcher and `ocr_chrome.dll` are compiled from the published C sources. Building your game afterwards uses the published `engine/host`, `engine/gpu` and `engine/nx2` code against your own game file.

The copy of `tools/alpha/build_alpha.ps1` is the original developer packaging route. It expects an unpatched pinned engine checkout and a developer dependency layout; use the portable entry point above for this published snapshot.

## Dependencies without an installed distribution

See `engine/CONTRIBUTING.md` and `engine/docs/development.md` for the upstream dependency/build route. Python package versions are pinned in `engine/requirements.txt` and `engine/nx2/prompt_requirements.txt`. Windows uses llvm-mingw (the v1.0.8 distribution carries the 20261104 toolchain). The Vulkan and FFmpeg SDKs go in `engine/cpm`, SDL binaries in `engine/third_party/sdl2`, and optional WebGPU runtime files in `engine/wgpu-native`. The latter directory includes the upstream tag and patches used for that dependency.

The launcher environment additionally needs NumPy, lz4, zstandard and zbic. Offline tunic-color preparation uses Pillow, astc-encoder-py and texture2ddecoder from the bundled engine Python environment. The packaged `python/` and `engine/python/` environments contain these tools. FSR 4 is a separate AMD runtime dependency; its redistributable binaries and license are in the distribution's `amd-fsr4/` directory.

## Checks

With Python 3.11 and the packages above installed, and llvm-mingw's `bin` on PATH:

```powershell
python -m unittest discover -s tools/alpha/tests -v
```

For upstream engine checks, see `engine/tests/run_all.py`. A game file is not needed for these tests. Renderer-only compilation and full game-build commands are documented in `engine/docs/development.md`.

The snapshot keeps existing dependency license and attribution files. The engine is GPL-3.0; see `engine/LICENSE` and `engine/NOTICE-OCARINA-REBORN.txt`. Publishing the source does not grant additional rights to third-party media or trademarks.