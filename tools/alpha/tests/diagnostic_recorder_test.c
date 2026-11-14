/* Exercise the actual recorder without game data, rendering or audio devices. */
#include "../../../engine/host/ocr_diagnostics.c"
HosThread *hos_self(void) {return NULL;}
const char *hos_thread_name(HosThread *t) {(void)t;return "fixture";}
void hos_log(const char *fmt, ...) {(void)fmt;}
int ocr_diag_cpu_threads(OcrDiagCpuThread *out,int max) {
    if(max<1)return 0;
    out[0].tid=17;out[0].cpu_100ns=(uint64_t)(now_ns()-origin)/10;
    strcpy(out[0].name,"\xe5\x87\xa6\xe7\x90\x86 CPU");return 1;
}
int ocr_diag_context(OcrDiagContext *out) {
    strcpy(out->map,"TestRoom");out->event=1;out->loading=1;out->child=0;out->age_ms=12;return 1;
}
static DWORD WINAPI io_worker(void *arg) {
    (void)arg;
    for(int i=0;i<5000;++i) {
        OcrDiagSpan a=ocr_diag_begin(OCR_DIAG_READ);
        OcrDiagSpan b=ocr_diag_begin(OCR_DIAG_ZSTD);
        ocr_diag_end(b,128);ocr_diag_end(a,64);
    }
    return 0;
}
int main(int argc,char **argv) {
    char checked[48];safe_text(checked,sizeof checked,"\xe5\x87\xa6\xe7\x90\x86 CPU");
    if(strcmp(checked,"\xe5\x87\xa6\xe7\x90\x86 CPU"))return 10;
    safe_text(checked,3,"\xe5\x87\xa6");if(checked[0])return 11;
    safe_text(checked,sizeof checked,"\xe5");if(strcmp(checked,"_"))return 12;
    ocr_diag_init();
    if(argc>1 && !strcmp(argv[1],"slots")) {
        for(int i=0;i<DIAG_THREADS;++i)atomic_store(&threads[i].claimed,2);
        for(int i=0;i<10;++i) {OcrDiagSpan s=ocr_diag_begin(OCR_DIAG_READ);ocr_diag_end(s,64);}
        if(own_slot!=-2 || atomic_load(&untracked_phase_threads)!=1)return 13;
        if(atomic_load(&stage_bytes[OCR_DIAG_READ])!=640)return 14;
        ocr_diag_stop();return 0;
    }
    if(argc>1 && !strcmp(argv[1],"cap")) {
        written=DIAG_LIMIT;
        write_line("{\"schema\":1,\"type\":\"after_rotation\"}");ocr_diag_stop();return 0;
    }
    OcrDiagFrame f={.frame_ms=16.667,.renderer_ms=3,.gpu_ms=4,.draws=0,.vram_known=1,.vram_used=123,.vram_budget=456};
    if(argc>1 && !strcmp(argv[1],"bench")) {
        int64_t start=now_ns();
        for(int i=0;i<300000;++i) {ocr_diag_frame(&f);OcrDiagSpan a=ocr_diag_begin(OCR_DIAG_READ);ocr_diag_end(a,64);}
        printf("recorder_frame_and_span_us=%.6f\n",(now_ns()-start)/3e8);
        ocr_diag_stop();return 0;
    }
    HANDLE work[4];for(int i=0;i<4;++i)work[i]=CreateThread(NULL,0,io_worker,NULL,0,NULL);
    WaitForMultipleObjects(4,work,TRUE,5000);for(int i=0;i<4;++i)CloseHandle(work[i]);
    for(int i=0;i<12;++i) {ocr_diag_frame(&f);Sleep(100);}
    f.frame_ms=180;ocr_diag_frame(&f);Sleep(1200);
    ocr_diag_mark();Sleep(1200);
    OcrDiagSpan wait=ocr_diag_begin(OCR_DIAG_WAIT);
    Sleep(5200);ocr_diag_end(wait,0);
    for(int i=0;i<100;++i)ocr_diag_event("flood", "test bounded queue");
    Sleep(1100);
    ocr_diag_stop();return 0;
}
