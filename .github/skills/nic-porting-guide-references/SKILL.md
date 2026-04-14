---
name: nic-porting-guide-references
description: "9-volume reference knowledge base for Linux-to-FreeBSD NIC driver porting. Covers architectural foundations, portable NIC core, FreeBSD native adapter, DMA engine, TX/RX paths, interrupts/MSI-X, offloads, and TDD/validation. Use when: implementing any porting phase, writing tests, designing seams, mapping APIs, or validating ported code."
---

# NIC Porting Guide — Volume References

This skill provides the authoritative reference material for every phase of a Linux-to-FreeBSD NIC driver port. Each volume maps to one or more phases and defines the expected deliverables, key APIs, risk areas, and code patterns.

## Volume-to-Phase Map

| Volume | Title | Primary Phase(s) | Key Deliverable |
| ------ | ----- | ----------------- | --------------- |
| I | Architectural Foundations | 0 (scope-baseline) | Extracted Linux dataplane file inventory |
| II | Portable NIC Core | 2-3 (seam-design, tdd-harness) | tx_ring.c, rx_ring.c, descriptor.c, offload.c |
| III | FreeBSD Native Adapter | 2 (seam-design) | Compilable skeleton module (kldload succeeds) |
| IV | DMA Engine | 4 (incremental-port) | mynic_dma.c — tags, ring alloc, populate, refill, sync, unload |
| V | Transmit Path | 4 (incremental-port) | mynic_tx.c — if_transmit, queue select, TSO, multi-queue |
| VI | Receive Path | 4 (incremental-port) | mynic_rx.c — ring init, rx_process, refill, pre-alloc pool |
| VII | Interrupts, MSI-X & Taskqueues | 4-5 (incremental-port, gates) | mynic_intr.c — MSI-X setup, fast handler, taskqueue, teardown |
| VIII | Offloads | 5 (gates) | RSS config, TSO/checksum flag translation |
| IX | TDD, Performance & Validation | 5-7 (gates, merge-sync, multi-os) | 500+ TDD tests, risk register, performance tuning, checklist |

---

## Volume I — Architectural Foundations (Phase 0)

### Objective
Extract and inventory all Linux dataplane source files for the target driver. Establish the baseline hash, identify OS-dependent vs OS-independent code, and lock the scope.

### Key Concepts
- Linux NIC driver split: admin-plane (ethtool, devlink, PF/VF mgmt) vs data-plane (TX/RX rings, DMA, interrupts).
- Only the data-plane is in scope for porting.
- Identify all kernel API calls: `dma_map_single`, `napi_gro_receive`, `netif_napi_add`, `request_irq`, `skb_*`, `pci_*`.

### Expected Outputs
- File list with line counts and dependency graph.
- API call inventory with frequency counts.
- Scope lock document signed by orchestrator.

### Risk Areas
- Scope creep into admin-plane code.
- Undetected compile-time dependencies on Linux-only headers.

---

## Volume II — Portable NIC Core (Phases 2-3)

### Objective
Design the OS-abstraction seams and build the portable inner core that compiles on both Linux and FreeBSD without modification.

### Key Files
- `tx_ring.c` — descriptor ring management, doorbell writes.
- `rx_ring.c` — receive ring management, buffer posting.
- `descriptor.c` — descriptor format encode/decode.
- `offload.c` — hardware offload capability negotiation.

### Seam Design Principles
- Compile-time seams via `#ifdef __FreeBSD__` / `#ifdef __linux__`.
- Link-time seams via weak symbols for platform-specific hooks.
- Zero new abstractions — reuse LinuxKPI shims exclusively.
- All platform calls go through a thin inline wrapper in `mynic_osdep.h`.

### Expected Outputs
- `mynic_osdep.h` with all platform-abstracted inline wrappers.
- Portable core files that build on both targets with only `osdep.h` included.

---

## Volume III — FreeBSD Native Adapter (Phase 2)

### Objective
Create the FreeBSD iflib adapter skeleton that loads as a kernel module and registers with the network stack.

