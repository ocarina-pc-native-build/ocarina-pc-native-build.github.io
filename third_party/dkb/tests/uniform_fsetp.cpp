// Authored uniform floating comparisons; no captured shader instructions.
#include <array>
#include <cstdio>
#include "shader_recompiler/frontend/ampere/lower_to_maxwell.h"
using namespace Shader::Ampere;
int main() {
    unsigned checks=0,failures=0;
    const Instruction exit{{0x794d,0,0x03800000,0}};
    for(unsigned ur : {0u,21u,22u,27u,63u,28u,62u})
        for(unsigned cmp=0;cmp<16;cmp++) for(unsigned comb=0;comb<4;comb++) {
            Instruction op{{0x04007c0b,ur,(1u<<20)|(cmp<<12)|(comb<<10)|(7u<<23),0}};
            auto r=LowerToMaxwell(std::array{op,exit},"full");
            bool valid=(ur<28||ur==63)&&comb<3;
            ++checks;
            if(bool(r)!=valid) { ++failures; continue; }
            if(!valid)continue;
            unsigned mapped=ur<22?216+ur:ur<28?218+ur:255;
            auto word=r.instructions.front();
            ++checks;
            if((word>>8&255)!=4 || (word>>20&255)!=mapped ||
               (word>>48&15)!=cmp || (word>>45&3)!=comb ||
               (word&7)!=1 || (word>>3&7)!=0)++failures;
        }
    std::printf("uniform FSETP: %u checks, %u failures\n",checks,failures);
    return failures?1:0;
}
