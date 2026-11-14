#pragma once
#include <stdint.h>
#include "../gpu/vk/ocr_diag_types.h"
enum { OCR_DIAG_READ, OCR_DIAG_ZSTD, OCR_DIAG_WAIT, OCR_DIAG_STAGES };
typedef struct OcrDiagSpan { int slot, previous, kind; int64_t start, previous_start; } OcrDiagSpan;
void ocr_diag_init(void);
int ocr_diag_enabled(void);
void ocr_diag_stop(void);
void ocr_diag_frame(const OcrDiagFrame *frame);
void ocr_diag_event(const char *kind, const char *detail);
void ocr_diag_mark(void);
OcrDiagSpan ocr_diag_begin(int kind);
void ocr_diag_end(OcrDiagSpan span, uint64_t bytes);
typedef struct OcrDiagCpuThread { uint32_t tid; uint64_t cpu_100ns; char name[48]; } OcrDiagCpuThread;
int ocr_diag_cpu_threads(OcrDiagCpuThread *out, int max);
typedef struct OcrDiagContext { char map[80]; int event, loading, child; double age_ms; } OcrDiagContext;
int ocr_diag_context(OcrDiagContext *out);
