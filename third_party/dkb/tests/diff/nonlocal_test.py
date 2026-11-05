"""Generate authored AArch64 setjmp callers, run native, compare with Unicorn.

Usage: nonlocal_test.py --cc /path/to/clang --out ignored/test-directory
The compiler's directory must also provide ld.lld and llvm-objcopy.
"""
import argparse
import ctypes
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import unicorn as uc
from unicorn import arm64_const as A

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'recomp'))
from gen import Emitter, chunk_text
from lifter import Lifter
from module import Module


def plt_cases():
    mod = Module.__new__(Module)
    mod.base = mod.lo = 0x100000
    mod.words = np.array([0x90000010, 0xf9440211, 0x91200210, 0xd61f0220], dtype='<u4')
    mod.nso = SimpleNamespace(syms=[('setjmp', 2, 0, 0, 0)], relocs=[(0x800, 1026, 0, 0)])
    assert mod.setjmp_targets() == {mod.lo}
    mod.words[3] = 0xd61f0200  # A different branch register is not this PLT form.
    assert not mod.setjmp_targets()
    mod.words[3] = 0xd61f0220
    mod.nso.relocs = [(0x808, 1026, 0, 0)]
    assert not mod.setjmp_targets()
    mod.nso.relocs = [(0x800, 1027, 0, 0)]
    assert not mod.setjmp_targets()
    mod.nso.relocs = [(0x800, 1026, 0, 0)]
    mod.nso.syms = [('ordinary_call', 2, 0, 0, 0)]
    assert not mod.setjmp_targets()


def main():
    plt_cases()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cc', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    here = Path(__file__).resolve().parent
    suffix = '.exe' if os.name == 'nt' else ''
    elf, binary = args.out / 'fixture.elf', args.out / 'fixture.bin'
    linker = args.cc.parent.resolve() / ('ld.lld' + suffix)
    subprocess.run([str(args.cc), '--target=aarch64-none-elf', '-nostdlib', f'--ld-path={linker}',
                    '-Wl,--image-base=0x100000', '-Wl,-Ttext=0x100000', '-Wl,--entry=fixture',
                    str(here / 'nonlocal_fixture.S'), '-o', str(elf)], check=True)
    subprocess.run([str(args.cc.parent / ('llvm-objcopy' + suffix)), '-O', 'binary', '--only-section=.text',
                    str(elf), str(binary)], check=True)
    mod = Module.__new__(Module)
    mod.base = mod.lo = 0x100000
    mod.image = binary.read_bytes()
    mod.hi = mod.lo + len(mod.image)
    mod.words = np.frombuffer(mod.image, dtype='<u4')
    mod.nso = SimpleNamespace(syms=[('setjmp', 2, 1, 0x200, 0)], relocs=[])
    mod.lifter = Lifter(mod.base, 'c')
    from collections import OrderedDict
    mod._cache = OrderedDict()
    assert mod.setjmp_targets() == {0x100200}
    starts = [mod.lo + x for x in (0, 0x100, 0x200, 0x300)]
    generated = args.out / 'fixture.c'
    emitter = Emitter(mod, set(starts))
    generated.write_text(chunk_text('authored', 0, emitter, list(zip(starts, starts[1:] + [mod.hi]))))
    assert emitter.stats['nonlocal_functions'] == 2
    assert emitter.stats['setjmp_continuations'] == 2
    library = args.out / ('nonlocal.dll' if os.name == 'nt' else 'nonlocal.so')
    subprocess.run([str(args.cc), '-O2', '-g', '-shared', '-static', '-I', str(ROOT / 'runtime'),
                    str(generated), str(here / 'nonlocal_harness.c'), str(ROOT / 'runtime/nonlocal.c'),
                    '-o', str(library)], check=True)
    native = ctypes.CDLL(str(library.resolve()))
    native.run_case.argtypes = [ctypes.c_uint64, ctypes.POINTER(ctypes.c_uint64)]
    native.registry_cases()
    mu = uc.Uc(uc.UC_ARCH_ARM64, uc.UC_MODE_ARM)
    mu.mem_map(mod.lo, 0x2000)
    mu.mem_write(mod.lo, mod.image)
    buf = 0x7200000000
    mu.mem_map(buf, 0x40000)
    mu.reg_write(A.UC_ARM64_REG_CPACR_EL1, 0x300000)
    xregs = [A.UC_ARM64_REG_X0+i for i in range(29)] + [A.UC_ARM64_REG_X29, A.UC_ARM64_REG_X30]
    cases = [0, 1, 2, 12345, 0x7fffffff, 0x80000000, 0xffffffff] * 16
    for value in cases:
        mu.mem_write(buf, bytes(0x40000))
        for reg in xregs:
            mu.reg_write(reg, 0)
        mu.reg_write(xregs[0], buf)
        mu.reg_write(xregs[1], value)
        mu.reg_write(xregs[30], 0x101000)
        mu.reg_write(A.UC_ARM64_REG_SP, buf+0x3f000)
        for i in range(19, 30):
            mu.reg_write(xregs[i], 0x500+i)
        for i in range(8, 16):
            mu.reg_write(A.UC_ARM64_REG_Q0+i, (0xdeadbeef << 64) | (0x600+i))
        mu.emu_start(mod.lo, 0x101000, count=1000)
        assert mu.reg_read(A.UC_ARM64_REG_PC) == 0x101000
        expected = [mu.reg_read(xregs[0]), mu.reg_read(A.UC_ARM64_REG_SP)]
        expected += [mu.reg_read(xregs[i]) for i in range(19, 31)]
        expected += [mu.reg_read(A.UC_ARM64_REG_D0+i) for i in range(8, 16)]
        out = (ctypes.c_uint64 * 22)()
        native.run_case(value, out)
        assert list(out) == expected, (value, list(out), expected)
    print(f'PASS: {len(cases)} generated nested longjmp/Unicorn comparisons; owner, PC, SP, reuse, cleanup, host-depth checks')


if __name__ == '__main__':
    main()
