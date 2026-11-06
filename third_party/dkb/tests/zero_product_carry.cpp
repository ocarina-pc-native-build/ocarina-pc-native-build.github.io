// Authored low-word IMAD.X arithmetic, predication and aliasing regression.
#include <array>
#include <cstdio>
#include "shader_recompiler/frontend/ampere/lower_to_maxwell.h"
using namespace Shader::Ampere;
static unsigned checks, failures;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; if (failures < 10) std::fprintf(stderr,"line %d: %s\n",__LINE__,#c); } } while (0)
static bool enabled(unsigned p, unsigned mask) {
    const bool value=(p&7)==7 || ((mask>>(p&7))&1);
    return value ^ bool(p&8);
}
int main() {
    const Instruction end{{0x794d,0,0x03800000,0}};
    for (unsigned sign : {0u,1u}) for (unsigned dest : {6u,8u})
    for (unsigned guard : {0u,8u,7u}) for (unsigned carry=0;carry<8;carry++) {
        Instruction ins{{0xff007224u|(dest<<16),255,0x000e0406u|(sign<<9)|(carry<<23),0}};
        ins.words[0]=(ins.words[0]&~0xf000u)|(guard<<12);
        auto lowered=LowerToMaxwell(std::array{ins,end},"full");
        CHECK(bool(lowered)); if(!lowered)continue;
        for (u32 value : {0u,1u,0x7fffffffu,0x80000000u,0xfffffffeu,0xffffffffu})
        for (unsigned predicates=0;predicates<128;predicates++) {
            std::array<u32,256> r;
            for (unsigned k=0;k<256;k++)r[k]=0xa5a50000u+k;
            r[6]=value; r[255]=0; const auto original=r;
            for (unsigned k=0;k<lowered.source_instruction_offsets[1];k++) {
                const u64 m=lowered.instructions[k];
                if(!enabled((m>>16)&15,predicates))continue;
                u32 result=0; const u32 a=r[(m>>8)&255],b=r[(m>>20)&255];
                if(m>>56==1)result=u32(m>>20);
                else if((m&0xfff8000000000000ull)==0x5ca0000000000000ull)
                    result=enabled(((m>>39)&7)|(((m>>42)&1)<<3),predicates)?a:b;
                else if((m&0xfff8000000000000ull)==0x5c10000000000000ull)result=a+b;
                else { CHECK(false); break; }
                if((m&255)!=255)r[m&255]=result;
            }
            const u32 expected=enabled(guard,predicates)?value+u32(enabled(carry,predicates)):original[dest];
            CHECK(r[dest]==expected);
            for(unsigned k=0;k<250;k++)if(k!=dest)CHECK(r[k]==original[k]);
        }
    }
    // The additional accepted bit must not admit arbitrary modifiers or products.
    for(unsigned bit : {8u,11u,12u,20u,22u,26u}) {
        Instruction invalid{{0xff067224,255,0x000e0606u|(1u<<bit),0}};
        CHECK(!LowerToMaxwell(std::array{invalid,end},"full"));
    }
    Instruction product{{0x01067224,255,0x000e0606,0}};
    CHECK(!LowerToMaxwell(std::array{product,end},"full"));
    std::printf("zero-product carry: %u checks, %u failures\n",checks,failures);
    return failures?1:0;
}
