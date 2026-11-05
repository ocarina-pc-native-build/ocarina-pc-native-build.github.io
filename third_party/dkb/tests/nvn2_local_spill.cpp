// SPDX-License-Identifier: GPL-3.0-or-later
// Authored stage controls and instructions; no extracted shader data.
#include <cstdio>
#include "../runtime/nvn2_lower.cpp"

extern "C" void rt_log(const char *, ...) {}
extern "C" uint64_t gfx_shader_nvn2_hash(const uint8_t *control, const uint8_t *code) {
    uint32_t length; std::memcpy(&length, control+0x38, 4);
    uint64_t hash=0xcbf29ce484222325ULL;
    for(unsigned i=0;i<0xd8;i++) hash=(hash^control[i])*0x100000001b3ULL;
    for(unsigned i=0;i<length;i++) hash=(hash^code[i])*0x100000001b3ULL;
    return hash;
}
int main() {
    uint32_t control[0xd8/4]{},code[0x100/4]{};
    control[0x30/4]=sizeof control; control[0x38/4]=0xc0;
    code[0]=1|(4<<5)|(1<<10);
    const uint32_t native[][4]={
        {0x00007882,19,0,0}, {0x00ef7802,29,0xf00,0},
        {0x00087202,239,0xf00,0}, {0x0000794d,0,0x03800000,0}
    };
    std::memcpy(code+0x80/4,native,sizeof native);
    const uint8_t *out_control{},*out_code{};
    unsigned checks=0,failures=0;
    const auto run=[&]() { return nvn2_lower(reinterpret_cast<const uint8_t *>(control),
                                          reinterpret_cast<const uint8_t *>(code),&out_control,&out_code); };
    const auto check=[&](bool ok) { checks++; failures+=!ok; };
    check(run()==1);
    if(out_code) {
        uint32_t local; std::memcpy(&local,out_code+0x34,4);
        check((local&0xffffff)==1024);
    }
    for(unsigned field=1;field<=3;field++) {
        code[field]=64; check(run()==0); code[field]=0;
    }
    code[0]=1|(4<<5)|(5<<10); check(run()==0); // FS has implicit GPR outputs
    code[0]=1|(4<<5)|(1<<10);
    code[0x80/4+8]=0x00007944; check(run()==0); // unsupported call cannot escape a spill epilogue
    std::printf("native local spill adapter: %u checks, %u failures\n",checks,failures);
    return failures?1:0;
}
