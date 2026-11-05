"""Compile original synthetic AArch64 instructions using the vendored lifter; test against Unicorn."""
from pathlib import Path
import ctypes
import random
import struct
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'third_party/dkb/recomp'))
WORDS=[0x8b010000,0xeb010000,0x8a010000,0xca010000,0xaa010000,0x9b017c00,0x0b010000,0x9ac12000,0x9ac12800,0x9ac10800]
VECTOR_WORDS=[base|(q<<30)|(u<<29)|(m<<16)|(n<<5)|d
              for base in [0x0e809400] for q in (0,1) for u in (0,1)
              for d,n,m in [(0,1,2),(0,0,2),(0,1,0),(0,0,0)]] + [0x2ef8f800|(q<<30)|(n<<5) for q in (0,1) for n in (0,1)]

def generate(path):
    from lifter import Lifter
    lift=Lifter(0x10000,simd='c')
    lines=['/* Original synthetic test instructions. No game content. */','#include "cpu.h"','#include "simd.h"']
    for i,w in enumerate(WORDS):
        ins=lift.lift(w,0x10000)
        assert ins.kind=='op',ins.kind
        lines.append(f'static void test_{i}(Cpu *c){{{ins.code}}}')
    lines+=['__declspec(dllexport) int evaluate(unsigned test, uint64_t a, uint64_t b, uint64_t flags, uint64_t *out) {',
            'Cpu c={0}; c.x[0]=a; c.x[1]=b; c.nzcv=flags; switch(test){']
    for i in range(len(WORDS)):
        lines.append(f'case {i}: test_{i}(&c); break;')
    lines+=['default: return -1;} out[0]=c.x[0]; out[1]=c.nzcv; return 0;}']
    lines+=['__declspec(dllexport) int evaluate_vector(unsigned test, const void *in, void *out) {',
            'Cpu state={0}; Cpu *c=&state; memcpy(c->v,in,48); switch(test){']
    for i,w in enumerate(VECTOR_WORDS):
        ins=lift.lift(w,0x10000);assert ins.kind=='op'
        lines.append(f'case {i}: {ins.code} break;')
    lines+=['default: return -1;} memcpy(out,c->v,48); return 0;}']
    Path(path).write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(f'Generated {len(WORDS)} native test functions using DKB lifter')

def test(path):
    from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM
    from unicorn.arm64_const import UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_NZCV
    lib=ctypes.CDLL(str(Path(path).resolve()))
    lib.evaluate.argtypes=[ctypes.c_uint,ctypes.c_uint64,ctypes.c_uint64,ctypes.c_uint64,ctypes.POINTER(ctypes.c_uint64)]
    lib.evaluate.restype=ctypes.c_int
    emu=Uc(UC_ARCH_ARM64,UC_MODE_ARM);emu.mem_map(0x10000,0x1000)
    randomizer=random.Random(20261105)
    edge=[0,1,31,32,63,64,(1<<63)-1,1<<63,(1<<64)-1]
    cases=[(a,b) for a in edge for b in edge]+[(randomizer.getrandbits(64),randomizer.getrandbits(64)) for _ in range(256)]
    count=0
    for i,word in enumerate(WORDS):
        # Separate instruction addresses avoid stale translation-cache entries.
        addr=0x10000+i*4;emu.mem_write(addr,struct.pack('<I',word))
        for a,b in cases:
            flags=randomizer.randrange(16)<<28
            emu.reg_write(UC_ARM64_REG_X0,a);emu.reg_write(UC_ARM64_REG_X1,b);emu.reg_write(UC_ARM64_REG_NZCV,flags)
            emu.emu_start(addr,addr+4,count=1)
            expected=(emu.reg_read(UC_ARM64_REG_X0),emu.reg_read(UC_ARM64_REG_NZCV))
            out=(ctypes.c_uint64*2)()
            if lib.evaluate(i,a,b,flags,out)!=0 or tuple(out)!=expected:
                raise AssertionError(f'{word:08x} a={a:x} b={b:x}: native={tuple(out)} reference={expected}')
            count+=1
    print(f'PASS {count} AArch64-to-native differential cases across {len(WORDS)} encodings (X0 and NZCV). Seed=20261105')
    print('Unicorn is a test-only reference; runtime does not link or launch an emulator.')
    from unicorn.arm64_const import UC_CPU_ARM64_MAX,UC_ARM64_REG_Q0,UC_ARM64_REG_Q1,UC_ARM64_REG_Q2
    emu=Uc(UC_ARCH_ARM64,UC_MODE_ARM);emu.ctl_set_cpu_model(UC_CPU_ARM64_MAX);emu.mem_map(0x10000,0x1000)
    lib.evaluate_vector.argtypes=[ctypes.c_uint,ctypes.c_void_p,ctypes.c_void_p]
    lib.evaluate_vector.restype=ctypes.c_int
    edge_vectors=[bytes(48),bytes([255])*48,bytes(range(48)),bytes.fromhex('007c00fc017c017e00800000ff7b01fc')*3]
    inputs=edge_vectors+[randomizer.randbytes(48) for _ in range(256)]
    count=0
    for i,w in enumerate(VECTOR_WORDS):
        addr=0x10000+i*4;emu.mem_write(addr,struct.pack('<I',w))
        for data in inputs:
            for k,reg in enumerate((UC_ARM64_REG_Q0,UC_ARM64_REG_Q1,UC_ARM64_REG_Q2)):
                emu.reg_write(reg,int.from_bytes(data[k*16:(k+1)*16],'little'))
            emu.emu_start(addr,addr+4,count=1)
            expected=b''.join(emu.reg_read(r).to_bytes(16,'little') for r in (UC_ARM64_REG_Q0,UC_ARM64_REG_Q1,UC_ARM64_REG_Q2))
            out=ctypes.create_string_buffer(48)
            if lib.evaluate_vector(i,data,out)!=0 or out.raw!=expected:
                raise AssertionError(f'vector {w:08x}: native={out.raw.hex()} reference={expected.hex()}')
            count+=1
    print(f'PASS {count} UDOT/SDOT/FNEG-half differential cases, including register aliasing, Q=0 upper clearing, overflow and NaN bits')
if __name__=='__main__':
    if sys.argv[1]=='--test':test(sys.argv[2])
    else:generate(sys.argv[1])
