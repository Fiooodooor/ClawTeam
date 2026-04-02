# Source Analysis Agent Skills

Best Known Methods (BKMs) for Phase 0: analysing a Linux NIC driver source tree and scaffolding the porting directory layout.

## Domain Knowledge

### Linux Driver Source Layout

- Data-plane code is typically under `drivers/net/ethernet/<vendor>/` or a standalone repo root
- Key directories: `src/`, `include/`, `common/`, `test/`
- Data-plane files to locate: ring management, descriptor handling, Tx/Rx path, interrupt coalescing, DMA, RSS, checksum offload
- Ignore control-plane files: netdev_ops callbacks, ethtool, devlink, firmware management (unless they carry shared types)

### Three-Layer Separation

The porting output must follow the three-layer architecture:

| Layer | Directory | Contains |
| ----- | --------- | -------- |
| Portable NIC Core | `portable_core/` | Zero OS calls, pure C data-plane logic |
| FreeBSD Native Adapter | `freebsd_adapter/` | `if_<driver>.c`, `bus_dma`, `iflib`, `mbuf` |
| Hardware Registers | `hw/` | Register definitions, BAR offsets, mailbox, PHY |

### File Discovery Heuristics

- `grep -rl "napi_complete\|netif_receive_skb\|dma_map"` to find Rx/Tx hot paths
- Header files with `_hw.h` or `_type.h` often define registers
- `Makefile` or `Kbuild` reveals the full file set for a module

### Scaffolding Checklist

1. Create `output_dir/{portable_core, freebsd_adapter, hw, tests, docs}/`
2. Write `portable_core/README.md` with the zero-OS-call rule
3. Copy register headers into `hw/` verbatim
4. Create stub `.c / .h` files for each data-plane translation unit
