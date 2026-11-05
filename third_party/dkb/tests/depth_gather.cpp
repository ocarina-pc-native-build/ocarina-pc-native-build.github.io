// Authored depth gather with split outputs, including input/output overlap.
#include <array>
#include <cstdio>
#include "shader_recompiler/frontend/ampere/lower_to_maxwell.h"
using namespace Shader::Ampere;
int main() {
    unsigned checks=0,failures=0;
    for(unsigned a : {0u,8u,20u}) for(unsigned b : {2u,8u,20u}) for(unsigned pred : {0u,7u,8u}) {
        Instruction op{{(a<<24)|(8u<<16)|(pred<<12)|0xb63,0x30000800|b,0x001e4f14,0}};
        Instruction exit{{0x794d,0,0x03800000,0}};
        auto r=LowerToMaxwell(std::array{op,exit},"full");
        checks++;if(!r){failures++;continue;}
        for(unsigned i=0;i<2;i++) {
            auto m=r.instructions[i];checks++;
            if((m&255)!=250+i || (m>>20&255)!=a+i || (m>>16&15)!=pred)failures++;
        }
        auto tex=r.instructions[2];checks++;
        if((tex>>50&1)!=1 || (tex>>20&255)!=b || (tex>>28&7)!=2 || (tex>>31&15)!=15)failures++;
        for(unsigned i=0;i<4;i++) { auto m=r.instructions[3+i];checks++;
            if((m&255)!=(i<2?8+i:20+i-2) || (m>>20&255)!=250+i)failures++;
        }
        auto bad=op;bad.words[2]|=1u<<12;checks++;
        if(LowerToMaxwell(std::array{bad,exit},"full"))failures++;
    }
    std::printf("depth gather: %u checks, %u failures\n",checks,failures);
    return failures?1:0;
}
