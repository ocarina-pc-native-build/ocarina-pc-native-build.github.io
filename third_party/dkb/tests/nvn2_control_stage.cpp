// No executable is produced: the compiler evaluates these checks with -fsyntax-only.
#include <array>
#include "nvn2_control.h"

constexpr auto control(unsigned stage, unsigned bytes = 0xd8) {
    std::array<uint8_t, 0xe0> c{};
    c[0] = 0x34; c[1] = 0x12; c[2] = 0x76; c[3] = 0x98;
    c[4] = 0xc9; c[0x30] = (uint8_t)bytes; c[0x31] = (uint8_t)(bytes >> 8);
    c[0x56] = (uint8_t)stage;
    return c;
}

constexpr bool all_stages() {
    for (unsigned i = 0; i < 8; i++) {
        auto c = control(i);
        if (nvn2_control_stage(c.data(), c.size()) != i) return false;
    }
    return true;
}
static_assert(all_stages());
static_assert(nvn2_control_stage(nullptr, 0x10000) == NVN2_STAGE_INVALID);
static_assert(nvn2_control_stage(control(7).data(), 0x56) == NVN2_STAGE_INVALID);
static_assert(nvn2_control_stage(control(7).data(), 0xd7) == NVN2_STAGE_INVALID);
static_assert(nvn2_control_stage(control(7).data(), 0xd8) == NVN2_STAGE_MESH);
static_assert(nvn2_control_stage(control(6).data(), 0xd8) == NVN2_STAGE_TASK);
static_assert(nvn2_control_stage(control(7, 0).data(), 0xd8) == NVN2_STAGE_MESH);
static_assert(nvn2_control_stage(control(7, 0).data(), 0xd7) == NVN2_STAGE_INVALID);
static_assert(nvn2_control_stage(control(7, 0x56).data(), 0xe0) == NVN2_STAGE_INVALID);
static_assert(nvn2_control_stage(control(7, 0xe1).data(), 0xe0) == NVN2_STAGE_INVALID);
static_assert(nvn2_control_stage(control(8).data(), 0xe0) == NVN2_STAGE_INVALID);
static_assert([] { auto c=control(7); c[4]=0; return nvn2_control_stage(c.data(),c.size())==NVN2_STAGE_INVALID; }());
static_assert([] { auto c=control(7); c[3]=0; return nvn2_control_stage(c.data(),c.size())==NVN2_STAGE_INVALID; }());
