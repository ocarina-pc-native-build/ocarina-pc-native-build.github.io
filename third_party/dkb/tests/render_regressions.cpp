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
static void bindless_textures() {
    const u32 coord_count[]={1,2,3,3,2,3,0,4}, types[]={0,2,4,6,1,3,0,7};
    for (u32 opcode:{0xf60u,0x361u}) for (u32 dim:{0u,1u,2u,3u,4u,5u,7u})
    for (u32 lod=0;lod<4;lod++) for (u32 offset=0;offset<2;offset++)
    for (u32 depth=0;depth<2;depth++) for (u32 packed=0;packed<2;packed++) {
        const u32 coords=coord_count[dim], handle_count=opcode==0x361, has_lod=lod>=2;
        const u32 count=coords+handle_count+has_lod+offset+depth;
        const u32 a_count=opcode==0x361 && (!packed || count>4) ? coords : count<=4 ? (count+1)/2 : 4;
        auto input=[&](u32 n) {return 1000+(n<a_count ? 20+n : 40+n-a_count);};
        auto i=op(opcode); bits(i,16,8,8); bits(i,24,8,20); bits(i,32,8,40);
        if (opcode==0xf60) bits(i,40,6,22); // UR22 maps to R240, not R238.
        bits(i,59,1,opcode==0x361); bits(i,60,1,packed); bits(i,61,3,dim);
        bits(i,64,8,depth?255:10); bits(i,72,4,depth?1:15); bits(i,76,1,offset);
        bits(i,78,1,depth); bits(i,81,3,7); bits(i,87,3,lod);
        auto out=lower(i); CHECK(bool(out)); if (!out) continue;
        CHECK(out.required_texture_buffer==~0U);
        u32 reg[256]; for (u32 n=0;n<256;n++) reg[n]=1000+n;
        bool sampled=false;
        for (u64 m:out.instructions) {
            if ((m&0xfff8000000000000ull)==0x5c98000000000000ull) {
                reg[m&255]=reg[(m>>20)&255];
            } else if ((m&0xff80000000000000ull)==0xde80000000000000ull) {
                CHECK(!sampled); sampled=true;
                CHECK(((m>>8)&255)==250 && ((m>>20)&255)==246);
                CHECK(((m>>28)&7)==types[dim]); CHECK(((m>>31)&15)==(depth?1:15));
                CHECK(((m>>36)&1)==offset && ((m>>37)&7)==lod && ((m>>50)&1)==depth);
                for (u32 n=0;n<coords;n++) CHECK(reg[250+n]==input(n));
                CHECK(reg[246]==(opcode==0xf60?1240:input(coords)));
                u32 meta=247,next=coords+handle_count;
                if (has_lod) CHECK(reg[meta++]==input(next++));
                if (offset) CHECK(reg[meta++]==input(next++));
                if (depth) CHECK(reg[meta++]==input(next++));
                for (u32 n=0;n<4;n++) reg[250+n]=2000+n; // distinguish packed result components
            }
        }
        CHECK(sampled); CHECK(reg[8]==2000);
        if (!depth) {CHECK(reg[9]==2001); CHECK(reg[10]==2002); CHECK(reg[11]==2003);}
        auto bad=i; bits(bad,81,3,2); CHECK(!lower(bad));
        if (opcode==0xf60) {bad=i; bits(bad,40,6,28); CHECK(!lower(bad));}
    }
}
static void wide_immediate_multiply() {
    const u32 vals[]={0,1,0xffff,0x10000,0x10001,0x7fffffff,0x80000000,0xffffffff};
    const u64 adds[]={0,1,0xffffffff,0x100000000ull,0x12345678ffffffffull,~u64{0}};
    for (bool uniform:{false,true}) for (u32 dst:{4u,8u,12u})
    for (u32 guard: {7u,1u,9u}) {
        if (uniform && guard!=7) continue;
        for (u32 a:vals) for (u32 b:vals) for (u64 c:adds) {
            auto i=op(uniform?0x8a5:0x825); bits(i,12,4,guard); bits(i,16,8,dst); bits(i,24,8,4);
            i.words[1]=b; i.words[2]=(uniform?0x0f8e0000:0x078e0000)|12;
            auto out=lower(i); CHECK(bool(out)); if (!out) continue;
            for (bool gate:{false,true}) {
                u32 r[256]={}; const unsigned bank=uniform?216:0;
                r[bank+4]=a; r[bank+12]=u32(c); r[bank+13]=u32(c>>32);
                const u64 before=u64{r[bank+dst]}|(u64{r[bank+dst+1]}<<32);
                bool carry=false;
                for (unsigned n=0;n<out.source_instruction_offsets[1];n++) {
                    const u64 m=out.instructions[n]; const unsigned pred=(m>>16)&15;
                    if (!((pred&7)==7 || (gate^bool(pred&8)))) continue;
                    u32 value=0; const u32 x=r[(m>>8)&255],y=r[(m>>20)&255];
                    if ((m&0xffc0000000000000ull)==0x3600000000000000ull ||
                        (m&0xffc0000000000000ull)==0x5b00000000000000ull) {
                        const bool imm=(m>>56)==0x36;
                        u32 av=(x>>(((m>>53)&1)?16:0))&0xffff;
                        u32 bv=imm ? (m>>20)&0xffff : (y>>(((m>>35)&1)?16:0))&0xffff;
                        u32 cv=r[(m>>39)&255];
                        switch ((m>>50)&3) {case 1:cv&=0xffff;break;case 2:cv>>=16;break;default:break;}
                        value=av*bv+cv;
                    } else if ((m&0xfff8000000000000ull)==0x3828000000000000ull) value=x>>((m>>20)&31);
                    else if ((m&0xfff8000000000000ull)==0x5c18000000000000ull) value=(x<<((m>>39)&31))+y;
                    else if ((m&0xfff0000000000000ull)==0x5c10000000000000ull) {
                        const u64 sum=u64{x}+y+(((m>>43)&1)?carry:0); value=u32(sum);
                        if ((m>>47)&1) carry=bool(sum>>32);
                    } else CHECK(false);
                    r[m&255]=value; r[255]=0;
                }
                const bool enabled=guard==7 || (gate^bool(guard&8));
                const u64 expected=enabled ? u64{a}*b+c : before;
                CHECK((u64{r[bank+dst]}|(u64{r[bank+dst+1]}<<32))==expected);
            }
        }
    }
}
static void array_gather() {
    for (u32 mask=1;mask<16;mask++) for (u32 component=0;component<4;component++)
    for (u32 dst:{8u,20u,40u}) for (u32 guard:{7u,2u,10u}) {
        const u32 count=std::popcount(mask), second=count>2?60:255;
        auto i=op(0xb63); bits(i,16,8,dst); bits(i,24,8,20); bits(i,32,8,40);
        bits(i,12,4,guard); bits(i,40,14,8); bits(i,54,5,2); bits(i,60,1,1); bits(i,61,3,5);
        bits(i,64,8,second); bits(i,72,4,mask); bits(i,81,3,7); bits(i,87,2,component);
        auto out=lower(i); CHECK(bool(out)); if (!out) continue;
        CHECK(out.required_texture_buffer==2);
        for (bool enabled:{false,true}) {
            u32 r[256]; for(u32 n=0;n<256;n++)r[n]=1000+n;
            const bool execute=guard==7 || enabled; bool gathered=false;
            for(unsigned k=0;k<out.source_instruction_offsets[1];k++) {
                const u64 m=out.instructions[k]; CHECK(((m>>16)&15)==guard);
                if(!execute)continue;
                if((m&0xfff8000000000000ull)==0x5c98000000000000ull)r[m&255]=r[(m>>20)&255];
                else if((m&0xfc00000000000000ull)==0xc800000000000000ull) {
                    CHECK(!gathered); gathered=true;
                    CHECK(((m>>28)&7)==3 && ((m>>31)&15)==mask && ((m>>56)&3)==component);
                    CHECK(((m>>36)&8191)==8 && ((m>>20)&255)==255);
                    CHECK(r[250]==1020 && r[251]==1021 && r[252]==1040);
                    for(u32 n=0;n<count;n++)r[250+n]=2000+n;
                } else CHECK(false);
            }
            CHECK(gathered==execute);
            for(u32 n=0;n<count;n++) {
                const u32 target=n<2?dst+n:second+n-2;
                CHECK(r[target]==(execute?2000+n:1000+target));
            }
        }
        auto bad=i; bits(bad,78,1,1); CHECK(!lower(bad));
        bad=i; bits(bad,79,1,1); CHECK(!lower(bad));
        bad=i; bits(bad,76,2,1); CHECK(!lower(bad));
    }
}
static void high_native_registers() {
    // Constant/immediate comparisons contain encoded predicates and constants,
    // not GPRs in their wide operand fields. Preserve those bits while spilling
    // source/result registers, including a disabled write and an aliased result.
    for(u32 opcode:{0xa0au,0x80bu}) for(u32 src:{215u,216u,239u,254u})
    for(u32 dst:{4u,216u,239u,254u}) for(bool enabled:{false,true}) {
        Instruction original{{(src<<24)|((opcode==0xa0a?dst:0)<<16)|0x7000|opcode,
                              opcode==0xa0a?0x800000u:0x3f800000u,
                              opcode==0xa0a?0x03801000u:0x03901000u,0}};
        auto rewritten=original;NativeRegisterSpill plan;CHECK(plan.Prepare(rewritten));
        CHECK(rewritten.words[1]==original.words[1] && rewritten.words[2]==original.words[2]);
        if(opcode==0x80b)CHECK(rewritten.Bits(16,8)==0); // predicate fields are not spilled
        std::array<u32,256> physical{},local{},expected{};
        for(u32 r=0;r<255;r++){physical[r]=1000+r;expected[r]=r<216?1000+r:2000+r;}
        for(u32 r=216;r<255;r++)local[r-216]=expected[r];
        auto execute=[&](bool after) {
            std::vector<u64> instructions;plan.Emit(instructions,after);
            for(u64 m:instructions){const u32 reg=m&255,offset=(m>>20)&0xffffff;
                CHECK(offset%4==0 && offset<NativeRegisterSpill::bytes);
                if((m&0xfff0000000000000ull)==0xef50000000000000ull)local[offset/4]=physical[reg];
                else physical[reg]=local[offset/4];
            }
        };
        execute(false);CHECK(physical[rewritten.Bits(24,8)]==expected[src]);
        if(enabled && opcode==0xa0a)physical[rewritten.Bits(16,8)]=expected[dst]=0x3f800000;
        execute(true);
        for(u32 r=0;r<255;r++)CHECK(physical[r]==(r<216?expected[r]:1000+r));
        for(u32 r=216;r<255;r++)CHECK(local[r-216]==expected[r]);
        Instruction end{{0x794d,0,0x03800000,0}};
        CHECK(bool(LowerToMaxwell(std::array{original,end},"full",true)));
    }
    // Every low register is live, and all uniform/scratch mirrors have distinct
    // values. Spilling a vector or an aliased scalar op must preserve both.
    for(u32 dst=216;dst<255;dst++) for(u32 src:{0u,4u,215u,216u,239u,248u,254u})
    for(bool enabled:{false,true}) {
        auto original=op(0x221); bits(original,16,8,dst); bits(original,24,8,src); bits(original,32,8,dst);
        auto rewritten=original; NativeRegisterSpill plan; CHECK(plan.Prepare(rewritten));
        std::array<u32,256> physical{},local{},expected{};
        for(u32 r=0;r<255;r++) { physical[r]=1000+r; expected[r]=2000+r; }
        for(u32 r=0;r<216;r++) expected[r]=physical[r];
        for(u32 r=216;r<255;r++) local[r-216]=expected[r];
        const auto execute=[&](bool after) {
            std::vector<u64> instructions; plan.Emit(instructions,after);
            for(u64 m:instructions) {
                const u32 r=m&255,offset=(m>>20)&0xffffff;
                CHECK(offset%4==0 && offset<NativeRegisterSpill::bytes);
                CHECK(((m>>16)&15)==7 && ((m>>8)&255)==255 && ((m>>48)&7)==4);
                if ((m&0xfff0000000000000ull)==0xef50000000000000ull) local[offset/4]=physical[r];
                else physical[r]=local[offset/4];
            }
        };
        execute(false);
        if(enabled) {
            physical[rewritten.Bits(16,8)]=physical[rewritten.Bits(24,8)]+physical[rewritten.Bits(32,8)];
            expected[dst]=expected[src]+expected[dst];
        }
        execute(true);
        for(u32 r=0;r<255;r++) CHECK(physical[r]==1000+r); // includes emulated URs and scratch
        for(u32 r=216;r<255;r++) CHECK(local[r-216]==expected[r]);
    }
    for(u32 width:{1u,2u,4u}) for(u32 dst=216;dst+width<=255;dst+=width) {
        auto load=op(0x981); bits(load,16,8,dst); bits(load,24,8,255); bits(load,32,6,0);
        bits(load,73,3,width==4?6:width==2?5:4);
        NativeRegisterSpill plan; CHECK(plan.Prepare(load));
        CHECK(load.Bits(16,8)%width==dst%width);
        for(u32 n=0;n<width;n++) CHECK(plan.mapped[dst+n]==load.Bits(16,8)+n);
    }
    auto uniform=op(0x882); bits(uniform,16,8,0); uniform.words[1]=19;
    auto high=op(0x802); bits(high,16,8,239); high.words[1]=29; high.words[2]=0xf00;
    auto copy=op(0x202); bits(copy,16,8,8); copy.words[1]=239; copy.words[2]=0xf00;
    auto end=op(0x94d); bits(end,87,4,7);
    const std::vector<Instruction> code{uniform,high,copy,end};
    CHECK(!LowerToMaxwell(code,"full"));
    auto out=LowerToMaxwell(code,"full",true); CHECK(bool(out)); CHECK(out.local_spill_bytes==1024);
    // Calls/local operations cannot alias the private spill area through an
    // unmodelled access. The ordinary lowering still handles them separately.
    for(u32 opcode:{0x387u,0x983u,0x949u}) {
        auto unknown=op(opcode); NativeRegisterSpill plan; CHECK(!plan.Prepare(unknown));
    }
    auto cross=op(0x321); bits(cross,16,8,214); bits(cross,74,2,3);
    NativeRegisterSpill plan; CHECK(!plan.Prepare(cross));
}
static void uniform_shift_registers() {
    const u32 registers[]={0,15,16,21,22,27};
    const u32 values[]={0,1,0x80000000,0xffffffff,0x12345678};
    for (u32 dst:registers) for (u32 src:registers) for (u32 mode=0;mode<5;mode++)
        for (u32 shift:{0u,1u,17u,31u,32u}) {
            auto i=op(0x899); bits(i,16,8,dst); i.words[1]=shift;
            const bool high=mode==1 || mode==3 || mode==4;
            bits(i,24,8,high?63:src);
            i.words[2]=(mode==0?0x08000600:mode==1?0x08010600:mode==2?0x08001600:
                        mode==3?0x08011600:0x08011400)|(high?src:63);
            auto out=lower(i); CHECK(bool(out)); if (!out) continue;
            const u64 m=out.instructions[0];
            CHECK((m&255)==(dst<22?216+dst:218+dst));
            CHECK(((m>>8)&255)==(src<22?216+src:218+src));
            CHECK(((m>>20)&0x7ffff)==shift);
            const bool right=(m&0xfff8000000000000ull)==0x3828000000000000ull;
            const bool signed_right=(m>>48)&1;
            CHECK(right==(mode>=2)); CHECK(signed_right==(mode==4));
            for (u32 value:values) {
                const u32 expected=mode<2?(shift==32?0:value<<shift):
                    mode==4?u32(s32(value)>>(shift<32?shift:31)):(shift==32?0:value>>shift);
                const u32 actual=right?(signed_right?u32(s32(value)>>(shift<32?shift:31)):
                    (shift==32?0:value>>shift)):(shift==32?0:value<<shift);
                CHECK(actual==expected);
            }
        }
    for (u32 bad:{28u,62u,63u}) {
        auto i=op(0x899); bits(i,16,8,bad); bits(i,24,8,1); i.words[2]=0x0800063f;
        CHECK(!lower(i));
    }
}
static void clamped_immediate_funnel() {
    for (u32 wrap:{0u,1u}) for (u32 value:{0u,1u,0xffffffffu,0x80000001u,0x12345678u}) {
        auto i=op(0x419); bits(i,16,8,8); bits(i,24,8,255); i.words[1]=value;
        i.words[2]=0x00010600|(wrap<<11)|4;
        auto out=lower(i); CHECK(bool(out)); if (!out) continue;
        CHECK(out.instructions.size()==3); // materialize immediate, shift, EXIT
        const u64 mov=out.instructions[0], shift=out.instructions[1];
        CHECK(((mov>>20)&0xffffffff)==value); CHECK((mov&255)==250);
        CHECK(((shift>>8)&255)==250 && ((shift>>20)&255)==4 && (shift&255)==8);
        CHECK(((shift>>39)&1)==wrap);
        for (u32 amount:{0u,1u,31u,32u,33u,63u,64u,0xffffffffu}) {
            const u32 n=(shift>>39)&1?amount&31:amount;
            const u32 got=n>=32?0:value<<n;
            // High 32 bits of (value:0 << min(amount,32)), or modulo-32 shift.
            const u32 expected=wrap?value<<(amount&31):(amount>=32?0:value<<amount);
            CHECK(got==expected);
        }
    }
}
static void high_address_subtract() {
    for (u32 dst:{0u,1u,8u}) for (u32 sign:{0u,1u}) for (u32 amount:{0u,1u,17u,30u,31u}) {
        auto i=op(0x211); bits(i,16,8,dst); bits(i,24,8,0); bits(i,32,8,1); bits(i,63,1,1);
        bits(i,64,8,255); bits(i,73,1,sign); bits(i,75,5,amount); bits(i,80,1,1); bits(i,81,3,7);
        auto out=lower(i); CHECK(bool(out)); if (!out) continue;
        for (u32 a:{0u,1u,0x80000000u,0xffffffffu,0x87654321u})
            for (u32 b:{0u,1u,0xffffffffu,0x12345678u}) {
                u32 regs[256]={}; regs[0]=a; regs[1]=b;
                for (u64 m:out.instructions) {
                    u32 d=m&255,ra=(m>>8)&255,rb=(m>>20)&255;
                    const u64 opcode=m&0xfff8000000000000ull;
                    if(opcode==0x3828000000000000ull) {
                        u32 n=(m>>20)&0x7ffff;
                        regs[d]=(m>>48)&1?u32(s32(regs[ra])>>(n<32?n:31)):(n<32?regs[ra]>>n:0);
                    } else if(opcode==0x5c10000000000000ull) {
                        regs[d]=regs[ra]+(((m>>48)&3)==1?0-regs[rb]:regs[rb]);
                    }
                }
                const u64 full=sign?u64(s64(s32(a))):u64(a);
                const u32 expected=u32((full<<amount)>>32)-b;
                CHECK(regs[dst]==expected);
            }
    }
}
static void surface_reduction() {
    for(u32 operation:{0u,6u}) {
    auto i=op(0x59f); bits(i,24,8,4); bits(i,32,8,8); bits(i,40,14,4);
    bits(i,61,3,3); i.words[2]=0x0010e000|(operation<<23);
    auto out=lower(i); CHECK(bool(out));
    if(out) {
        const u64 m=out.instructions[0];
        CHECK((m&0xfff8000000000000ull)==0xeb58000000000000ull);
        CHECK((m&255)==8 && ((m>>8)&255)==4);
        CHECK(((m>>20)&15)==0 && ((m>>24)&7)==operation); // U32 ADD/OR
        CHECK(((m>>33)&7)==3 && ((m>>36)&0x1fff)==4 && ((m>>51)&1));
    }
    bits(i,73,1,1); CHECK(!lower(i)); // other element/reduction modes are not this operation
    }
}
int main() {
    txq(); i2f(); texture_half_order(); extended_compare(); extended_accumulator(); bindless_textures(); wide_immediate_multiply(); array_gather(); high_native_registers(); uniform_shift_registers(); clamped_immediate_funnel(); high_address_subtract(); surface_reduction(); windows();
    std::printf("render regressions: %u checks, %u failures\n", checks, failures);
    return failures?1:0;
}
