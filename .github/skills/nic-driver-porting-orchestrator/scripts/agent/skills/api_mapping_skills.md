# API Mapping Agent Skills

Best Known Methods (BKMs) for Phase 1: building Linux → target-OS API mapping tables.

## Domain Knowledge

### Core Linux → FreeBSD Mappings

| Linux API | FreeBSD Equivalent | Notes |
| --------- | ------------------ | ----- |
| `dma_map_single` / `dma_map_page` | `bus_dmamap_load` | Requires `bus_dma_tag_t` setup |
| `dma_unmap_single` | `bus_dmamap_unload` | Must sync before unload |
| `sk_buff` / `skb` | `mbuf` / `m_freem` | Chain via `m_next` |
| `napi_schedule` / `napi_complete` | `iflib_rx_intr_deferred` or `taskqueue_enqueue` | iflib path preferred |
| `netif_receive_skb` | `if_input` / `iflib` callback | |
| `kzalloc` / `kfree` | `malloc(M_DEVBUF)` / `free` | Use `M_WAITOK \| M_ZERO` |
| `spin_lock` / `spin_unlock` | `mtx_lock` / `mtx_unlock` | |
| `pci_read_config_dword` | `pci_read_config(dev, reg, 4)` | |
| `readl` / `writel` | `bus_space_read_4` / `bus_space_write_4` | |
| `msleep` | `pause_sbt` or `DELAY` | |
| `dev_err` / `dev_info` | `device_printf` | |
| `MODULE_INIT` / `MODULE_EXIT` | `DRIVER_MODULE` macro | |

### Core Linux → Windows NDIS Mappings

| Linux API | NDIS Equivalent | Notes |
| --------- | --------------- | ----- |
| `dma_map_single` | `NdisMAllocateSharedMemory` | Or `NDIS_SCATTER_GATHER_DMA` |
| `sk_buff` | `NET_BUFFER_LIST` / `NET_BUFFER` | |
| `napi_schedule` | `NdisMIndicateReceiveNetBufferLists` | In DPC context |
| `kzalloc` | `NdisAllocateMemoryWithTagPriority` | |
| `spin_lock` | `NdisAcquireSpinLock` | |

### Mapping Table Output Format

Produce a JSON or Markdown table per source file with columns:

- `linux_api` — original call
- `target_api` — replacement call
- `file` — source file where it appears
- `line` — approximate line number
- `risk` — LOW / MEDIUM / HIGH (semantic gap size)
- `notes` — special handling instructions

### Pitfalls

- `dma_sync_single_for_cpu` has no direct FreeBSD equivalent — use `bus_dmamap_sync(BUS_DMASYNC_POSTREAD)`
- Timer APIs (`mod_timer`, `del_timer_sync`) require `callout_reset` / `callout_drain`
- Completion variables (`init_completion`, `wait_for_completion`) → `sx_lock` + `cv_wait`
