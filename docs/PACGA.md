# PACGA implementation and compatibility

All 58 PACGA instructions in the supplied 1.1.1 SDK were decoded and their
containing functions and consumers inspected. There are four function bodies:

| Function family | Instructions | Result use |
|---|---:|---|
| setjmp (three symbol aliases) | 14 | Sign saved general registers, stack and floating-point state; pack and store the signatures in the jump context. |
| longjmp (two aliases) | 14 | Recompute the saved-context signatures; compare and trap on mismatch before restoring execution. |
| Fiber initialization | 2 | Sign the initial entry and context using a stack-derived modifier. |
| Fiber dispatch | 28 | Sign the outgoing context and authenticate the incoming context, including register chains. |

No observed PACGA result is a dispensable hint. Replacing these instructions
with NOP would leave stale registers and could corrupt authentication chains.
The detailed address inventory and disassembly remain with the private game
build, outside the source repository.

The lifter emits `rt_pacga(data, modifier)`. The helper implements QARMA5 and
returns the high 32 cipher bits with the low 32 bits zero, as PACGA requires.
The first source uses XZR for register 31; the modifier uses SP for register 31;
the destination discards writes to XZR. NZCV and unrelated registers are
preserved, including when source and destination registers alias.

A 128-bit APGA key is generated once per native process with BCryptGenRandom.
All native threads and guest fibers share it. It is never logged or persisted.
The observed code both generates and verifies its contexts within this process,
so it does not need the console's original process key. Importing already signed
console contexts or resuming such contexts across process restarts is not
supported by this compatibility argument. Other pointer-authentication
instructions retain the donor runtime's handling; this change specifically
implements PACGA and does not claim a complete ARM pointer-authentication model.

The cipher is adapted from QEMU at the revision in THIRD_PARTY_NOTICES.md.
`tools/test_pacga.py` compares 2,050 data/modifier/key tuples against Unicorn's
ARM64 PACGA, tests 512 compiled lifter cases for register aliases/SP/XZR/NZCV,
checks 1,000 cross-thread calls, and verifies that twelve deliberately corrupted
register-context fixtures fail authentication. Unicorn is a development-only
reference; it is not part of the game runtime.
