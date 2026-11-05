# OoT2026-PC-Recomp

An experimental Windows x64 recompilation workspace. **This is not a playable
Ocarina of Time port.** It contains an actually compiled independent host, a native
diagnostic launcher, a Vulkan 1.3 transfer/readback test, SDL3 controller discovery,
validated NSO preprocessing and an adapted ARM64-to-C lifter.

The supplied NUP identifies itself as Ocarina of Time 1.1.1. That metadata is not
an independent authenticity or compatibility certificate. Its full game runtime,
Horizon integration and NVN2 rendering are not connected to the diagnostic host.

## Run the independent runtime

Extract the archive and keep `bin/oot-runtime.exe` beside `bin/SDL3.dll`.
Double-click the executable for the diagnostic launcher, or run:

```powershell
.\bin\oot-runtime.exe --self-test
.\bin\oot-runtime.exe --probe-vulkan
.\bin\oot-runtime.exe --probe-vulkan --validate
.\bin\oot-runtime.exe --probe-input
```

`--validate` requires the Khronos validation layer supplied by the Vulkan SDK and
fails explicitly when absent. The GPU diagnostic selects a Vulkan 1.3 device,
preferring a discrete AMD GPU, submits a real buffer fill, synchronizes and checks
all 4096 returned bytes. It is not a rendered game frame. The launcher folder
chooser currently displays a directory; it does not start or build a game.

## Rebuild without game files

Python 3.11.9 or compatible newer Python 3.11, Windows 10/11 x64 and network access
for the first dependency download are needed. No global installation is performed.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tools/bootstrap.py
.\.venv\Scripts\python.exe tools/build.py --config Debug
.\.venv\Scripts\python.exe tools/build.py --config Release
```

Artifacts and command/exit-code logs are under `build/debug` and `build/release`.
The scripts use CMake, Ninja and pinned LLVM-MinGW, SDL3 and Vulkan headers.
Debug/Release CMake presets are also included for an already configured PATH.
The complete Vulkan SDK is optional for compilation. Validation layers can come
from that SDK or the separate local setup below. CI configuration is included; remote CI has not
been executed for this newly created local repository. Dependency pins improve
repeatability; byte-for-byte reproducible executable output has not been proven.

The tests include malformed NSO checks, host memory/TLS/thread checks and native
generated code compared with Unicorn. The optional ZBIC roundtrip test runs after
installing `requirements-zbic.txt`; otherwise it is visibly skipped.

Optional validation without installing the full SDK:

```powershell
.\.venv\Scripts\python.exe tools/setup_validation.py
$env:VK_LAYER_PATH=(Resolve-Path toolchain/validation/ucrt64/bin).Path
$env:PATH=$env:VK_LAYER_PATH+';'+$env:PATH
.\build\release\oot-runtime.exe --probe-vulkan --validate
```

## Local game integration

Only use your own legally supplied, decrypted files. Outputs below are local
game-derived material and are excluded from the distributable archive.

```powershell
.\.venv\Scripts\python.exe third_party/dkb/tools/extract_nup.py 'D:\YourGame.nup' --list
# Select the actual package index from the listing; do not assume every NUP has a base.
.\.venv\Scripts\python.exe third_party/dkb/tools/extract_nup.py 'D:\YourGame.nup' --package 0 --only exefs --out local/dump
.\.venv\Scripts\python.exe -m pip install -r requirements-zbic.txt
.\.venv\Scripts\python.exe tools/normalize_nso.py local/dump/exefs --out local/normalized
.\.venv\Scripts\python.exe tools/inspect_dump.py local/normalized --analyze --output local/analysis.json
.\.venv\Scripts\python.exe tools/lift_game.py local/normalized --out generated/oot111 --jobs 4
```

Normalization preserves the original, validates decoded segment hashes and verifies
that the normalized image is identical. Both original and normalized SHA-256 values
are recorded. Build IDs are reported but no supported-version whitelist is claimed.
`--analyze` uses the upstream MOD0/symbol/relocation parser for trusted local dumps;
it is not a security-hardened parser for hostile files.

The strict lifting wrapper returns exit code 3 if unsupported instructions remain.
The underlying upstream generator emits trap calls for such instructions and can
still exit zero; **that alone must never be interpreted as successful game support**.
`rtld` is inspected but not lifted, because the intended host performs module linking.
No Donkey Kong or TotK fixed-address patch set is applied.

For compiler diagnosis only, including incomplete translations:

```powershell
.\.venv\Scripts\python.exe tools/compile_modules.py --generated generated/oot111 --llvm toolchain/llvm/llvm-mingw-20261104-ucrt-x86_64 --out local/objects --jobs 4
```

This produces native COFF objects, not a linked game. Do not distribute them.
See [the engineering status](docs/STATUS.md), [repository audit](docs/UPSTREAM_AUDIT.md)
and [license notices](THIRD_PARTY_NOTICES.md) for the verified scope and remaining work.
