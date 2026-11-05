# Continuing the linked Windows runtime

Reuse an existing verified ExeFS, RomFS image, translation directory and native
output directory. Do not rerun extraction/lifting merely to change a host source
file. `tools/build_full_runtime.py` validates the module manifests, invokes the
incremental build and checks existing object hashes. Generated C is never edited.

From this repository, with paths to the existing local artifacts:

```powershell
python tools/build_full_runtime.py --exefs <normalized> --romfs <romfs> --generated <generated> --out <native> --profile <profile> --deps <runtime-deps> --llvm <llvm-mingw> --ninja <ninja.exe> --jobs 6
python tools/test_full_runtime.py <native>/oot2026.exe --logs <logs>/host-probes
python tools/run_full_runtime.py <native>/oot2026.exe --logs <logs>/boot --frames 600 --timeout 60 --preemption 2 --screenshot
```

The angle-bracket paths are placeholders. For this machine the existing artifacts
are under `C:/Users/Pascal/Documents/Codex/2026-11-05/du-h/work/`: game inputs and
outputs in `game/oot111/`, dependencies in `runtime-deps/`, the compiler in
`toolchain/llvm-mingw-20261104-ucrt-x86_64/`, and Python/Ninja in `venv/Scripts/`.
The preserved `work/build_native.py` also rebuilds that same output incrementally.

For a new dependency directory only, `tools/runtime_deps.py --out <runtime-deps>
--sdl <directory-containing-SDL3-3.4.18>` verifies pinned downloads including
dav1d. Reuse the existing populated directory here. The build copies required DLLs
beside the executable. `--translator` on the build wrapper can copy an existing
`totk_xlate.exe` and its identity file when setting up a different output directory.

To enable actual Vulkan validation before the bounded run:

```powershell
$env:TOTK_VK_VALIDATION='1'
$env:VK_LAYER_PATH=(Resolve-Path <validation>/ucrt64/bin).Path
$env:PATH=$env:VK_LAYER_PATH+';'+$env:PATH
```

Read the log to confirm the validation layer loaded. A zero validation-error
counter without the layer enabled is not evidence of valid Vulkan usage.

Each run gets a unique log/JSON/capture name. The runner records the executable
hash, frame counters, actual process status and a separate diagnostic exit code:
0 for a reached checkpoint without reported errors, 1 for a failed process,
2 for missing checkpoint or reported graphics/runtime errors, 124 for timeout.
Even exit 0 does not establish rendering correctness or playability.

Only inspect the generated `-preview.png` in chat tools: it is at most 960 pixels
on its longest edge and 512 KiB, with checked PNG integrity. The runtime's original
uncompressed capture can be about 14.7 MB; preserve it on disk without attaching
it to the chat. A new run never mistakes a previous capture for a new result.

Earlier boot/failure logs are retained under `work/logs/continuation/`, including
the crashing/passing fiber regression, pre-fix shutdown timeout and final validated
600-frame result. The public source summary is in
`logs/runtime-integration-2026-11-05.json`. The visible title/menu continuation is
recorded separately in `logs/rendering-integration-2026-11-05.json` and
[RENDERING_BRINGUP.md](RENDERING_BRINGUP.md), including the before/after shader
census and actual Vulkan device. No files need to be regenerated to continue.

The frame target counts guest present requests. The log now separately reports
accepted `vkQueuePresentKHR` calls. A checkpoint drains replay/GPU work; screenshots
use the guest window's crop, rather than the unused part of a larger texture.
The runner still reports graphics errors even when reviewed images show a menu.

Additional targeted checks from the repository root:

```powershell
$env:TOTK_GPU='vulkan'
python tools/test_full_runtime.py <native>/oot2026.exe --logs <logs>/gpu-probes --modes probe-vkmem probe-vkpool
clang++ -std=c++20 -O2 -Wall -Wextra -Werror -static-libstdc++ -static-libgcc -I third_party/dkb/runtime/third_party/eglantine third_party/dkb/tests/render_regressions.cpp -o <work>/render-regressions.exe
& <work>/render-regressions.exe
python third_party/dkb/tests/native_exit_capture_test.py --cxx <llvm>/bin/clang++.exe --out <logs>/native-exit --opt 2
```

Keep validation enabled for both GPU probes. The shader/range tests contain only
authored instructions; the GPU storage-view test writes a tiny authored texture.
These are regressions, not evidence of game output. For the real menu test, create
a private text input script containing `900 PLUS 8`, `1400 DOWN 8`, `1600 A 8`,
`2000 B 8` on separate lines, set `TOTK_INPUT_SCRIPT` to it, set
`TOTK_SHOTS=800-2600:200` and `TOTK_SHOTS_DIR` to a private capture directory,
then run the bounded runner with `--frames 3000 --timeout 100 --screenshot`.
Remove those input/capture settings for an interactive run.

After translator changes use a new `TOTK_SHADER_CACHE` directory, retaining the
old one for comparison; validate its `.spv` files with
`spirv-val --target-env vulkan1.3`. Do not commit those files or native shader
captures. Cache keys already incorporate lowered code and translator/options
identity; a new directory additionally removes ambiguity during diagnosis.
