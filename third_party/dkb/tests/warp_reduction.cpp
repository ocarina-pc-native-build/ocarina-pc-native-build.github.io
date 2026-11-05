// Authored active-lane integer reductions; no captured shader instructions.
#include <array>
#include <cstdio>
#include <cstdint>
#include <algorithm>
#include "shader_recompiler/frontend/ampere/lower_to_maxwell.h"
using namespace Shader::Ampere;
static unsigned checks,failures;
#define CHECK(c) do { ++checks; if(!(c)) { ++failures; std::fprintf(stderr,"line %d: %s\n",__LINE__,#c); } } while(0)
static u32 logic(u32 a,u32 b,u32 op) {
    if(op==0)return a&b;
    if(op==1)return a|b;
    if(op==2)return a^b;
    return b;
}
static void run(u32 mode,u32 mask,unsigned seed) {
    Instruction reduce{{0x040373c4,0,mode,0}},exit{{0x0000794d,0,0x03800000,0}};
    const std::array code{reduce,exit};
    auto lowered=LowerToMaxwell(code,"full");
    CHECK(bool(lowered)); if(!lowered)return;
    std::array<std::array<u32,256>,32> regs{};
    std::array<u32,32> inputs{};
    u32 state=seed;
    for(unsigned lane=0;lane<32;lane++) {
        state=state*1664525+1013904223;
        inputs[lane]=regs[lane][4]=seed==0?0x80000000u+lane:seed==1?lane+1:state;
    }
    const unsigned operation=mode>>14;
    const bool sign=(mode&0x200)!=0;
    u32 expected=operation==4?(sign?0x7fffffffu:0xffffffffu):operation==5&&sign?0x80000000u:0;
    for(unsigned l=0;l<32;l++)if(mask>>l&1) {
        if(operation==3)expected+=inputs[l];
        else if(operation==4)expected=sign?u32(std::min(s32(expected),s32(inputs[l]))):std::min(expected,inputs[l]);
        else if(operation==5)expected=sign?u32(std::max(s32(expected),s32(inputs[l]))):std::max(expected,inputs[l]);
    }
    for(u64 ins:lowered.instructions) {
        const u64 op=ins&0xfff8000000000000ull;
        unsigned d=ins&255,a=(ins>>8)&255,b=(ins>>20)&255;
        for(unsigned l=0;l<32;l++)if(mask>>l&1) {
            auto& r=regs[l];r[255]=0;
            if(ins>>56==1)r[d]=u32(ins>>20);
            else if(op==0x50d8000000000000ull)r[d]=mask;
            else if(op==0xef10000000000000ull)r[d]=inputs[(ins>>20)&31];
            else if(op==0x3828000000000000ull)r[d]=r[a]>>((ins>>20)&31);
            else if(ins>>58==1)r[d]=logic((ins>>55&1)?~r[a]:r[a],(ins>>56&1)?~u32(ins>>20):u32(ins>>20),(ins>>53)&3);
            else if(op==0x5c10000000000000ull)r[d]=r[a]+((ins>>48&1)?0-r[b]:r[b]);
            else if(op==0x5c40000000000000ull)r[d]=logic((ins>>39&1)?~r[a]:r[a],(ins>>40&1)?~r[b]:r[b],(ins>>41)&3);
            else if(op==0x5c20000000000000ull)r[d]=((ins>>39)&15)==15?std::max(r[a],r[b]):std::min(r[a],r[b]);
            else if(ins>>52==0xe30) {} // EXIT
            else { CHECK(false); return; }
        }
    }
    for(unsigned l=0;l<32;l++)if(mask>>l&1)CHECK(regs[l][219]==expected);
}
int main() {
    for(u32 mode:{0xc000u,0x10000u,0x10200u,0x14000u,0x14200u})
        for(u32 mask:{1u,0x80000000u,0x12345678u,0x7fu,0xffffu,0xffffffffu})
            for(unsigned seed=0;seed<24;seed++)run(mode,mask,seed);
    Instruction bad{{0x040373c4,0,0xc200,0}},exit{{0x0000794d,0,0x03800000,0}};
    CHECK(!LowerToMaxwell(std::array{bad,exit},"full"));
    // Authored uniform-address global reductions: signedness, predicate and byte offset.
    for (u32 type : {0u,1u}) for (u32 operation=0;operation<8;operation++)
        for (s32 offset : {-0x80000,-4,0,4,0x7ffff}) {
            Instruction red{{0xff00098e,7u|(u32(offset)&0xffffffu)<<8,
                             0x0c10e104u|(type<<9)|(operation<<23),0}};
            auto r=LowerToMaxwell(std::array{red,exit},"full");
            CHECK(bool(r)); if(!r)continue;
            const u64 out=r.instructions.front();
            CHECK((out&0xff)==7); CHECK((out>>8&255)==220);
            CHECK((out>>16&15)==0); CHECK((out>>20&7)==type);
            CHECK((out>>23&7)==operation); CHECK((out>>28&0xfffff)==(u32(offset)&0xfffff));
            CHECK((out>>48&1)==1);
        }
    for (u32 source : {250u,254u}) {
        Instruction red{{0xff00798e,source,0x0c10e304,0}};
        CHECK(!LowerToMaxwell(std::array{red,exit},"full"));
    }
    Instruction zero{{0xff00798e,255,0x0c10e304,0}};
    auto z=LowerToMaxwell(std::array{zero,exit},"full");
    CHECK(bool(z)); if(z)CHECK((z.instructions.front()&255)==255);
    std::printf("warp reduction: %u checks, %u failures\n",checks,failures);
    return failures?1:0;
}
