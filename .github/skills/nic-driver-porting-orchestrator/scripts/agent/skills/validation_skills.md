# Validation Agent Skills

Best Known Methods (BKMs) for Phases 4–5: native validation, code review, performance analysis, and portability validation.

## Domain Knowledge

### Native Validation (Phase 4)

**native_score** measures how well the adapter layer uses idiomatic target-OS APIs:

| Check | Weight | Fails If |
| ----- | ------ | -------- |
| Uses `bus_dma` (not raw pointers) | 20 | Any `malloc`+cast for DMA |
| Uses `mbuf` chains correctly | 15 | Manual buffer stitching |
| Proper `MTX`/`SX` locking | 15 | Missing locks in Rx/Tx path |
| `DRIVER_MODULE` / `DEVMETHOD` boilerplate | 10 | Missing or malformed |
| `device_printf` for logging | 5 | Uses `printf` or Linux `pr_err` |
| iflib integration (if applicable) | 15 | Missing iflib callbacks |
| Error paths free resources | 10 | Leak on `bus_dmamap_load` failure |
| Correct `SYSCTL` tunables | 10 | Hardcoded magic numbers |

Threshold: **native_score ≥ 98** to pass gate.

### Code Review (Phase 4)

- Check for use-after-free in Rx buffer recycling
- Verify descriptor ring wrap-around arithmetic (power-of-two masking)
- Confirm no `#ifdef __linux__` leaks into portable core
- Validate all public functions have matching declarations in headers

### Performance Analysis (Phase 5)

- Identify hot paths: Rx clean loop, Tx map-and-post loop
- Flag unnecessary allocations inside hot loops
- Check for cache-line alignment on descriptor ring base addresses
- Verify prefetch hints (`__builtin_prefetch`) are preserved or adapted
- Look for per-packet lock acquisition (should be per-batch or lock-free)

### Portability Validation (Phase 5)

**portability_score** measures how clean the portable core is:

| Check | Weight | Fails If |
| ----- | ------ | -------- |
| Zero OS headers in `portable_core/` | 30 | Any `#include <sys/*>` |
| Only `stdint.h` / `stdbool.h` types | 20 | Uses `u32`, `ULONG`, etc. |
| No compiler-specific extensions | 15 | `__attribute__` without guard |
| No direct HW access in core | 20 | `bus_space_*` in core files |
| Adapter boundary via function pointers | 15 | Direct function calls to OS |

Threshold: **portability_score ≥ 95** to pass gate.