### Key APIs
- `iflib` framework: `DRIVER_MODULE`, `iflib_device_register`, `if_softc_alloc`.
- `device_method_t` array: `DEVMETHOD(device_probe, ...)`, `DEVMETHOD(device_attach, ...)`.
- `if_shared_ctx_t` for shared context between iflib and driver.

### Skeleton Structure
```c
static device_method_t mynic_methods[] = {
    DEVMETHOD(device_probe,    mynic_probe),
    DEVMETHOD(device_attach,   mynic_attach),
    DEVMETHOD(device_detach,   mynic_detach),
    DEVMETHOD_END
};

DRIVER_MODULE(mynic, pci, mynic_driver, mynic_devclass, 0, 0);
MODULE_DEPEND(mynic, pci, 1, 1, 1);
MODULE_DEPEND(mynic, ether, 1, 1, 1);
MODULE_DEPEND(mynic, iflib, 1, 1, 1);
```

### Expected Outputs
- `mynic_freebsd.c` — skeleton that compiles and loads via `kldload`.
- Makefile / module build integration.

### Validation Gate
- `kldload mynic.ko` succeeds without panic.
- `dmesg | grep mynic` shows probe message.

---

## Volume IV — DMA Engine (Phase 4)

### Objective
Port the DMA subsystem from Linux `dma_*` API to FreeBSD `bus_dma*` API with zero-copy guarantee.

### API Mapping

| Linux API | FreeBSD API | Notes |
| --------- | ----------- | ----- |
| `dma_alloc_coherent` | `bus_dmamem_alloc` + `bus_dmamap_load` | Two-step in FreeBSD |
| `dma_map_single` | `bus_dmamap_load_mbuf_sg` | Scatter-gather for mbufs |
| `dma_unmap_single` | `bus_dmamap_unload` | Must precede free |
| `dma_sync_single_for_device` | `bus_dmamap_sync(BUS_DMASYNC_PREWRITE)` | Before DMA write |
| `dma_sync_single_for_cpu` | `bus_dmamap_sync(BUS_DMASYNC_POSTREAD)` | After DMA read |

### DMA Tag Hierarchy
```c
/* Parent tag — device-wide constraints */
bus_dma_tag_create(bus_get_dma_tag(dev), 1, 0,
    BUS_SPACE_MAXADDR, BUS_SPACE_MAXADDR, NULL, NULL,
    BUS_SPACE_MAXSIZE, 0, BUS_SPACE_MAXSIZE, 0, NULL, NULL,
    &sc->parent_tag);

/* TX ring tag */
bus_dma_tag_create(sc->parent_tag, PAGE_SIZE, 0,
    BUS_SPACE_MAXADDR, BUS_SPACE_MAXADDR, NULL, NULL,
    tx_ring_size, 1, tx_ring_size, 0, NULL, NULL,
    &txr->desc_tag);
```

### Risk Register Items
- **R-01 DMA sync omitted** (Critical): Every DMA buffer access must be bracketed by `bus_dmamap_sync` calls. Missing sync causes data corruption on non-cache-coherent platforms.
- **R-02 Ring full race** (Critical): Ring-full check and doorbell write must be atomic or properly fenced.

### Expected Outputs
- `mynic_dma.c` — complete DMA lifecycle: tag create, ring alloc, populate, refill, sync, unload, destroy.
- Failing tests written first (Vol IX protocol), then implementation.

---

## Volume V — Transmit Path (Phase 4)

### Objective
Port the TX path from Linux `ndo_start_xmit` to FreeBSD `if_transmit` / iflib TX callback.

### Key Concepts
- FreeBSD uses `if_transmit()` as the entry point (replaces `ndo_start_xmit`).
- iflib provides `iflib_txq_can_drain()` and ring management.
- TSO: translate Linux `skb_is_gso()` + GSO fields to FreeBSD `CSUM_TSO` + `tso_segsz`.
- Multi-queue: map Linux `netdev_pick_tx()` to FreeBSD RSS-based queue selection.

