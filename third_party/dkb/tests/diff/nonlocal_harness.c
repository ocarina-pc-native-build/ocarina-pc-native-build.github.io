// Authored test support for generated returns-twice callers.
#include "cpu.h"
#include "nonlocal.h"
#include "platform/platform.h"
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#ifdef _WIN32
#include <windows.h>
#define EXPORT __declspec(dllexport)
#else
#include <sys/mman.h>
#define EXPORT
#endif
volatile int g_fnprof;
void fnprof_hit(uint64_t a,uint64_t b,uint64_t d) { abort(); }
void rt_log(const char *fmt,...) { (void)fmt; }
void rt_fatal(const char *fmt,...) { va_list a; va_start(a,fmt); vfprintf(stderr,fmt,a); va_end(a); abort(); }
void kern_backtrace(const Cpu *c) { (void)c; }
int plat_mem_read(uint64_t a,void *out,size_t n) { (void)a; (void)out; (void)n; return 0; }
void plat_mutex_lock(PlatMutex *m) { while(__atomic_exchange_n(&m->p,(void *)1,__ATOMIC_ACQUIRE)) {} }
void plat_mutex_unlock(PlatMutex *m) { __atomic_store_n(&m->p,NULL,__ATOMIC_RELEASE); }
void rt_dispatch(Cpu *c) { if(!rt_nonlocal_try_resume(c)) abort(); }
void rt_brk(Cpu *c,uint32_t imm,uint64_t pc) { abort(); }
void rt_udf(Cpu *c,uint64_t pc) { abort(); }
void f_100000(Cpu *c);

EXPORT void run_case(uint64_t value,uint64_t *out) {
    const uintptr_t addr=UINT64_C(0x7200000000);
    static void *memory;
    if(!memory) {
#ifdef _WIN32
        memory=VirtualAlloc((void *)addr,0x40000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
#else
        memory=mmap((void *)addr,0x40000,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED,-1,0);
#endif
        assert(memory==(void *)addr);
    }
    memset(memory,0,0x40000);
    Cpu c={0};
    c.x[0]=addr; c.x[1]=value; c.x[30]=0x101000; c.sp=addr+0x3f000;
    for(unsigned i=19;i<30;i++) c.x[i]=0x500+i;
    for(unsigned i=8;i<16;i++) c.v[i]=((__uint128_t)0xdeadbeef<<64)|(0x600+i);
    f_100000(&c);
    out[0]=c.x[0]; out[1]=c.sp;
    for(unsigned i=19;i<31;i++) out[2+i-19]=c.x[i];
    for(unsigned i=8;i<16;i++) out[14+i-8]=(uint64_t)c.v[i];
    // Normal return removes every registration, including unwound nested frames.
    c.pc=0x100018; c.sp=addr+0x3f000-32;
    assert(!rt_nonlocal_try_resume(&c));
}

EXPORT void registry_cases(void) {
    static Cpu a,b; static int thread[2];
    memset(&a,0,sizeof a); memset(&b,0,sizeof b);
    thread[1]=3; a.thread=thread;
    RtJumpFrame *outer=rt_nonlocal_enter(&a,100);
    a.sp=200; rt_nonlocal_bind(&a,300,400);
    b.sp=200; b.pc=400; assert(!rt_nonlocal_try_resume(&b));
    a.pc=401; assert(!rt_nonlocal_try_resume(&a));
    a.pc=400; a.sp=201; assert(!rt_nonlocal_try_resume(&a));
    // Reusing one jmp_buf invalidates the preceding binding, even in an outer frame.
    RtJumpFrame *inner=rt_nonlocal_enter(&a,500);
    rt_nonlocal_bind(&a,300,600);
    a.sp=200; assert(!rt_nonlocal_try_resume(&a));
    rt_nonlocal_leave(inner);
    rt_nonlocal_leave(outer);
    RtJumpFrame *owned=rt_nonlocal_enter(&b,700);
    rt_nonlocal_enter(&a,800); rt_nonlocal_bind(&a,900,1000);
    rt_nonlocal_discard(&a);
    a.pc=1000; assert(!rt_nonlocal_try_resume(&a));
    rt_nonlocal_leave(owned);
    RtJumpFrame *target=rt_nonlocal_enter(&a,1100);
    if(!setjmp(target->host)) {
        rt_nonlocal_bind(&a,1200,1300);
        thread[1]=19; a.pc=1300;
        rt_nonlocal_try_resume(&a);
        abort();
    }
    rt_nonlocal_reentered(&a,target);
    assert(thread[1]==3);
    rt_nonlocal_leave(target);
}
