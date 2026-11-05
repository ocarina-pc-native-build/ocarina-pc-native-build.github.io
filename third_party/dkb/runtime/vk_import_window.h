// Bounded zero-copy views of a larger host allocation. No game-specific sizes.
#pragma once
#include <stdint.h>

static inline int vk_import_window(uint64_t pool_lo, uint64_t pool_hi, uint64_t addr, uint64_t size,
                                   uint64_t align, uint64_t limit, uint64_t *lo, uint64_t *hi) {
    if (!align || (align & (align - 1)) || !size || pool_hi <= pool_lo || addr < pool_lo ||
        addr >= pool_hi || size > pool_hi - addr) return 0;
    uint64_t start = addr & ~(align - 1), cap = limit & ~(align - 1);
    if (start < pool_lo || !cap || addr - start > cap || size > cap - (addr - start)) return 0;
    uint64_t n = pool_hi - start;
    if (n > cap) n = cap;
    if (n & (align - 1)) return 0; // the owning imported range is aligned outwards
    *lo = start;
    *hi = start + n;
    return 1;
}