### TX Descriptor Posting Pattern
```c
static int
mynic_isc_txd_encap(void *arg, if_pkt_info_t pi)
{
    /* Map mbuf fragments to TX descriptors */
    bus_dmamap_load_mbuf_sg(txr->buf_tag, txbuf->map,
        pi->ipi_m, segs, &nsegs, BUS_DMA_NOWAIT);
    bus_dmamap_sync(txr->buf_tag, txbuf->map,
        BUS_DMASYNC_PREWRITE);
    /* Fill descriptors, set TSO/checksum flags */
    /* Write doorbell */
}
```

### Expected Outputs
- `mynic_tx.c` — complete TX path with queue selection, descriptor posting, TSO support.

---

## Volume VI — Receive Path (Phase 4)

### Objective
Port the RX path from Linux NAPI to FreeBSD iflib RX callback.

### Key Concepts
- FreeBSD iflib calls `isc_rxd_pkt_get()` to dequeue received packets.
- mbuf allocation: `m_getjcl()` for jumbo, `m_gethdr()` for standard, or iflib managed buffers.
- Refill: `isc_rxd_refill()` posts new buffers to hardware ring.
- Pre-allocated mbuf pool avoids allocation in hot path.

### RX Processing Pattern
```c
static int
mynic_isc_rxd_pkt_get(void *arg, if_rxd_info_t ri)
{
    /* Read descriptor status */
    /* Extract packet length, RSS hash, VLAN, checksum status */
    bus_dmamap_sync(rxr->buf_tag, rxbuf->map,
        BUS_DMASYNC_POSTREAD);
    bus_dmamap_unload(rxr->buf_tag, rxbuf->map);
    ri->iri_len = pkt_len;
    ri->iri_frags[0].irf_flid = 0;
    ri->iri_frags[0].irf_idx = idx;
    ri->iri_nfrags = 1;
    return 0;
}
```

### Risk Register Items
- **R-03 mbuf freed too early** (Critical): mbuf must not be freed until DMA unload completes.
- **R-04 mbuf exhaustion under flood** (High): Pre-alloc pool must handle sustained line-rate traffic.

### Expected Outputs
- `mynic_rx.c` — ring init, rx_process, refill, pre-alloc pool management.

---

## Volume VII — Interrupts, MSI-X & Taskqueues (Phases 4-5)

### Objective
Port interrupt registration and handling from Linux `request_irq` / threaded IRQs to FreeBSD `bus_setup_intr` / taskqueue.

### API Mapping

| Linux API | FreeBSD API | Notes |
| --------- | ----------- | ----- |
| `request_irq` | `bus_setup_intr` | With `INTR_TYPE_NET \| INTR_MPSAFE` |
| `free_irq` | `bus_teardown_intr` | Must be called before resource release |
| `enable_irq` / `disable_irq` | `bus_bind_intr` / mask via register | Per-vector control |
| Threaded IRQ / `napi_schedule` | `taskqueue_enqueue` | Fast handler + deferred work |

### MSI-X Setup Pattern
```c
/* Allocate MSI-X vectors */
rid = 1;
for (i = 0; i < num_vectors; i++) {
    sc->msix[i].res = bus_alloc_resource_any(dev,
        SYS_RES_IRQ, &rid, RF_ACTIVE);
    bus_setup_intr(dev, sc->msix[i].res,
        INTR_TYPE_NET | INTR_MPSAFE,
        mynic_fast_intr, NULL, sc->msix[i].arg,
        &sc->msix[i].tag);
    rid++;
}
```

### Risk Register Items
- **R-05 Interrupt storm on detach** (High): All interrupt handlers must be torn down before resources are freed. `bus_teardown_intr` must precede `bus_release_resource`.

### Expected Outputs
- `mynic_intr.c` — MSI-X allocation, fast handler, taskqueue setup, teardown sequence.

---

## Volume VIII — Offloads (Phase 5)

### Objective
Map hardware offload capabilities and flags between Linux and FreeBSD.

### Flag Translation

