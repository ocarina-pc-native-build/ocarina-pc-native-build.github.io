// SPDX-License-Identifier: MIT
// Host continuation frames for generated callers of the guest setjmp ABI.
#pragma once
#include <setjmp.h>
#include "cpu.h"
typedef struct RtJumpBinding RtJumpBinding;
typedef struct RtJumpFrame {
    jmp_buf host;
    Cpu *cpu;
    struct RtJumpFrame *next;
    RtJumpBinding *bindings;
    uint64_t entry;
    int resume_depth;
} RtJumpFrame;
RtJumpFrame *rt_nonlocal_enter(Cpu *cpu,uint64_t entry);
void rt_nonlocal_bind(Cpu *cpu,uint64_t buffer,uint64_t continuation);
void rt_nonlocal_reentered(Cpu *cpu,RtJumpFrame *frame);
void rt_nonlocal_leave(RtJumpFrame *frame);
void rt_nonlocal_discard(Cpu *cpu);
int rt_nonlocal_try_resume(Cpu *cpu);
void rt_nonlocal_diagnose(const Cpu *cpu,const char *phase);
