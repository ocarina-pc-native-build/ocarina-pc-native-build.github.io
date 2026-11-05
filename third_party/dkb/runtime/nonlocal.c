// SPDX-License-Identifier: MIT
#include "nonlocal.h"
#include "host.h"
#include "kernel.h"
#include "platform/platform.h"
#include <stdlib.h>
#ifdef _WIN32
#include <windows.h>
#endif

struct RtJumpBinding {
    RtJumpBinding *next;
    uint64_t buffer,pc,sp;
    int host_depth;
};
static PlatMutex jump_lock=PLAT_MUTEX_INIT;
static RtJumpFrame *frames;

void rt_nonlocal_diagnose(const Cpu *c,const char *phase) {
    rt_log("nonlocal %s: Cpu %p thread %p target-PC %#llx LR %#llx FP %#llx SP %#llx x0 %#llx x1 %#llx",
        phase,(void *)c,c->thread,(unsigned long long)c->pc,(unsigned long long)c->x[30],
        (unsigned long long)c->x[29],(unsigned long long)c->sp,
        (unsigned long long)c->x[0],(unsigned long long)c->x[1]);
    for(unsigned i=0;i<32;i+=4)
        rt_log("nonlocal registers x%u..x%u: %016llx %016llx %016llx %016llx",i,i+3,
            (unsigned long long)c->x[i],(unsigned long long)c->x[i+1],
            (unsigned long long)c->x[i+2],(unsigned long long)c->x[i+3]);
    uint64_t stack[16];
    if(plat_mem_read(c->sp,stack,sizeof stack))
        for(unsigned i=0;i<16;i+=4)
            rt_log("nonlocal stack +%#x: %016llx %016llx %016llx %016llx",i*8,
                (unsigned long long)stack[i],(unsigned long long)stack[i+1],
                (unsigned long long)stack[i+2],(unsigned long long)stack[i+3]);
    kern_backtrace(c);
#ifdef _WIN32
    void *trace[16]; unsigned n=CaptureStackBackTrace(0,16,trace,NULL);
    uintptr_t base=(uintptr_t)GetModuleHandleW(NULL);
    for(unsigned i=0;i<n;i++)
        rt_log("nonlocal host frame %u: %p (exe-relative %#llx)",i,trace[i],
            (unsigned long long)((uintptr_t)trace[i]-base));
#endif
}

static int tracing(void) { const char *s=getenv("OOT_NONLOCAL_TRACE"); return s && *s && *s!='0'; }
static void free_frame(RtJumpFrame *f) {
    while(f->bindings) { RtJumpBinding *b=f->bindings; f->bindings=b->next; free(b); }
    free(f);
}

RtJumpFrame *rt_nonlocal_enter(Cpu *c,uint64_t entry) {
    RtJumpFrame *f=calloc(1,sizeof *f);
    if(!f) rt_fatal("nonlocal: frame allocation");
    f->cpu=c; f->entry=entry;
    plat_mutex_lock(&jump_lock); f->next=frames; frames=f; plat_mutex_unlock(&jump_lock);
    return f;
}

void rt_nonlocal_bind(Cpu *c,uint64_t buffer,uint64_t pc) {
    plat_mutex_lock(&jump_lock);
    RtJumpFrame *owner=NULL;
    for(RtJumpFrame *f=frames;f;f=f->next) if(f->cpu==c) {
        if(!owner) owner=f;
        // Reusing a guest jmp_buf supersedes its preceding context.
        for(RtJumpBinding **p=&f->bindings;*p;) {
            if((*p)->buffer==buffer) { RtJumpBinding *b=*p; *p=b->next; free(b); }
            else p=&(*p)->next;
        }
    }
    if(!owner) { plat_mutex_unlock(&jump_lock); rt_fatal("nonlocal: setjmp without a generated caller frame"); }
    RtJumpBinding *b=malloc(sizeof *b);
    if(!b) { plat_mutex_unlock(&jump_lock); rt_fatal("nonlocal: binding allocation"); }
    *b=(RtJumpBinding){owner->bindings,buffer,pc,c->sp,c->thread?*kern_host_depth(c->thread):0};
    owner->bindings=b;
    plat_mutex_unlock(&jump_lock);
    static unsigned traces;
    if(tracing() && __atomic_fetch_add(&traces,1,__ATOMIC_RELAXED)<32)
        rt_log("nonlocal bind: Cpu %p thread %p function %#llx buffer %#llx continuation %#llx SP %#llx LR %#llx",
            (void *)c,c->thread,(unsigned long long)owner->entry,(unsigned long long)buffer,
            (unsigned long long)pc,(unsigned long long)c->sp,(unsigned long long)c->x[30]);
}

int rt_nonlocal_try_resume(Cpu *c) {
    plat_mutex_lock(&jump_lock);
    RtJumpFrame *target=NULL;
    for(RtJumpFrame *f=frames;f && !target;f=f->next) if(f->cpu==c)
        for(RtJumpBinding *b=f->bindings;b;b=b->next)
            if(b->pc==c->pc && b->sp==c->sp) { target=f; f->resume_depth=b->host_depth; break; }
    if(!target) { plat_mutex_unlock(&jump_lock); return 0; }
    // Only this Cpu's younger frames are unwound; other threads/fibers retain theirs.
    for(RtJumpFrame **p=&frames;*p && *p!=target;) {
        RtJumpFrame *f=*p;
        if(f->cpu==c) { *p=f->next; free_frame(f); } else p=&f->next;
    }
    plat_mutex_unlock(&jump_lock);
    static unsigned traces;
    if(tracing() && __atomic_fetch_add(&traces,1,__ATOMIC_RELAXED)<16)
        rt_nonlocal_diagnose(c,"validated guest continuation");
    // Guest SDK code has already restored registers, authenticated its saved
    // context, and normalized longjmp(0) to 1. Leave that Cpu state intact.
    longjmp(target->host,1);
}

void rt_nonlocal_reentered(Cpu *c,RtJumpFrame *f) {
    if(c!=f->cpu) rt_fatal("nonlocal: wrong Cpu owner");
    if(c->thread) __atomic_store_n(kern_host_depth(c->thread),f->resume_depth,__ATOMIC_RELAXED);
    rt_fpcr_sync(c);
}

void rt_nonlocal_leave(RtJumpFrame *f) {
    plat_mutex_lock(&jump_lock);
    RtJumpFrame **p=&frames;
    while(*p && *p!=f) p=&(*p)->next;
    if(!*p) { plat_mutex_unlock(&jump_lock); rt_fatal("nonlocal: returning frame not registered"); }
    *p=f->next; plat_mutex_unlock(&jump_lock); free_frame(f);
}

void rt_nonlocal_discard(Cpu *c) {
    plat_mutex_lock(&jump_lock);
    for(RtJumpFrame **p=&frames;*p;) {
        RtJumpFrame *f=*p;
        if(f->cpu==c) { *p=f->next; free_frame(f); } else p=&f->next;
    }
    plat_mutex_unlock(&jump_lock);
}
