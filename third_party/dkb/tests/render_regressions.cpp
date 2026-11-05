// Authored instructions and address ranges; no game assets or generated shader bytes.
#include <cstdio>
#include <bit>
#include <vector>
#include "shader_recompiler/frontend/ampere/lower_to_maxwell.h"
#include "../runtime/vk_import_window.h"
using namespace Shader::Ampere;
static unsigned checks, failures;
#define CHECK(x) do { ++checks; if (!(x)) { ++failures; std::fprintf(stderr, "line %d: %s\n", __LINE__, #x); } } while (0)
static void bits(Instruction& i, unsigned at, unsigned n, u32 v) {
    for (unsigned b=0; b<n; b++) {
        auto& w=i.words[(at+b)/32]; unsigned bit=(at+b)%32;
        w=(w & ~(1u<<bit)) | (((v>>b)&1u)<<bit);
    }
}
static Instruction op(u32 code) { Instruction i{}; bits(i,0,12,code); bits(i,12,4,7); return i; }
static LoweredProgram lower(Instruction i) {
    auto end=op(0x94d); bits(end,87,4,7);
    const std::vector<Instruction> code{i,end}; return LowerToMaxwell(code,"full");
}
static void txq() {
    for (u32 mask=1; mask<16; mask++) {
        auto i=op(0xb6f); bits(i,16,8,8); bits(i,24,8,4); bits(i,54,5,2);
        bits(i,64,8,255); bits(i,72,4,mask);
        auto r=lower(i); unsigned n=std::popcount(mask);
        CHECK(bool(r)==(n<=2));
        if (r) {
            CHECK(((r.instructions[0]>>31)&15)==mask);
            CHECK((r.instructions[0]&255)==8);
            CHECK(r.required_texture_buffer==2);
        }
        bits(i,64,8,12); r=lower(i); CHECK(bool(r));
        if (r) {
            CHECK((r.instructions[0]&255)==250);
            for (unsigned k=0; k<n; k++) {
                CHECK((r.instructions[k+1]&255)==(k<2?8+k:12+k-2));
                CHECK(((r.instructions[k+1]>>20)&255)==250+k);
            }
        }
    }
    auto i=op(0xb6f); bits(i,64,8,255); CHECK(!lower(i)); // empty output mask
}
static void i2f() {
    const u32 values[]={0,1,0x80,0x8000,0x7fff,0x80017fff,0xffffffff,0x81ff007f};
    for (u32 half=0; half<2; half++) for (u32 sign=0; sign<2; sign++)
        for (u32 sel=0; sel<(half?2u:4u); sel++) {
            auto i=op(0x306); bits(i,16,8,8); bits(i,32,8,4); bits(i,60,2,sel);
            i.words[2]=0x1000|(half<<20)|(sign<<10);
            auto r=lower(i); CHECK(bool(r)); if (!r) continue;
            const u64 m=r.instructions[0];
            CHECK(((m>>10)&3)==half); CHECK(((m>>13)&1)==sign);
            CHECK(((m>>41)&3)==sel*(half?2u:1u));
            for (u32 value: values) {
                unsigned width=((m>>10)&3)?16:8, shift=((m>>41)&3)*8;
                u32 sample=(value>>shift)&((1u<<width)-1);
                int result=int(sample); if ((m>>13)&1 && (sample&(1u<<(width-1)))) result-=1u<<width;
                u32 part=value>>(sel*(half?16:8));
                int expected=half?(sign?int(int16_t(part)):int(uint16_t(part))):
                                  (sign?int(int8_t(part)):int(uint8_t(part)));
                CHECK(float(result)==float(expected));
            }
        }
    auto i=op(0x306); i.words[2]=0x101000; bits(i,60,2,2); CHECK(!lower(i));
}
static void texture_half_order() {
    auto i=op(0xb60); bits(i,16,8,8); bits(i,24,8,4); bits(i,32,8,6);
    bits(i,61,3,1); bits(i,64,8,255); bits(i,72,4,15); bits(i,79,1,1); bits(i,81,3,7);
    auto r=lower(i); CHECK(bool(r)); if (!r) return;
    unsigned merges=0;
    for (u64 m:r.instructions) if ((m&0xfff8000000000000ull)==0x5c18000000000000ull) {
        // Maxwell ISCADD Rd, Ra, Rb, 16 is (Ra << 16) + Rb.
        const u32 a=(m>>8)&255, b=(m>>20)&255;
        const u32 regs[2]={0x3400,0x3a00}; // authored half bits .25, .75
        CHECK(a==247 && b==246);
        if (a>=246 && a<=247 && b>=246 && b<=247)
            CHECK((regs[a-246]<<16)+regs[b-246]==0x3a003400);
        ++merges;
    }
    CHECK(merges==2);
}
template<class T> static bool compare(T a,T b,unsigned relation) {
    switch (relation) {
    case 1:return a<b; case 2:return a==b; case 3:return a<=b;
    case 4:return a>b; case 5:return a!=b; case 6:return a>=b;
    default:return false;
    }
}
static void extended_compare() {
    const u32 highs[]={0,1,0x7fffffff,0x80000000,0xffffffff}, lows[]={0,1,0xffffffff};
    for (u32 sign=0;sign<2;sign++) for (u32 relation=1;relation<=6;relation++)
    for (u32 invert=0;invert<2;invert++) for (u32 lowp=0;lowp<2;lowp++) {
        auto i=op(0x20c); bits(i,24,8,4); bits(i,32,8,6);
        bits(i,68,3,lowp); bits(i,71,1,invert); bits(i,72,1,1); bits(i,73,1,sign);
        bits(i,76,3,relation); bits(i,81,3,0); bits(i,84,3,7); bits(i,87,4,7);
        auto r=lower(i); CHECK(bool(r)); if (!r) continue;
        unsigned count=(relation==2 || relation==5)?1:2;
        for (u32 ah:highs) for (u32 bh:highs) for (u32 al:lows) for (u32 bl:lows) {
            bool p[8]={}; p[7]=true; p[lowp]=compare(al,bl,relation)^bool(invert);
            for (unsigned n=0;n<count;n++) {
                u64 m=r.instructions[n];
                CHECK(((m>>8)&255)==4 && ((m>>20)&255)==6);
                bool v=(m>>48)&1 ? compare(std::bit_cast<int32_t>(ah),std::bit_cast<int32_t>(bh),(m>>49)&7)
                                     :compare(ah,bh,(m>>49)&7);
                bool input=p[(m>>39)&7]^bool((m>>42)&1);
                unsigned combine=(m>>45)&3;
                CHECK(combine<2);
                p[(m>>3)&7]=combine ? v||input : v&&input;
            }
            u64 a=(u64{ah}<<32)|al,b=(u64{bh}<<32)|bl;
            bool expected=sign ? compare(std::bit_cast<int64_t>(a),std::bit_cast<int64_t>(b),relation)
                               :compare(a,b,relation);
            CHECK(p[0]==expected);
        }
        auto rejected=i; bits(rejected,84,3,2); CHECK(!lower(rejected));
        rejected=i; bits(rejected,74,2,1); CHECK(!lower(rejected));
        rejected=i; bits(rejected,12,4,0); CHECK(!lower(rejected));
    }
}
static void windows() {
    uint64_t lo=0,hi=0; const uint64_t base=0x100000000, end=base+0x98010000, cap=0x80000000;
    CHECK(vk_import_window(base,end,base+0x7ffff000,0x20000,0x1000,cap,&lo,&hi));
    CHECK(lo==base+0x7ffff000 && hi==end && hi-lo<=cap);
    CHECK(vk_import_window(base,end,base,cap,0x1000,cap,&lo,&hi) && hi-lo==cap);
    CHECK(!vk_import_window(base,end,base+1,cap,0x1000,cap,&lo,&hi));
    CHECK(!vk_import_window(base,end,end-1,2,0x1000,cap,&lo,&hi));
    CHECK(!vk_import_window(base,end,base,UINT64_MAX,0x1000,cap,&lo,&hi));
    CHECK(!vk_import_window(base,end,base-1,1,0x1000,cap,&lo,&hi));
    CHECK(!vk_import_window(base,end,base,1,3,cap,&lo,&hi));
    CHECK(!vk_import_window(base,end,base,0,0x1000,cap,&lo,&hi));
    CHECK(!vk_import_window(base,end,base,1,0x1000,0xfff,&lo,&hi));
}
static void extended_accumulator() {
    // ISETP.EX computes a 64-bit relation, then ANDs an independent predicate.
    // Exercise aliasing, every predicate state and false/inverted guards. The
    // emitted Maxwell stream must preserve all seven live predicates except Pd.
    const u32 highs[]={0,1,0x7fffffff,0x80000000,0xffffffff};
    const u32 slots[][3]={{0,0,1},{1,2,1},{1,1,2},{3,0,2},{0,7,7}};
    for (u32 relation=1;relation<=6;relation++) for (u32 sign=0;sign<2;sign++)
    for (auto& slot:slots) for (u32 inv=0;inv<4;inv++) for (u32 guard:{7u,4u,12u}) {
        const u32 dst=slot[0], low=slot[1]|((inv&1)<<3), acc=slot[2]|((inv&2)<<2);
        if (acc==7) continue; // The existing plain-form suite covers this fast path.
        auto i=op(0x20c); bits(i,12,4,guard); bits(i,24,8,4); bits(i,32,8,6);
        bits(i,68,4,low); bits(i,72,1,1); bits(i,73,1,sign);
        bits(i,76,3,relation); bits(i,81,3,dst); bits(i,84,3,7); bits(i,87,4,acc);
        auto out=lower(i); CHECK(bool(out)); if (!out) continue;
        for (u32 state=0;state<128;state++) for (u32 a:highs) for (u32 b:highs) {
            bool predicates[8]; u32 registers[256]={}; registers[4]=a; registers[6]=b;
            for (unsigned k=0;k<8;k++) predicates[k]=k==7 || bool(state&(1u<<k));
            auto read=[&](u32 p) {return predicates[p&7]^bool(p&8);};
            const bool enabled=read(guard), lo=read(low), extra=read(acc);
            const bool eq=a==b;
            const bool ordered=sign ? compare(std::bit_cast<int32_t>(a),std::bit_cast<int32_t>(b),relation<=3?1:4)
                                    :compare(a,b,relation<=3?1:4);
            const bool wide=relation==2 ? eq&&lo : relation==5 ? !eq||lo : ordered||(eq&&lo);
            const bool expected=enabled ? wide&&extra : predicates[dst];
            for (unsigned n=0;n<out.source_instruction_offsets[1];n++) {
                const u64 m=out.instructions[n];
                if (!read((m>>16)&15)) continue;
                if ((m&0xfff0000000000000ull)==0x5b60000000000000ull) {
                    const u32 lhs=registers[(m>>8)&255],rhs=registers[(m>>20)&255];
                    bool v=(m>>48)&1 ? compare(std::bit_cast<int32_t>(lhs),std::bit_cast<int32_t>(rhs),(m>>49)&7)
                                         :compare(lhs,rhs,(m>>49)&7);
                    bool input=read((m>>39)&15);
                    predicates[(m>>3)&7]=((m>>45)&3) ? v||input : v&&input;
                } else if ((m&0xfff8000000000000ull)==0x38e8000000000000ull) {
                    u32 mask=(m>>20)&0x7f, packed=0;
                    for (u32 k=0;k<7;k++) if (predicates[k]) packed|=1u<<k;
                    registers[m&255]=(registers[(m>>8)&255]&~mask)|(packed&mask);
                } else if ((m&0xfff8000000000000ull)==0x38f0000000000000ull) {
                    const u32 mask=(m>>20)&0x7f,value=registers[(m>>8)&255];
                    for (u32 k=0;k<7;k++) if (mask&(1u<<k)) predicates[k]=bool(value&(1u<<k));
                } else if ((m&0xfff0000000000000ull)==0x5090000000000000ull) {
                    CHECK(((m>>24)&3)==0 && ((m>>45)&3)==0);
                    predicates[(m>>3)&7]=read((m>>12)&15)&&read((m>>29)&15)&&read((m>>39)&15);
                } else CHECK(false);
                predicates[7]=true;
            }
            for (u32 k=0;k<7;k++) CHECK(predicates[k]==(k==dst ? expected : bool(state&(1u<<k))));
        }
    }
}
int main() {
    txq(); i2f(); texture_half_order(); extended_compare(); extended_accumulator(); windows();
    std::printf("render regressions: %u checks, %u failures\n", checks, failures);
    return failures?1:0;
}
