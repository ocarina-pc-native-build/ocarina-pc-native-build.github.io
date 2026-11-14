/* Bounded flight recorder. No allocation or file I/O on the rendering/IO threads.
   One low-priority writer samples once/second; 30 samples precede an incident,
   10 follow it. Idle history is retained every five seconds. Windows first. */
#include "ocr_diagnostics.h"
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>
typedef struct HosThread HosThread;
extern HosThread *hos_self(void);
extern const char *hos_thread_name(HosThread *thread);
extern void hos_log(const char *fmt, ...);

#define DIAG_THREADS 256
#define DIAG_HISTORY 30
#define DIAG_LINE 4096
#define DIAG_LIMIT (8u * 1024u * 1024u)
static SRWLOCK frame_lock = SRWLOCK_INIT, event_lock = SRWLOCK_INIT;
static _Atomic int enabled, stopping, marker, hitch, dropped, events_dropped, untracked_phase_threads;
static _Atomic int64_t last_frame_ns;
static int64_t frequency, origin;
static HANDLE worker, stop_event;
static FILE *output;
static wchar_t output_path[1024], previous_path[1100];
static unsigned segment;
static size_t written;
static int capped;
static char history[DIAG_HISTORY][DIAG_LINE];
static unsigned history_at, history_count;
static char events[32][512];
static unsigned event_count;
static OcrDiagFrame sum;
static double worst;
static unsigned frames, over50, over100;
static _Atomic uint64_t stage_ns[OCR_DIAG_STAGES], stage_bytes[OCR_DIAG_STAGES], stage_calls[OCR_DIAG_STAGES];
typedef struct DiagThread {
    _Atomic int claimed, phase;
    _Atomic int64_t since;
    DWORD tid;
    char name[48];
} DiagThread;
static DiagThread threads[DIAG_THREADS];
static __thread int own_slot = -1;
static int64_t now_ns(void) {
    LARGE_INTEGER q;
    QueryPerformanceCounter(&q);
    return frequency ? (int64_t)((double)q.QuadPart * (1e9 / frequency)) : 0;
}
static double since_ms(int64_t now) { return (now - origin) / 1e6; }
static void safe_text(char *out, size_t cap, const char *in) {
    size_t n = 0;
    while (in && *in && n+1 < cap) {
        unsigned char c = (unsigned char)*in;
        if (c < 128) {
            out[n++] = (c >= 32 && c != 127 && c != '"' && c != '\\') ? c : '_';
            ++in;continue;
        }
        // Preserve complete UTF-8 thread names, including the game's Japanese names.
        int len=c>=0xc2 && c<=0xdf?2:c>=0xe0 && c<=0xef?3:c>=0xf0 && c<=0xf4?4:0;
        unsigned code=len?c&((1u<<(7-len))-1):0;
        int valid=len>0;
        for(int j=1;j<len;++j) {
            unsigned char next=(unsigned char)in[j];
            if((next&0xc0)!=0x80) {valid=0;break;}
            code=(code<<6)|(next&0x3f);
        }
        if(!valid || code<(len==2?0x80:len==3?0x800:0x10000) || code>0x10ffff || (code>=0xd800 && code<=0xdfff)) {
            out[n++]='_';++in;continue;
        }
        if(n+len>=cap)break;
        memcpy(out+n,in,len);n+=len;in+=len;
    }
    out[n] = 0;
}
static void clock_anchor(void);
static void write_line(const char *line) {
    if (!output || capped) return;
    size_t n = strlen(line);
    if (written + n + 1 > DIAG_LIMIT - 128) {
        fputs("{\"schema\":1,\"type\":\"limit\",\"reason\":\"8 MiB segment rotated; only the two latest segments are retained\"}\n", output);
        fclose(output); output=NULL;
        if (!MoveFileExW(output_path,previous_path,MOVEFILE_REPLACE_EXISTING) || !(output=_wfopen(output_path,L"wb"))) {
            capped=1;return;
        }
        written=0;
        char rotation[240];
        snprintf(rotation,sizeof rotation,"{\"schema\":1,\"type\":\"continuation\",\"segment\":%u,\"t_ms\":%.3f,\"note\":\"Previous segment in .previous.jsonl; older segments may have been discarded\"}",++segment,since_ms(now_ns()));
        write_line(rotation);
        clock_anchor();
    }
    if (fwrite(line, 1, n, output) != n || fputc('\n', output) == EOF) { capped = 1; return; }
    written += n+1;
}
static void clock_anchor(void) {
    SYSTEMTIME utc;GetSystemTime(&utc);char anchor[256];
    snprintf(anchor,sizeof anchor,"{\"schema\":1,\"type\":\"clock_anchor\",\"t_ms\":%.3f,\"utc\":\"%04u-%02u-%02uT%02u:%02u:%02u.%03uZ\"}",since_ms(now_ns()),utc.wYear,utc.wMonth,utc.wDay,utc.wHour,utc.wMinute,utc.wSecond,utc.wMilliseconds);
    write_line(anchor);
}
void ocr_diag_event(const char *kind, const char *detail) {
    if (!atomic_load_explicit(&enabled, memory_order_relaxed)) return;
    if (kind && !strcmp(kind, "user_marker")) atomic_store(&marker, 1);
    if (!TryAcquireSRWLockExclusive(&event_lock)) { atomic_fetch_add(&events_dropped, 1); return; }
    if (event_count < 32) {
        char k[40], d[360]; safe_text(k, sizeof k, kind); safe_text(d, sizeof d, detail);
        snprintf(events[event_count++], 512, "{\"schema\":1,\"type\":\"event\",\"t_ms\":%.3f,\"kind\":\"%s\",\"detail\":\"%s\"}", since_ms(now_ns()), k, d);
    } else atomic_fetch_add(&events_dropped, 1);
    ReleaseSRWLockExclusive(&event_lock);
}
void ocr_diag_mark(void) {
    if (!atomic_load(&enabled)) return;
    atomic_store(&marker, 1);
    ocr_diag_event("user_marker", "Player marked a problem (Ctrl+F8). Add room/boss/song details when exporting.");
}
int ocr_diag_enabled(void) { return atomic_load_explicit(&enabled, memory_order_relaxed); }
void ocr_diag_frame(const OcrDiagFrame *s) {
    if (!atomic_load_explicit(&enabled, memory_order_relaxed) || !s) return;
    atomic_store_explicit(&last_frame_ns, now_ns(), memory_order_relaxed);
    if (s->frame_ms >= 100) atomic_store(&hitch, 1);
    if (!TryAcquireSRWLockExclusive(&frame_lock)) { atomic_fetch_add(&dropped, 1); return; }
    ++frames; over50 += s->frame_ms > 50; over100 += s->frame_ms > 100;
    if (s->frame_ms > worst) worst = s->frame_ms;
#define ADD(f) sum.f += s->f
    ADD(frame_ms); ADD(renderer_ms); ADD(gpu_ms); ADD(pipeline_ms); ADD(program_ms); ADD(upload_ms);
    ADD(memory_sync_ms); ADD(slot_wait_ms); ADD(readback_ms); ADD(texture_frame_ms); ADD(translate_ms); ADD(pipeline_wait_ms);
    ADD(draws); ADD(upload_bytes); ADD(new_pipelines); ADD(not_ready);
#undef ADD
    sum.menu = s->menu; sum.frame_generation = s->frame_generation;
    sum.vram_used = s->vram_used; sum.vram_budget = s->vram_budget; sum.vram_known = s->vram_known;
    ReleaseSRWLockExclusive(&frame_lock);
}
OcrDiagSpan ocr_diag_begin(int kind) {
    OcrDiagSpan span = {.slot=-1, .kind=kind};
    if (!atomic_load_explicit(&enabled, memory_order_relaxed) || kind < 0 || kind >= OCR_DIAG_STAGES) return span;
    span.start = now_ns();
    if (own_slot == -1) {
        own_slot=-2; // Exhausted: do not rescan all slots on every future file read/wait.
        for (int i=0; i<DIAG_THREADS; ++i) {
            int empty=0;
            if (atomic_compare_exchange_strong(&threads[i].claimed, &empty, 1)) {
                own_slot=i; threads[i].tid=GetCurrentThreadId();
                HosThread *t=hos_self();
                safe_text(threads[i].name, sizeof threads[i].name, t ? hos_thread_name(t) : "host");
                atomic_store(&threads[i].phase, -1);
                atomic_store_explicit(&threads[i].claimed, 2, memory_order_release); break;
            }
        }
        if(own_slot==-2) atomic_fetch_add(&untracked_phase_threads,1);
    }
    span.slot=own_slot;
    if (span.slot >= 0) {
        DiagThread *t=&threads[span.slot];
        span.previous=atomic_load(&t->phase); span.previous_start=atomic_load(&t->since);
        atomic_store(&t->since, span.start); atomic_store(&t->phase, kind);
    }
    return span;
}
void ocr_diag_end(OcrDiagSpan s, uint64_t bytes) {
    if (!s.start) return;
    int64_t duration=now_ns()-s.start;
    atomic_fetch_add_explicit(&stage_ns[s.kind], duration > 0 ? duration : 0, memory_order_relaxed);
    atomic_fetch_add_explicit(&stage_bytes[s.kind], bytes, memory_order_relaxed);
    atomic_fetch_add_explicit(&stage_calls[s.kind], 1, memory_order_relaxed);
    if (s.slot >= 0) {
        atomic_store(&threads[s.slot].since, s.previous_start);
        atomic_store(&threads[s.slot].phase, s.previous);
    }
}
static uint64_t filetime_value(FILETIME v) { return (uint64_t)v.dwLowDateTime | (uint64_t)v.dwHighDateTime << 32; }
static void active_threads(int64_t now) {
    static const char *names[]={"file_read", "native_zstd", "guest_wait"};
    for (int i=0,n=0; i<DIAG_THREADS && n<48; ++i) {
        if (atomic_load_explicit(&threads[i].claimed, memory_order_acquire) != 2) continue;
        int phase=atomic_load(&threads[i].phase); int64_t start=atomic_load(&threads[i].since);
        if (phase < 0 || phase >= OCR_DIAG_STAGES || start <= 0 || now-start < 50000000) continue;
        char line[320];
        snprintf(line,sizeof line,"{\"schema\":1,\"type\":\"thread_phase\",\"t_ms\":%.3f,\"tid\":%lu,\"name\":\"%s\",\"phase\":\"%s\",\"elapsed_ms\":%.3f}",
                 since_ms(now),(unsigned long)threads[i].tid,threads[i].name,names[phase],(now-start)/1e6);
        write_line(line); ++n;
    }
}
static DWORD WINAPI record_thread(void *unused) {
    (void)unused;
    SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_BELOW_NORMAL);
    int64_t previous=now_ns(), active_until=0, last_incident=0, last_stall=0;
    uint64_t previous_cpu=0; unsigned seq=0;
    double previous_writer_work_ms=0;
    OcrDiagCpuThread previous_threads[128]; int previous_count=0;
    while (WaitForSingleObject(stop_event, 1000)==WAIT_TIMEOUT) {
        int64_t work_start=now_ns(), now=work_start;
        double interval=(now-previous)/1e6; previous=now;
        OcrDiagFrame s; unsigned n, h50, h100; double max_ms;
        AcquireSRWLockExclusive(&frame_lock);
        s=sum; n=frames; max_ms=worst; h50=over50; h100=over100;
        memset(&sum,0,sizeof sum); frames=over50=over100=0; worst=0;
        ReleaseSRWLockExclusive(&frame_lock);
        MEMORYSTATUSEX mem={.dwLength=sizeof mem}; int mem_ok=GlobalMemoryStatusEx(&mem);
        PROCESS_MEMORY_COUNTERS_EX pm={.cb=sizeof pm};
        int pm_ok=GetProcessMemoryInfo(GetCurrentProcess(),(PROCESS_MEMORY_COUNTERS*)&pm,sizeof pm);
        PERFORMANCE_INFORMATION pi={.cb=sizeof pi}; int pi_ok=GetPerformanceInfo(&pi,sizeof pi);
        FILETIME created,exit,kernel,user; double cpu_ms=-1;
        if (GetProcessTimes(GetCurrentProcess(),&created,&exit,&kernel,&user)) {
            uint64_t cpu=filetime_value(kernel)+filetime_value(user);
            if (previous_cpu) cpu_ms=(cpu-previous_cpu)/10000.0;
            previous_cpu=cpu;
        }
        OcrDiagCpuThread current_threads[128]; double thread_ms[128];
        int thread_count=ocr_diag_cpu_threads(current_threads,128);
        for(int i=0;i<thread_count;++i) {
            thread_ms[i]=-1;
            for(int j=0;j<previous_count;++j) if(current_threads[i].tid==previous_threads[j].tid) {
                if(current_threads[i].cpu_100ns>=previous_threads[j].cpu_100ns)
                    thread_ms[i]=(current_threads[i].cpu_100ns-previous_threads[j].cpu_100ns)/10000.0;
                break;
            }
        }
        char cpu_threads[1024]="["; size_t at=1;
        for(int n=0;n<8;++n) {
            int best=-1;
            for(int i=0;i<thread_count;++i) if(thread_ms[i]>=0 && (best<0 || thread_ms[i]>thread_ms[best])) best=i;
            if(best<0) break;
            char name[48];safe_text(name,sizeof name,current_threads[best].name);
            int added=snprintf(cpu_threads+at,sizeof cpu_threads-at,"%s{\"tid\":%u,\"name\":\"%s\",\"cpu_ms\":%.3f}",n?",":"",current_threads[best].tid,name,thread_ms[best]);
            if(added<0 || (size_t)added>=sizeof cpu_threads-at-2) break;
            at+=added;thread_ms[best]=-1;
        }
        cpu_threads[at++]=']';cpu_threads[at]=0;
        memcpy(previous_threads,current_threads,sizeof current_threads[0]*thread_count);previous_count=thread_count;
        OcrDiagContext context={0};int context_known=ocr_diag_context(&context);
        char map[80];safe_text(map,sizeof map,context.map);
        uint64_t times[OCR_DIAG_STAGES], bytes[OCR_DIAG_STAGES], calls[OCR_DIAG_STAGES];
        for(int i=0;i<OCR_DIAG_STAGES;++i) {
            times[i]=atomic_exchange(&stage_ns[i],0); bytes[i]=atomic_exchange(&stage_bytes[i],0); calls[i]=atomic_exchange(&stage_calls[i],0);
        }
        char line[DIAG_LINE];
        int64_t last=atomic_load(&last_frame_ns);
        double gap=last ? (now-last)/1e6 : -1;
        snprintf(line,sizeof line,
            "{\"schema\":1,\"type\":\"sample\",\"seq\":%u,\"t_ms\":%.3f,\"interval_ms\":%.3f,\"frames\":%u,\"frame_sum_ms\":%.3f,\"worst_ms\":%.3f,\"over50\":%u,\"over100\":%u,"
            "\"renderer_ms\":%.3f,\"gpu_ms\":%.3f,\"pipeline_ms\":%.3f,\"program_ms\":%.3f,\"upload_ms\":%.3f,\"memory_sync_ms\":%.3f,\"slot_wait_ms\":%.3f,\"readback_ms\":%.3f,\"texture_frame_ms\":%.3f,\"translate_ms\":%.3f,\"pipeline_wait_ms\":%.3f,"
            "\"draws\":%llu,\"upload_bytes\":%llu,\"new_pipelines\":%llu,\"not_ready\":%llu,\"menu\":%d,\"fg\":%d,\"vram_known\":%d,\"vram_used\":%llu,\"vram_budget\":%llu,"
            "\"memory_known\":%d,\"available_ram\":%llu,\"process_memory_known\":%d,\"working_set\":%llu,\"private_commit\":%llu,\"system_commit_known\":%d,\"system_commit\":%llu,\"system_commit_limit\":%llu,\"process_cpu_ms\":%.3f,"
            "\"read_ms\":%.3f,\"read_bytes\":%llu,\"read_calls\":%llu,\"native_zstd_ms\":%.3f,\"decompressed_bytes\":%llu,\"guest_wait_ms\":%.3f,\"no_frame_ms\":%.3f,\"dropped_frames\":%d,\"dropped_events\":%d,\"untracked_phase_threads\":%d,\"sample_work_ms\":%.3f,\"previous_writer_work_ms\":%.3f,\"thread_cpu\":%s,\"context_known\":%d,\"map\":\"%s\",\"context_age_ms\":%.3f,\"event_active\":%d,\"loading\":%d,\"child\":%d}",
            ++seq,since_ms(now),interval,n,s.frame_ms,max_ms,h50,h100,s.renderer_ms,s.gpu_ms,s.pipeline_ms,s.program_ms,s.upload_ms,s.memory_sync_ms,s.slot_wait_ms,s.readback_ms,s.texture_frame_ms,s.translate_ms,s.pipeline_wait_ms,
            (unsigned long long)s.draws,(unsigned long long)s.upload_bytes,(unsigned long long)s.new_pipelines,(unsigned long long)s.not_ready,s.menu,s.frame_generation,s.vram_known,(unsigned long long)s.vram_used,(unsigned long long)s.vram_budget,
            mem_ok,(unsigned long long)mem.ullAvailPhys,pm_ok,(unsigned long long)pm.WorkingSetSize,(unsigned long long)pm.PrivateUsage,pi_ok,(unsigned long long)pi.CommitTotal*pi.PageSize,(unsigned long long)pi.CommitLimit*pi.PageSize,cpu_ms,
            times[0]/1e6,(unsigned long long)bytes[0],(unsigned long long)calls[0],times[1]/1e6,(unsigned long long)bytes[1],times[2]/1e6,gap,atomic_load(&dropped),atomic_load(&events_dropped),atomic_load(&untracked_phase_threads),(now_ns()-work_start)/1e6,previous_writer_work_ms,cpu_threads,context_known,map,context.age_ms,context.event,context.loading,context.child);
        int marked=atomic_exchange(&marker,0), hit=atomic_exchange(&hitch,0);
        int startup_wait=!last && now-origin>=30000000000LL;
        int stalled=(gap>=5000 || startup_wait) && (!last_stall || now-last_stall>=10000000000LL);
        if(stalled) last_stall=now;
        if(marked || stalled || (hit && (!last_incident || now-last_incident>=30000000000LL))) {
            char event[240];
            snprintf(event,sizeof event,"{\"schema\":1,\"type\":\"incident\",\"t_ms\":%.3f,\"reason\":\"%s\",\"note\":\"Observation; not proof of a fault or cause\"}",since_ms(now),marked?"user_marker":startup_wait?"startup_without_frames":stalled?"no_frame_progress":"frame_over_100ms");
            write_line(event);
            if(now>active_until) for(unsigned j=0;j<history_count;++j) write_line(history[(history_at+DIAG_HISTORY-history_count+j)%DIAG_HISTORY]);
            active_until=now+10000000000LL; last_incident=now; active_threads(now);
        }
        if(now<=active_until || seq%5==0) write_line(line);
        memcpy(history[history_at],line,strlen(line)+1); history_at=(history_at+1)%DIAG_HISTORY;
        if(history_count<DIAG_HISTORY) ++history_count;
        char pending[32][512]; unsigned count;
        AcquireSRWLockExclusive(&event_lock); count=event_count; memcpy(pending,events,count*512); event_count=0; ReleaseSRWLockExclusive(&event_lock);
        for(unsigned j=0;j<count;++j) write_line(pending[j]);
        if(output && (now<=active_until || count || seq%5==0)) fflush(output);
        previous_writer_work_ms=(now_ns()-work_start)/1e6;
    }
    for(unsigned j=0;j<history_count;++j) write_line(history[(history_at+DIAG_HISTORY-history_count+j)%DIAG_HISTORY]);
    AcquireSRWLockExclusive(&event_lock);
    for(unsigned j=0;j<event_count;++j) write_line(events[j]);
    event_count=0;ReleaseSRWLockExclusive(&event_lock);
    write_line("{\"schema\":1,\"type\":\"end\"}");
    if(output) { fclose(output); output=NULL; }
    return 0;
}
void ocr_diag_stop(void) {
    if(!worker || atomic_exchange(&stopping,1)) return;
    atomic_store(&enabled,0); SetEvent(stop_event);
    if(WaitForSingleObject(worker,2000)==WAIT_OBJECT_0) { CloseHandle(worker); CloseHandle(stop_event); worker=stop_event=NULL; }
}
void ocr_diag_init(void) {
    static int initialized;
    if(initialized++) return;
    const char *setting=getenv("OCR_DIAGNOSTICS"); if(setting && !atoi(setting)) return;
    LARGE_INTEGER f; QueryPerformanceFrequency(&f); frequency=f.QuadPart; origin=now_ns();
    wchar_t path[1024];
    DWORD n=GetEnvironmentVariableW(L"OCR_TRACE_FILE",path,1024);
    if(!n || n>=1024) {
        n=GetModuleFileNameW(NULL,path,900); if(!n || n>=900) return;
        while(n && path[n-1]!=L'\\' && path[n-1]!=L'/') --n;
        _snwprintf(path+n,1024-n,L"ocarina_reborn_diagnostics.jsonl");
    }
    wcscpy(output_path,path);
    _snwprintf(previous_path,1100,L"%ls.previous.jsonl",path);
    output=_wfopen(path,L"wb"); if(!output) return;
    // Direct launches reuse a fixed path; never pair a new run with stale history.
    DeleteFileW(previous_path);
    write_line("{\"schema\":1,\"type\":\"start\",\"history_seconds\":30,\"follow_seconds\":10,\"segment_max_bytes\":8388608,\"retained_segments\":2,\"notes\":\"Stage totals overlap across threads; GPU timing delayed. Native zstd only; uninstrumented work is unknown. No-frame progress may mean loading or focus loss. Ctrl+F8 marks a problem.\"}");
    clock_anchor();
    fflush(output);
    stop_event=CreateEventW(NULL,TRUE,FALSE,NULL);
    if(!stop_event) { fclose(output);output=NULL;return; }
    atomic_store(&enabled,1);
    worker=CreateThread(NULL,0,record_thread,NULL,0,NULL);
    if(!worker) { atomic_store(&enabled,0);CloseHandle(stop_event);stop_event=NULL;fclose(output);output=NULL;return; }
    atexit(ocr_diag_stop);
    hos_log("[diagnostics] bounded timeline enabled; Ctrl+F8 marks a problem; no memory or audio capture");
}
#else
void ocr_diag_init(void) {}
int ocr_diag_enabled(void) {return 0;}
void ocr_diag_stop(void) {}
void ocr_diag_frame(const OcrDiagFrame *f) {(void)f;}
void ocr_diag_event(const char *a,const char *b) {(void)a;(void)b;}
void ocr_diag_mark(void) {}
OcrDiagSpan ocr_diag_begin(int k) {OcrDiagSpan s={0};s.kind=k;return s;}
void ocr_diag_end(OcrDiagSpan s,uint64_t b) {(void)s;(void)b;}
#endif
