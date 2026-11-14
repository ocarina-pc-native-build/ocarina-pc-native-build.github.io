#pragma once
#include <stdint.h>
/* C ABI. Durations can overlap and must not be added to infer a frame's cause.
   GPU results may arrive later than their originating frame. */
typedef struct OcrDiagFrame {
    double frame_ms, renderer_ms, gpu_ms, pipeline_ms, program_ms, upload_ms;
    double memory_sync_ms, slot_wait_ms, readback_ms, texture_frame_ms, translate_ms, pipeline_wait_ms;
    uint64_t draws, upload_bytes, new_pipelines, not_ready, vram_used, vram_budget;
    int menu, frame_generation, vram_known;
} OcrDiagFrame;
