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
`logs/runtime-integration-2026-11-05.json`. See `STATUS.md` for the open graphics
blockers; no files need to be regenerated to resume that work.
