"""Compare PACGA QARMA5 against Unicorn ARM64 with explicit APGA keys."""
import ctypes,random,struct,sys,concurrent.futures
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM
from unicorn.arm64_const import *
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'third_party/dkb/recomp'))
from lifter import Lifter
REG_CASES=[(2,0,1),(0,0,1),(1,0,1),(2,31,1),(2,0,31),(31,0,1),(30,30,30),(31,31,31)]
WORDS=[0x9ac03000|(m<<16)|(n<<5)|d for d,n,m in REG_CASES]
def generate(path):
    lift=Lifter(0,simd='c')
    lines=['/* Original PACGA test encodings; no game content. */','#include "cpu.h"',
           '__declspec(dllexport) void evaluate(unsigned test, uint64_t *state) {',
           'Cpu cpu={0}; Cpu *c=&cpu; memcpy(c->x,state,256); c->sp=state[32]; c->nzcv=state[33]; switch(test){']
    for i,w in enumerate(WORDS):lines.append(f'case {i}: {lift.lift(w,0).code} break;')
    lines+=['} memcpy(state,c->x,256); state[32]=c->sp; state[33]=c->nzcv;}']
    Path(path).write_text('\n'.join(lines)+'\n',encoding='utf-8')
def main(path):
    dll=ctypes.CDLL(str(Path(path).resolve()));fn=dll.oot_pacga_qarma5
    fn.argtypes=[ctypes.c_uint64]*4;fn.restype=ctypes.c_uint64
    native=dll.rt_pacga;native.argtypes=[ctypes.c_uint64]*2;native.restype=ctypes.c_uint64
    key=dll.oot_pacga_test_key;key.argtypes=[ctypes.c_uint64]*2
    u=Uc(UC_ARCH_ARM64,UC_MODE_ARM);u.ctl_set_cpu_model(UC_CPU_ARM64_MAX);u.mem_map(0x10000,0x1000)
    # Unicorn's documented PAuth setup: non-secure AArch64 EL1 and no EL2/3
    # instruction trap. Without SCR.NS/RW, PACGA traps before doing arithmetic.
    for reg,flags in [((3,6,1,1,0),1|(1<<10)|(1<<17)),
                      ((3,0,1,0,0),(1<<31)|(1<<30)),
                      ((3,4,1,1,0),1<<41)]:
        u.cpr_write(*reg,u.cpr_read(*reg)|flags)
    u.mem_write(0x10000,struct.pack('<I',0x9ac13002)) # PACGA x2,x0,x1
    rnd=random.Random(20261105);cases=[(0,0,0,0),((1<<64)-1,)*4]+[tuple(rnd.getrandbits(64) for _ in range(4)) for _ in range(2048)]
    for data,mod,lo,hi in cases:
        u.cpr_write(3,0,2,3,0,lo);u.cpr_write(3,0,2,3,1,hi)
        u.reg_write(UC_ARM64_REG_X0,data);u.reg_write(UC_ARM64_REG_X1,mod)
        u.emu_start(0x10000,0x10004,count=1);want=u.reg_read(UC_ARM64_REG_X2)
        got=fn(data,mod,lo,hi)
        if got!=want:raise AssertionError(f'PACGA mismatch {got:016x} != {want:016x}')
        assert got & 0xffffffff==0
    # Real host entry: stable across threads, sensitive to data and modifier,
    # and independent from x86 thread IDs. This preserves guest fiber signatures.
    key(0x0123456789abcdef,0xfedcba9876543210)
    u.cpr_write(3,0,2,3,0,0x0123456789abcdef);u.cpr_write(3,0,2,3,1,0xfedcba9876543210)
    evaluate=dll.evaluate;evaluate.argtypes=[ctypes.c_uint,ctypes.POINTER(ctypes.c_uint64)]
    host_regs=[globals()[f'UC_ARM64_REG_X{i}'] for i in range(31)]
    for i,w in enumerate(WORDS):
        addr=0x10100+i*4;u.mem_write(addr,struct.pack('<I',w))
        for _ in range(64):
            before=[rnd.getrandbits(64) for _ in range(33)]+[rnd.randrange(16)<<28]
            for r,value in zip(host_regs,before):u.reg_write(r,value)
            u.reg_write(UC_ARM64_REG_SP,before[32]);u.reg_write(UC_ARM64_REG_NZCV,before[33])
            u.emu_start(addr,addr+4,count=1)
            want=[u.reg_read(r) for r in host_regs]+[before[31],u.reg_read(UC_ARM64_REG_SP),u.reg_read(UC_ARM64_REG_NZCV)]
            state=(ctypes.c_uint64*34)(*before);evaluate(i,state)
            assert list(state)==want,f'lifted PACGA register mismatch: {w:08x}'
    expected=native(123,456)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        assert all(x==expected for x in pool.map(lambda _:native(123,456),range(1000)))
    assert native(122,456)!=expected and native(123,457)!=expected
    # Model the SDK's chained state signatures: save -> restore matches;
    # corruption of any of 12 register slots must be detected in these fixtures.
    def signature(values,context):
        return tuple(native(values[i+6],native(values[i],context+i)) for i in range(6))
    regs=[rnd.getrandbits(64) for _ in range(12)];saved=signature(regs,0x8000000000000000)
    assert signature(regs,0x8000000000000000)==saved
    for i in range(12):
        changed=regs.copy();changed[i]^=1;assert signature(changed,0x8000000000000000)!=saved
    lift=Lifter(0,simd='c')
    assert 'c->sp' in lift.lift(0x9adf3002,0).code
    assert '0ull' in lift.lift(0x9ac133e2,0).code
    assert lift.lift(0x9ac1301f,0).code.startswith('(void)(') # XZR destination discarded
    print(f'PASS PACGA: {len(cases)} QARMA5 reference cases, 512 lifted register/flags cases, 1000 thread calls, 12 tampered contexts')
if __name__=='__main__':
    if sys.argv[1]=='--generate':generate(sys.argv[2])
    else:main(sys.argv[1])
