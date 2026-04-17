# Coder Agent Skills

Best Known Methods (BKMs) for Phase 3: implementing ported data-plane driver code.

## Domain Knowledge

### Zero-Framework Rule for Portable Core

- `portable_core/` files must contain **zero** OS-specific headers (`#include <linux/*>`, `<sys/param.h>`, `<ndis.h>`)
- All OS interactions go through adapter function pointers or inline helpers in the adapter layer
- Use types from `<stdint.h>` and `<stdbool.h>` — never `u32`/`s32` (Linux) or `ULONG` (Windows)

### Adapter Layer Pattern

```c
/* freebsd_adapter/if_ixgbe.c */
#include <sys/bus.h>
#include <net/if.h>
#include "portable_core/ixgbe_rx.h"

static uint32_t freebsd_read_reg(void *ctx, uint32_t offset) {
    struct ixgbe_softc *sc = ctx;
    return bus_space_read_4(sc->osdep.mem_bus_space_tag,
                            sc->osdep.mem_bus_space_handle, offset);
}
```

### Implementation Order

1. Hardware register layer (`hw/`) — should mostly be copy-paste + type fixes
2. Portable core data structures and ring management
3. Rx path (alloc → post → clean → deliver)
4. Tx path (map → enqueue → clean → complete)
5. Interrupt and polling glue in the adapter layer

### Common Pitfalls

- Forgetting `bus_dmamap_sync` before reading descriptors (causes stale data on FreeBSD)
- Using `__attribute__((packed))` differently across compilers — prefer explicit padding
- Endianness: always use `le32_to_cpu` / `htole32` when touching descriptor fields
- Lock ordering: acquire Tx lock before Rx lock if both are needed (prevents deadlock)

### Code Quality Standards

- Every function ≤ 80 lines
- Every file ≤ 600 lines (split if larger)
- Static functions for internal helpers; exported functions get `driver_` prefix
- `const` correctness on all pointer parameters that are read-only
