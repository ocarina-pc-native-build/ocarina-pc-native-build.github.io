// Authored full-rate register reads. No captured game shader bytes.
#include <array>
#include <cstdio>
#include "shader_recompiler/frontend/ampere/lower_to_maxwell.h"
using namespace Shader::Ampere;
int main() {
    unsigned checks=0,failures=0;
    for(unsigned op : {0x919u,0x9c3u}) for(unsigned pred=0;pred<16;pred++) {
        Instruction read{{(4u<<16)|(pred<<12)|op,0,132u<<8,0}};
        Instruction exit{{0x794d,0,0x03800000,0}};
        auto result=LowerToMaxwell(std::array{read,exit},"full");
        checks++; if(!result) { failures++;continue; }
        if(pred==15) { checks++; if(result.instructions.size()!=1)failures++;continue; }
        auto mov=result.instructions[0];
        checks++;
        if((mov&255)!=(op==0x919?4u:220u) || ((mov>>16)&15)!=pred ||
           ((mov>>20)&0xffffffff)!=0x10100)failures++;
        for(unsigned invalid=0;invalid<3;invalid++) {
            auto bad=read;
            if(invalid==0)bad.words[1]=1;
            else if(invalid==1)bad.words[2]|=1;
            else bad.words[2]=133u<<8;
            checks++;if(LowerToMaxwell(std::array{bad,exit},"full"))failures++;
        }
    }
    std::printf("fragment rate: %u checks, %u failures\n",checks,failures);
    return failures?1:0;
}