| Linux Flag | FreeBSD Flag | Feature |
| ---------- | ------------ | ------- |
| `NETIF_F_RXCSUM` | `IFCAP_RXCSUM` | RX checksum offload |
| `NETIF_F_TXCSUM` | `IFCAP_TXCSUM` | TX checksum offload |
| `NETIF_F_TSO` | `IFCAP_TSO4` | TCP Segmentation Offload (IPv4) |
| `NETIF_F_TSO6` | `IFCAP_TSO6` | TCP Segmentation Offload (IPv6) |
| `NETIF_F_LRO` | `IFCAP_LRO` | Large Receive Offload |
| `NETIF_F_RXHASH` | `IFCAP_RXHASH` \| RSS | Receive-side Scaling hash |

### RSS Configuration
- Use `rss_getcpu()` and `rss_hash2bucket()` for queue-to-CPU mapping.
- Configure indirection table via `if_setmulti` / device register writes.

### Expected Outputs
- Offload capability registration in `mynic_attach()`.
- Flag translation helpers (compile-time macros, not runtime).

---

## Volume IX — TDD, Performance & Validation (Phases 5-7)

### Objective
Establish the test-driven development protocol, performance validation gates, and final acceptance checklist.

### TDD Protocol
1. **Red**: tdd-writer creates failing tests for the target subsystem BEFORE any implementation.
2. **Green**: coder implements the minimum code to pass the tests.
3. **Refactor**: code-reviewer ensures minimal-touch compliance.
4. **Gate**: native-validator + portability-validator verify scores.

### Test Categories

| Category | Count Target | Owner |
| -------- | ------------ | ----- |
| DMA lifecycle | 50+ | tdd-writer |
| TX path (normal, TSO, multi-queue) | 80+ | tdd-writer |
| RX path (normal, jumbo, error) | 80+ | tdd-writer |
| Interrupt setup/teardown | 40+ | tdd-writer |
| Offload flag translation | 30+ | tdd-writer |
| Ring management edge cases | 50+ | tdd-writer |
| Error injection (alloc fail, DMA fail) | 50+ | tdd-writer |
| Cross-compile build gates | 20+ | verification-executor |
| Performance regression | 50+ | performance-engineer |
| Integration (attach/detach cycle) | 50+ | verification-executor |

### Risk Register Template
```json
{
  "id": "RISK-NNN",
  "phase": 0,
  "substep": "phase-key/role",
  "severity": "critical | high | medium | low",
  "description": "",
  "mitigation": "",
  "status": "open | mitigated | accepted | closed",
  "owner": "",
  "detected_at": "",
  "resolved_at": null
}
```

### Known Risk Categories

| ID | Description | Severity | Mitigation |
| -- | ----------- | -------- | ---------- |
| R-01 | DMA sync omitted — missing bus_dmamap_sync before/after DMA | Critical | Grep audit + dedicated test |
| R-02 | Ring full race — unprotected ring-full check vs doorbell write | Critical | Atomic fence or lock audit |
| R-03 | mbuf freed too early — free before DMA unload completes | Critical | Lifecycle sequence test |
| R-04 | mbuf exhaustion under flood — pre-alloc pool undersized | High | Stress test at line rate |
| R-05 | Interrupt storm on detach — handlers active after resource free | High | Teardown sequence test |

### Performance Validation Gates
- Zero memcpy in TX/RX hot paths (verified by tracing or static analysis).
- Latency regression < 5% vs Linux baseline.
- Throughput regression < 2% vs Linux baseline at line rate.
- CPU utilization within 10% of Linux baseline under identical load.

### Final Acceptance Checklist
- [ ] All TDD tests green (500+ tests).
- [ ] native_score >= 98.0.
- [ ] portability_score >= 95.0.
- [ ] critical_risks = 0.
- [ ] build_status = green (Linux + FreeBSD).
- [ ] kldload/kldunload cycle succeeds 100 times without leak.
- [ ] dmesg clean after attach/detach.
- [ ] Performance gates met.
- [ ] Risk register fully resolved or accepted.
- [ ] Patch set reviewed and merge-ready.
