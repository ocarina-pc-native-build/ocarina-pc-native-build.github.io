// Authored texture masks and register layouts; no captured game instructions.
#include <array>
#include <bit>
#include <cstdio>
#include "shader_recompiler/frontend/ampere/lower_to_maxwell.h"
using namespace Shader::Ampere;
int main() {
    unsigned checks=0,failures=0;
    const Instruction exit{{0x794d,0,0x03800000,0}};
    for(unsigned dim : {1u,5u}) for(unsigned mask=0;mask<16;mask++)
        for(unsigned dest : {8u,9u,246u,247u,248u})
        for(unsigned high : {10u,20u,21u,246u,247u,248u,255u}) {
            unsigned n=std::popcount(mask);
            Instruction op{{(dest<<16)|0x7b6c,(dim<<29)|0x804,0x001e0000|(mask<<8)|high,0}};
            auto r=LowerToMaxwell(std::array{op,exit},"full");
            // The non-spilling entry point reserves R246 upward before decoding TXD.
            bool valid=n && dest<246 && (n<2 || !(dest&1)) &&
                (n<=2 ? high==255 : high==255 || (high<246 && (n<4 || !(high&1))));
            checks++;
            if(bool(r)!=valid) { failures++; continue; }
            if(!valid)continue;
            bool direct=n<=2 || high==dest+2;
            auto tex=r.instructions.front();
            checks++;
            if((tex&255)!=(direct?dest:248) || (tex>>31&15)!=mask ||
               (tex>>28&7)!=(dim==5?3u:2u))failures++;
            if(!direct) for(unsigned i=0;i<n;i++) {
                if(i>=2 && high==255)break;
                auto mov=r.instructions[1+i];
                checks++;
                if((mov&255)!=(i<2?dest+i:high+i-2) || (mov>>20&255)!=248+i)failures++;
            }
        }
    std::printf("gradient texture: %u checks, %u failures\n",checks,failures);
    return failures?1:0;
}
