#include "host.h"
#include <windows.h>
#include <SDL3/SDL.h>
#include <stdio.h>
#include <string.h>

static _Thread_local uint64_t tls_value;
void *oot_reserve(size_t size) {
    if (!size || size > (size_t)1 << 34) return NULL;
    return VirtualAlloc(NULL, size, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
}
int oot_release(void *memory) { return memory && VirtualFree(memory,0,MEM_RELEASE) != 0; }
uint64_t oot_ticks_ns(void) {
    LARGE_INTEGER t,f;
    if (!QueryPerformanceCounter(&t) || !QueryPerformanceFrequency(&f)) return 0;
    return (uint64_t)(t.QuadPart/f.QuadPart)*1000000000ull +
        (uint64_t)(((__uint128_t)(t.QuadPart%f.QuadPart)*1000000000ull)/f.QuadPart);
}
int oot_unsupported_service(const char *service, uint32_t command, uint64_t pc) {
    fprintf(stderr,"UNIMPLEMENTED service=%s command=%u guest_pc=0x%llx\n",service,command,(unsigned long long)pc);
    return -1;
}
static DWORD WINAPI tls_worker(void *unused) {
    (void)unused;
    if(tls_value != 0) return 1;
    tls_value=99;
    return tls_value==99 ? 0 : 2;
}
int oot_selftest(void) {
    unsigned char *p=oot_reserve(65536);
    if(!p) return 1;
    memset(p,0xa5,65536);
    if(p[0]!=0xa5 || p[65535]!=0xa5) return 2;
    if(!oot_release(p) || oot_reserve(0)) return 3;
    tls_value=42;
    HANDLE thread=CreateThread(NULL,0,tls_worker,NULL,0,NULL);
    if(!thread) return 4;
    DWORD result=99;
    DWORD wait=WaitForSingleObject(thread,5000);
    GetExitCodeThread(thread,&result);
    CloseHandle(thread);
    if(wait!=WAIT_OBJECT_0 || result || tls_value!=42) return 5;
    uint64_t before=oot_ticks_ns(); Sleep(2); uint64_t after=oot_ticks_ns();
    if(!before || after<=before) return 6;
    if(oot_unsupported_service("test:unknown",123,0x7000000000ull)!=-1) return 7;
    puts("PASS host: committed memory, TLS isolation, thread join, monotonic time, explicit unsupported service");
    return 0;
}
int oot_probe_input(void) {
    if(!SDL_Init(SDL_INIT_GAMEPAD)) { fprintf(stderr,"SDL3: %s\n",SDL_GetError()); return 1; }
    int n=0;
    SDL_JoystickID *ids=SDL_GetGamepads(&n);
    if(!ids) { fprintf(stderr,"SDL3 enumeration: %s\n",SDL_GetError()); SDL_Quit(); return 1; }
    printf("SDL3 %d; connected gamepads=%d\n",SDL_GetVersion(),n);
    for(int i=0;i<n;++i) printf("gamepad %u: %s\n",ids[i],SDL_GetGamepadNameForID(ids[i]));
    SDL_free(ids); SDL_Quit();
    return 0;
}
