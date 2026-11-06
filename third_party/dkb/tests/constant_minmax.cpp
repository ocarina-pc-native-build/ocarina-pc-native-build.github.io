// Immediate encoding boundaries, independent of captured game shaders.
#include <array>
#include <cstdio>
#include "shader_recompiler/frontend/ampere/lower_to_maxwell.h"
using namespace Shader::Ampere;
int main() {
    unsigned checks=0,failures=0;
    for(u32 value : {0u,1u,0x7ffffu,0x80000u,0xfff7ffffu,0xfff80000u,0xfffffffeu,0xffffffffu})
        for(u32 sign : {0u,1u}) for(u32 maximum : {0u,1u}) {
            Instruction op{{0x04087817,value,0x03800000|(sign<<9)|(maximum<<26),0}};
            Instruction exit{{0x794d,0,0x03800000,0}};
            auto r=LowerToMaxwell(std::array{op,exit},"full");
            const bool fits=static_cast<s32>(value)>=-524288 && static_cast<s32>(value)<=524287;
            checks++;if(bool(r)!=fits){failures++;continue;}
            if(!fits)continue;
            auto m=r.instructions[0];
            u32 decoded=(m>>20)&0x7ffff;if((m>>56)&1)decoded|=0xfff80000;
            checks++;if(decoded!=value || (m>>48&1)!=sign || (m>>42&1)!=maximum)failures++;
        }
    std::printf("constant minmax: %u checks, %u failures\n",checks,failures);
    return failures?1:0;
}
