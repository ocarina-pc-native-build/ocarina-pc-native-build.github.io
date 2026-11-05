#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
void *oot_reserve(size_t size);
int oot_release(void *memory);
uint64_t oot_ticks_ns(void);
int oot_selftest(void);
int oot_probe_gpu(int validation);
int oot_probe_input(void);
int oot_unsupported_service(const char *service, uint32_t command, uint64_t pc);
#ifdef __cplusplus
}
#endif
