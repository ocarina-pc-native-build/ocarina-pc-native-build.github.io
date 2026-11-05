#pragma once
#include <stdint.h>
#ifdef OOT_PACGA_TEST
#define PACGA_API __declspec(dllexport)
#else
#define PACGA_API
#endif
PACGA_API uint64_t oot_pacga_qarma5(uint64_t data,uint64_t modifier,uint64_t key_lo,uint64_t key_hi);
PACGA_API uint64_t rt_pacga(uint64_t data,uint64_t modifier);
