# Lichii Ampere lowering (GPL-3.0-or-later)

`lower_to_maxwell.h`, `geometry_exit.h`, `register_pressure.h`, `instruction.h` and `program_capture.h` are copied from
[chuppatricky/Lichii](https://github.com/chuppatricky/Lichii) tag `chuppatricky-amd-testbuild-v13` (commit 3f17618,
`src/shader_recompiler/frontend/ampere/`), Copyright 2026 Eden Emulator Project, GPL-3.0-or-later. Only their
`#include "shader_recompiler/frontend/ampere/..."` lines were changed to file-relative includes.

nvn2_lower.cpp includes them with the namespace renamed to `Shader::AmpereLichii` and uses them as a fallback when the
Eglantine lowering (third_party/eglantine) rejects a non-mesh program. A Lichii result is accepted only if it has none
of Lichii's banked native register copies (a MOV form only Lichii's own Maxwell frontend decodes).
