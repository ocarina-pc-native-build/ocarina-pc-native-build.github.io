# Guest setjmp continuation repair

The pre-fix executable at source e6125e6 reproducibly exits 70 after New Game's
opening sequence: `rt_dispatch: no function at guest pc 0x7001661690
(main+0x1661690): not a function start (lr 0x7001661690)`.
The unchanged executable was reproduced with SHA-256
`3b332be94b9d36aa07e4747430ef9cb86827994d74f4858ae893337fe6188710`.
The historical input script and configuration were reused. A copy of the current
test profile was used; a byte-for-byte snapshot of the historical run's initial
profile was not available. The user's existing saves were not modified.

## Cause and implementation

The reported PC is the intended continuation after a BL to the setjmp PLT, not
the instruction that performed the failing branch. The containing generated
function is `f_7001661670`; its BL at main+166168c calls the setjmp import at
main+3c44140. The SDK setjmp at sdk+aec40 saves LR, SP, callee-saved registers and
SIMD state. SDK longjmp at sdk+aed50 authenticates and restores that context and
branches to the saved LR. The dispatch table previously accepted function entries
only; this valid interior continuation had no entry.

`recomp/module.py` identifies setjmp definitions and standard AArch64 PLT imports
from symbol/relocation metadata. `recomp/gen.py` emits a host continuation wrapper
only around callers of those identified entries. Their guest registers and flags
remain in Cpu across reentry. The existing generated SDK code, including PACGA
authentication and longjmp's zero-to-one result normalization, is unchanged.

`runtime/nonlocal.c` matches a restored PC and SP against an active binding owned
by the same Cpu. It unwinds younger continuation frames and resumes the registered
host frame. Other threads and fibers retain their bindings; host callback depth
is restored, and finalization/reinitialization discards stale contexts. Unknown
destinations still produce the original fatal error. This implementation covers
recognized direct calls and PLT calls to setjmp/_setjmp. Dynamically supplied
function pointers to setjmp are not automatically recognized.

CRT setjmp/longjmp is deliberate: it uses the existing Windows runtime convention
also used for thread exit. No generated C was edited by hand. Six of 548 generated
translation units changed; no architecture or PAC implementation was replaced.

## Evidence

The first real corrected run reaches the same nonlocal return around frame 23254:
target PC and LR `0x7001661690`, FP `0x11c50a630`, SP `0x11c50a620`, X0/X1 both 1.
The private log retains Cpu/thread identities, registers, 16 stack words, the
guest FP chain and Windows host stack. It then records save commits, visible
heart/action HUD and continued rendering, and exits 0 at 27000 guest presentation
requests. Its last accepted vkQueuePresentKHR reporting boundary is 25200;
these counters are different events. No claim of 27000 actual presentations is
made. The picture remains severely overexposed, and this run has no player input
after the transition, so it does not prove controllability.

The first successful run uses executable SHA-256
`34261af20ab89a554518d25b93f74b8d05a3a563adcddaebc60ada2ee4255f0c`.
The second fresh process repeats the identical input script from another copy of
the initial profile, executes the same registered continuation, creates the
gameplay save and also exits 0 at 27000. Its restored FP/SP are
`0x110340630`/`0x110340620`, with X0/X1 both 1. Its executable hash is
`3e67a31bc9ab0dd716441f522287e8ba4e8a42c086cfe8aabffaf6e6da04b0b7`
(diagnostic output capped after sixteen resumptions). Its last actual-present
reporting boundary is 23400. All 1778 collected game SPIR-V modules pass
`spirv-val --target-env vulkan1.3` after these runs.
Validation was off in this long reproduction. It records 380 distinct native
lowering failures and four later translator failures; 65 failed native shaders
were selected. This longer path loads additional programs and is not comparable
to the earlier 111-error menu census.

Authored regression `tests/diff/nonlocal_test.py` compiles synthetic AArch64
functions through the actual generator and compares 112 nested nonlocal returns
with Unicorn, including zero, negative and boundary return values and preserved
callee/SIMD state. Additional checks cover PLT recognition, wrong Cpu/PC/SP,
jmp_buf reuse, nested-frame cleanup and host callback depth. Existing whole-function
tests pass 2572 executable cases on 415 functions; 9956 random cases were skipped
by the reference's invalid-memory/step bounds. All 15 default host probes, 17
project tests and 245 Vulkan pool checks also pass. The GPU probe has zero core
validation messages; this does not establish validity of the game's 3D path.

`OOT_NONLOCAL_TRACE=1` enables bounded continuation diagnostics. Full private game
logs, saves, generated code and images remain outside the repository.
