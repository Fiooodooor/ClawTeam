# AI Agent Orchestration: Linux-to-FreeBSD Porting Guide

The ethernet driver porting manual. Best known methods and step-by-step instructions for porting Network Interface Card (NIC) driver data-plane from Linux to FreeBSD using native kernel APIs (LinuxKPI + iflib or pure native FreeBSD).
Last edited in `03.2026`.

## Porting The Ethernet Network Interface Card Driver `03.2026`

**Core Philosophy**  
The most maintainable and future-proof way to port any modern Ethernet NIC driver from Linux to FreeBSD in 2026 is to extract a **strictly framework-independent portable NIC core** (containing zero OS calls whatsoever) and wrap it with an extremely thin native FreeBSD adapter that speaks only the official FreeBSD kernel interfaces: `ifnet(9)`, `bus_dma(9)`, `mbuf(9)`, `pci(9)`, `taskqueue(9)`, and direct MSI-X registration.  

This approach guarantees:

- Identical dataplane behaviour to the original Linux driver (same descriptor formats, same RSS/TSO/checksum logic).
- Zero runtime overhead from translation layers.
- Full control over memory ownership, DMA mapping, and interrupt moderation.
- Easy debugging because every line in the hot path is either pure portable logic or a well-documented native FreeBSD call.
- Long-term maintainability – when the Linux reference driver changes, you only update the portable core.

**Strict Rules Enforced Throughout This Guide**  

- Portable core: zero `#include <linux/*>`, zero `sk_buff`, zero `net_device`, zero `napi`.  
- FreeBSD adapter: only `if_t`, `struct mbuf *`, `bus_dma_tag_t`, `bus_dmamap_t`, `taskqueue_enqueue`, `pci_alloc_msix`, etc.  
- All code is immediately compilable as a standard FreeBSD kernel module (`kldload`).  
- Every volume includes detailed rationales, line-by-line explanations, common pitfalls with exact mitigations, and heavily commented code examples.

The entire port is divided into **nine self-contained volumes**. Each volume builds directly on the previous one and produces immediately usable, testable artefacts.

---

## Orchestrator Execution Model

> Merged from the original `system-prompt.md`. The v2.0 consolidated reference lives in `unified-operations-guide.md`.

**Orchestrator Supervisor** — the root hierarchical supervisor of the Linux → FreeBSD NIC Data-Plane Porting Project. Its sole purpose is to autonomously drive the multi-agent swarm and produce complete, buildable, testable, framework-independent driver code. The supervisor has passwordless SSH access to enabled VMs via the connection info YAML file.

**Initialization Protocol (execute once at startup)**

1. Read this full porting guide (`./porting-guide.md` or the path provided by user).
2. Load and internalize every section: Architecture Decision, Phases 0–7, Testing Strategy, Risk Register, Validation Checklist.
3. Confirm parsing of:
   - All non-negotiable Core Porting Principles (correctness-first TDD, maximum performance + portability + minimal divergence, native-only OS calls, thin adapter seams).
   - The complete phase/sub-step mapping (Phases 0–7).
   - The execution model (ReAct loops, self-critique, multi-agent debate, conditional gates on native_score ≥98, portability_score ≥95).

**Operational Rules (never violate)**

- Route every sub-step to the correct specialist worker agent.
- Every sub-step protocol: TDD Writer (failing tests) → Coder → Native Validator → Reviewer → Performance Engineer → Portability Validator → Risk Auditor → Verification Executor → Supervisor gate.
- Enforce 100% native OS calls. Any detection of `rte_*`, DPDK, NDIS, or non-Linux/FreeBSD framework instantly triggers rejection and auto-fix.
- After every sub-step: create a durable checkpoint, update `artifacts/`, log to `./logs/`.
- Only proceed when ALL gates pass (native ≥98, portability ≥95, tests passed, build OK).

**Worker Agent Roles**

| Agent | Responsibility |
|-------|---------------|
| **TDD Writer** | Write failing tests BEFORE implementation using native mocks |
| **Coder** | Implement only native OS calls; maintain original Linux logic |
| **Native Validator** | Verify 100% native compliance, no framework leakage |
| **Code Reviewer** | Review for correctness, minimal divergence, `#ifdef` hygiene |
| **Performance Engineer** | Optimize only after baseline green; profile with perf/pmc |
| **Portability Validator** | Cross-compile Linux + FreeBSD; compute portability score |
| **Risk Auditor** | Maintain living risk register; flag critical issues |
| **Verification Executor** | Run full test suite + smoke tests on both OSes |

**Input/Output**

User provides: driver name (e.g., "ice", "ixgbe", "e1000e") and optional architecture preference (LinuxKPI+iflib vs pure native FreeBSD).

```
[ORCHESTRATOR] Phase X / Substep Y started
[ORCHESTRATOR] Guide loaded. Starting swarm for driver: <name>
... ReAct trace + scores per sub-step ...

========================================
ORCHESTRATOR COMPLETE — FULL PORT READY
Driver: <name>
Native score: XX.X | Portability: XX.X
Phases 0–7 executed
Artifacts: ./artifacts/<name>/
========================================
```

---

## Phase 0 — Directory Layout, Build Skeletons & TDD Harness

> Merged from the original `PHASE-0--core-layout--build-skeletons.md`.

**Directory Layout**

```
driver/
├── core/                  # portable_nic_core.c (zero OS calls)
├── os/
│   ├── linux/
│   └── freebsd/           # native ifnet/bus_dma or LinuxKPI+iflib
├── tests/                 # CppUTest native mocks
├── docs/
├── ...
├── porting_exceptions.md
├── Makefile.multi         # conditional
└── Kbuild
```

**Build System — full conditional example**

```make
# Makefile.multi
ifeq ($(OS),FREEBSD)
include freebsd_native.mk
else ifeq ($(OS),LINUX)
include linux_native.mk
endif
```

**TDD Harness — exact failing test with native mocks**

```cpp
TEST_GROUP(NativeRing);
TEST(NativeRing, TxRingPush_FreeBSD) {
    struct nic_ring r = {0};
    ring_init(&r, 64);
    struct mbuf *m = m_getcl(M_NOWAIT, MT_DATA, M_PKTHDR);  // native FreeBSD mock
    CHECK_EQUAL(0, portable_tx_submit(&r, m));  // fails first
}
```

**Deliverable of Phase 0**: Scaffold with directory layout, multi-OS build system, and initial failing TDD test — confirming the project compiles on both OSes before any porting begins.

---

## Phase 1 — API Inventory & Mapping Tables

**Objective**: Produce a 1:1 Linux→FreeBSD native API mapping table. Every Linux kernel call in the extracted dataplane files must resolve to a native FreeBSD equivalent.

**Workers**: `api-mapper` (concurrent), `kpi-auditor` (concurrent)

**Procedure**

1. **Scan**: Parse all `.c` and `.h` files under `core/` and `os/linux/` for kernel API calls (`dma_map_single`, `napi_schedule`, `netif_wake_queue`, `alloc_etherdev`, etc.).
2. **Classify**: Group each API call by subsystem:
   - Memory: `kmalloc`→`malloc(M_DEVBUF)`, `kfree`→`free(M_DEVBUF)`
   - DMA: `dma_map_single`→`bus_dmamap_load`, `dma_unmap_single`→`bus_dmamap_unload`
   - Network: `netif_receive_skb`→`if_input`, `napi_gro_receive`→`if_input`
   - Synchronization: `spin_lock`→`mtx_lock`, `spin_unlock`→`mtx_unlock`
   - PCI: `pci_read_config_dword`→`pci_read_config(dev, reg, 4)`
3. **Emit `api_mapping.json`**:
   ```json
   {
     "dma_map_single": {
       "freebsd": "bus_dmamap_load(tag, map, addr, len, callback, arg, flags)",
       "header": "<sys/bus_dma.h>",
       "notes": "Callback-based; requires bus_dma_tag_t pre-allocated"
     }
   }
   ```
4. **KPI Audit**: The `kpi-auditor` independently verifies that no LinuxKPI shims are needed — every mapping must be native FreeBSD.

**Gate**: `api_mapping.json` covers 100% of scanned calls. Zero unmapped entries.

---

## Phase 2 — Seam Architecture & OAL Design

**Objective**: Design thin OS Abstraction Layer (OAL) seams using `#ifdef`, inline wrappers, and weak symbols. Zero new abstractions.

**Workers**: `seam-architect` (depends on `api-mapper` + `kpi-auditor`)

**Procedure**

1. **Define seam boundaries** in `core/nic_oal.h`:
   ```c
   #ifdef __FreeBSD__
   #include "os/freebsd/oal_freebsd.h"
   #elif defined(__linux__)
   #include "os/linux/oal_linux.h"
   #endif
   ```
2. **Inline wrappers** — one per API mapping entry, e.g.:
   ```c
   /* os/freebsd/oal_freebsd.h */
   static inline int oal_dma_map(struct oal_dma_tag *t, void *addr,
                                  size_t len, bus_addr_t *paddr) {
       return bus_dmamap_load(t->tag, t->map, addr, len,
                              oal_dma_callback, paddr, BUS_DMA_NOWAIT);
   }
   ```
3. **Weak symbols** for optional features (e.g., `oal_hw_timestamp` defaults to no-op).
4. **Compile test**: `make -f Makefile.multi OS=FREEBSD oal-check` must succeed.

**Gate**: Both OS targets compile with zero errors. `grep -r 'sk_buff\|napi_struct\|net_device' core/` returns zero hits.

---

## Phase 3 — TDD Harness & Failing Tests

**Objective**: Write comprehensive failing tests for every ported subsystem BEFORE any implementation. Native mocks only.

**Workers**: `tdd-writer` (sequential)

**Procedure**

1. **Create test files** per subsystem:
   - `tests/test_tx_ring.c` — TX submission, completion, wrap-around, full-ring
   - `tests/test_rx_ring.c` — RX poll, refill, checksum validation, RSS
   - `tests/test_dma_engine.c` — Map, unmap, sync, bounce buffer, IOMMU
   - `tests/test_interrupts.c` — MSI-X allocation, handler dispatch, coalescing
   - `tests/test_offloads.c` — TSO segmentation, checksum offload, VLAN tag
2. **Each test must fail** with a clear assertion message:
   ```c
   TEST(TxRing, SubmitPacket_ReturnsZero) {
       struct nic_tx_ring r;
       nic_tx_ring_init(&r, 256);
       struct nic_packet pkt = { .data = mock_data, .len = 64, .dma_addr = 0x1000 };
       // This MUST fail until Phase 4 implements nic_tx_submit()
       CHECK_EQUAL(0, nic_tx_submit(&r, &pkt));
   }
   ```
3. **Run**: `make test` must show 100% FAIL (red) — confirms tests exercise unimplemented code.
4. **Document**: Each test file header explains what subsystem it covers and expected pass criteria.

**Gate**: All tests compile. All tests fail (no vacuous passes). Test count ≥ 50 per subsystem.

---

## Phase 4 — Incremental Port Slices

**Objective**: Port driver subsystems in micro-slices. Each slice must compile and pass its corresponding tests.

**Workers**: `coder` + `native-validator` (concurrent per slice)

**Slice ordering** (each depends on the previous):

| Slice | Subsystem | Key Files | Test Target |
|-------|-----------|-----------|-------------|
| 4.1 | Admin Queue | `admin_queue.c` | `test_admin_queue` |
| 4.2 | TX Ring | `tx_ring.c`, `os/freebsd/tx_freebsd.c` | `test_tx_ring` |
| 4.3 | RX Ring | `rx_ring.c`, `os/freebsd/rx_freebsd.c` | `test_rx_ring` |
| 4.4 | DMA Engine | `dma_engine.c`, `os/freebsd/dma_freebsd.c` | `test_dma_engine` |
| 4.5 | Interrupts/MSI-X | `intr.c`, `os/freebsd/intr_freebsd.c` | `test_interrupts` |
| 4.6 | Offloads | `offload.c`, `os/freebsd/offload_freebsd.c` | `test_offloads` |
| 4.7 | Stats/Counters | `stats.c` | `test_stats` |

**Per-slice protocol**:

1. TDD Writer confirms failing tests exist for this slice.
2. Coder implements the minimum code to pass tests — native FreeBSD calls only.
3. Native Validator: `grep -rn 'sk_buff\|napi\|rte_\|linuxkpi' os/freebsd/` must return zero.
4. Code Reviewer: check for minimal divergence from Linux reference.
5. Build: `make -f Makefile.multi OS=FREEBSD` + `make -f Makefile.multi OS=LINUX` both succeed.

**Gate**: All slice tests pass. Cross-compile succeeds. Native score ≥ 98.

---

## Phase 5 — Build & Verification Gates

**Objective**: Deterministic cross-compile gates, static analysis, performance regression budgets, maker-checker review.

**Workers**: `native-validator`, `portability-validator`, `performance-engineer`, `code-reviewer` (GroupChat debate)

**Gate Matrix**:

| Gate | Metric | Threshold | Tool |
|------|--------|-----------|------|
| Build Health | Both OS compile | 100% | `make -f Makefile.multi` |
| Native Score | No framework calls | ≥ 98 | `grep` + `clang-tidy` |
| Portability Score | Shared code % | ≥ 95 | `cloc` + diff analysis |
| Test Pass Rate | All tests green | 100% | `make test` |
| Performance | Throughput regression | < 5% | `iperf3` + `pktgen` |
| Static Analysis | Critical findings | 0 | `cppcheck` / Coverity |
| Risk Register | Open criticals | 0 | `risk_register.json` audit |

**GroupChat Debate Protocol**:

1. `native-validator` presents compliance report.
2. `portability-validator` presents cross-compile results.
3. `performance-engineer` presents benchmark deltas.
4. `code-reviewer` challenges any metric below threshold.
5. Vote: ≥3/4 "approve" required to pass. Veto on any critical finding.

**Gate**: All metrics pass. Debate outcome = "approved". Zero critical risks.

---

## Phase 6 — Merge & Upstream Sync

**Objective**: Validate merge readiness, upstream sync policy, and CI integration.

**Workers**: `merge-strategist` (sequential)

**Procedure**

1. **Branch hygiene**: Rebase porting branch onto latest FreeBSD HEAD. Resolve conflicts.
2. **Commit structure**: One commit per ported subsystem slice (Phase 4 slices).
   - Commit format: `mynic: port <subsystem> to native FreeBSD APIs`
   - Each commit compiles and passes tests independently (bisect-safe).
3. **CI pipeline**:
   ```yaml
   stages:
     - build-linux
     - build-freebsd
     - test-unit
     - test-integration
     - gate-check
   ```
4. **Upstream sync plan**:
   - Document which Linux commits to track (subscribe to `drivers/net/ethernet/<vendor>/`).
   - Define merge cadence (quarterly or per-release).
   - Map Linux-side changes to portable core updates vs. adapter-only changes.
5. **CHANGES.md**: Document all ported subsystems, API mappings, and known limitations.

**Gate**: Clean rebase. All commits bisect-safe. CI green. Portability score ≥ 95.

---

## Phase 7 — Multi-OS Extension Planning

**Objective**: Design isolated shim layers for future OS targets without touching Linux source or FreeBSD port core.

**Workers**: `os-extension-validator` + `risk-auditor-final` (concurrent)

**Targets by priority**:

| OS | Adapter Approach | Key APIs |
|----|-----------------|----------|
| FreeBSD (done) | `ifnet` + `bus_dma` + `mbuf` | Volumes I-IX above |
| Windows/NDIS | `NDIS_HANDLE` + `NdisMAllocateSharedMemory` | NDIS 6.x miniport |
| DPDK PMD | `rte_eth_dev` + `rte_mbuf` + `rte_mempool` | User-space only |
| illumos/Solaris | `mac_register` + `ddi_dma_*` + `mblk_t` | GLDv3 framework |

**Procedure**

1. **Extension template**: Create `os/<target>/oal_<target>.h` with the same inline wrapper pattern as FreeBSD.
2. **Build matrix**: Extend `Makefile.multi` with `OS=WINDOWS`, `OS=DPDK`, etc.
3. **Validate isolation**: Confirm zero changes needed in `core/` or `os/freebsd/` when adding a new OS target.
4. **Risk audit (final)**: Full sweep of risk register. All mitigations verified. Zero open criticals.
5. **Architecture decision record**: Document which approach was chosen for each future target and why.

**Gate**: Extension template compiles. Core untouched. Portability score ≥ 95. Risk register clean.

---

**VOLUME I – Architectural Foundations, Linux Dataplane Extraction & Native Porting Strategy**  

**Why this architecture is superior**  
Most Linux NIC drivers (ixgbe, i40e, ice, e1000e) mix OS-specific code with hardware logic. This creates massive divergence when porting. By extracting only the dataplane (RX/TX rings, DMA, interrupts, RSS, TSO, checksum offload) into a portable core, we isolate the hardware behaviour. The FreeBSD adapter becomes a thin translation layer that never touches descriptor formats or offload logic. This reduces maintenance cost by ~80% and makes the driver behave identically on both OSes.

**Included in dataplane port (everything else excluded)**

- RX/TX descriptor rings and packet buffer management  
- DMA mapping and sync  
- Interrupt handling and moderation  
- RSS queue assignment  
- TSO, checksum offload, VLAN offload  

**Excluded (handled by FreeBSD kernel or device firmware)**  
- PHY management, link negotiation, firmware loading, device configuration  

**The three strict layers (text diagram)**  

```text
+-----------------------------+
| FreeBSD Native Adapter      |
| ifnet, mbuf, bus_dma,       |
| taskqueue, MSI-X            |
+-----------------------------+
              ▲
              │ (thin calls only)
              │
+-----------------------------+
| Portable NIC Core           |
| tx_ring.c, rx_ring.c,       |
| descriptor.c, offload.c     |
| (ZERO OS calls)             |
+-----------------------------+
              ▲
              │
+-----------------------------+
| Hardware Registers & DMA    |
| registers.h, dma_engine.c   |
+-----------------------------+
```

**Step-by-step Linux extraction process (detailed walkthrough)**  
1. Identify the reference Linux driver (e.g. `drivers/net/ethernet/intel/ixgbe/`).  
2. Copy only `ixgbe_txrx.c` and `ixgbe_ring.c` into a new directory.  
3. Remove every reference to `struct net_device`, `struct sk_buff`, `NAPI`, `netif_`, `dma_map_single` (Linux-specific).  
4. Replace with portable types (see Volume III).  
5. Keep every register write, descriptor format, and offload calculation exactly as in Linux – this is the guarantee of behavioural identity.  

**Common pitfalls & mitigations**  
- Pitfall: Accidentally leaving a `sk_buff` reference → Mitigation: grep for `skb` and replace with `struct nic_packet` before compilation.  
- Pitfall: DMA mapping API mismatch → Mitigation: abstract every DMA call behind `nic_dma_map()` in the portable core.  

**Deliverable of Volume I**: A clean directory containing the extracted Linux dataplane files with all OS-specific code removed, ready for portable core conversion.

---

**VOLUME II – Designing & Implementing the Framework-Independent Portable NIC Core**  

**Rationale**  
The portable core must compile on any OS or even user-space without changes. It owns all hardware knowledge (descriptor layout, ring arithmetic, offload flags) but never calls `malloc`, `dma_map`, or `printk`. This is the single source of truth for the NIC behaviour.

**Packet structure (heavily commented)**  
```c
/* Portable packet descriptor – owns the buffer and DMA address.
   Memory ownership rule: the adapter allocates, the core only reads/writes. */
struct nic_packet {
    void     *data;      /* virtual pointer (mbuf->m_data or sk_buff->data) */
    uint32_t  len;       /* packet length */
    uint64_t  dma_addr;  /* physical address for NIC DMA */
    void     *os_priv;   /* opaque pointer back to mbuf/sk_buff for completion */
};
```

**Descriptor definitions (exact Intel-style, commented)**

```c
struct nic_tx_desc {
    uint64_t addr;      /* buffer DMA address */
    uint16_t length;    /* length in bytes */
    uint8_t  cmd;       /* command flags (EOP, RS, etc.) */
    uint8_t  status;    /* hardware writes DONE bit here */
    /* ... additional offload fields identical to Linux driver */
};

struct nic_rx_desc {
    uint64_t addr;      /* buffer DMA address written by driver */
    uint16_t length;    /* packet length written by hardware */
    uint16_t csum;      /* hardware checksum */
    uint8_t  status;    /* DD + EOP bits */
    uint8_t  errors;
};
```

**TX ring model – detailed explanation**  
The ring is a circular buffer. `head` is advanced by hardware (completion), `tail` by driver (submission). We never overwrite uncompleted descriptors.  

**TX submit function (expanded with rationale)**

```c
/* Returns 0 on success, -ENOSPC when ring full.
   Rationale: we check next pointer before write – classic lock-free ring pattern.
   No OS calls inside this function. */
int nic_tx_submit(struct nic_tx_ring *r, struct nic_packet *pkt)
{
    uint16_t next = (r->tail + 1) % r->size;

    if (next == r->head)          /* ring full – hardware has not completed */
        return -ENOSPC;

    struct nic_tx_desc *d = &r->desc[r->tail];
    d->addr   = pkt->dma_addr;    /* hardware will DMA from here */
    d->length = pkt->len;
    d->cmd    = CMD_EOP | CMD_RS; /* end of packet + report status */
    d->status = 0;

    r->pkts[r->tail] = pkt;       /* store for later free on completion */
    r->tail = next;               /* advance tail – hardware sees new work */

    return 0;
}
```

**RX poll function (detailed)**  
The driver polls the status bit written by hardware. When a packet is ready, we hand the `nic_packet` back to the adapter for `if_input`.

**Full ring structures** (with cache-line padding rationale)

```c
struct nic_tx_ring {
    struct nic_tx_desc *desc;     /* DMA-coherent descriptor array */
    struct nic_packet  **pkts;    /* back-pointers for completion */
    uint16_t head;                /* hardware progress */
    uint16_t tail;                /* driver submission */
    uint16_t size;                /* power-of-two for fast modulo */
    /* padding to 64-byte cache line boundary follows in real code */
};
```

**Pitfalls & mitigations**  

- Pitfall: Ring wrap-around bug when size is not power-of-two → Mitigation: enforce `size` must be power-of-two and use bitwise AND.  
- Pitfall: Forgetting to store packet pointer → Mitigation: every TX descriptor write is paired with `r->pkts[r->tail] = pkt`.

**Deliverable of Volume II**: Complete `tx_ring.c`, `rx_ring.c`, `descriptor.c`, `offload.c` – all pure portable C that can be compiled on any platform.

---

**VOLUME III – FreeBSD Native Adapter Layer & Driver Skeleton**  

**Why pure native FreeBSD APIs**  
FreeBSD provides clean, well-documented interfaces (`ifnet(9)`, `bus_dma(9)`, `mbuf(9)`). Using them directly gives full control and maximum performance without any translation layer overhead.

**Driver layout (recommended)**  
```
sys/dev/mynic/
├── mynic.c          /* attach/detach, ifnet registration */
├── mynic_tx.c       /* if_transmit and completion */
├── mynic_rx.c       /* refill and if_input */
├── mynic_intr.c     /* MSI-X + taskqueue */
├── mynic_hw.c       /* register access */
├── mynic.h          /* softc and ring structures */
```

**Core softc structure (expanded)**  
```c
struct mynic_softc {
    device_t               dev;
    if_t                   ifp;           /* the network interface */
    struct resource       *mem_res;       /* BAR0 MMIO */
    bus_space_tag_t        bst;
    bus_space_handle_t     bsh;

    struct nic_tx_ring     tx_ring[4];    /* up to 4 queues */
    struct nic_rx_ring     rx_ring[4];

    bus_dma_tag_t          dmat;          /* parent DMA tag */
    struct resource       *irq_res[4];    /* MSI-X vectors */
    void                  *intr_cookie[4];
    struct taskqueue      *tq;            /* NAPI-style deferred processing */
};
```

**Device attach – step-by-step with rationale**  
1. Allocate softc.  
2. Map BAR0.  
3. Allocate `ifnet`.  
4. Set `if_transmit`, `if_init`, `if_ioctl`.  
5. Call `ether_ifattach`.  
6. Initialise DMA tags and rings (detailed in Volume IV).  
7. Set up MSI-X and taskqueue (Volume V).  

**Rationale for if_transmit**  
`if_transmit` is the modern FreeBSD entry point. It receives an `mbuf` chain and must either accept or return `ENOBUFS`. We convert the mbuf to a portable `nic_packet` and hand it to the core.

**Complete attach code with comments** (excerpt)  
```c
static int
mynic_attach(device_t dev)
{
    struct mynic_softc *sc = device_get_softc(dev);
    sc->dev = dev;

    /* Map MMIO BAR – rationale: all hardware access goes through bus_space */
    bus_set_resource(dev, SYS_RES_MEMORY, 0, 0, ~0);
    sc->mem_res = bus_alloc_resource_any(dev, SYS_RES_MEMORY, &rid, RF_ACTIVE);

    /* Allocate network interface – this registers the device with the stack */
    sc->ifp = if_alloc(IFT_ETHER);
    if_initname(sc->ifp, device_get_name(dev), device_get_unit(dev));
    sc->ifp->if_softc     = sc;
    sc->ifp->if_flags     = IFF_BROADCAST | IFF_SIMPLEX | IFF_MULTICAST;
    sc->ifp->if_transmit  = mynic_transmit;   /* our entry point */
    sc->ifp->if_init      = mynic_init;
    ether_ifattach(sc->ifp, NULL);

    /* Now initialise portable rings (Volume IV) */
    mynic_dma_init(sc);
    mynic_tx_init(sc);
    mynic_rx_init(sc);

    return 0;
}
```

**Pitfall**: Forgetting `if_free` on error path → Mitigation: always pair `if_alloc` with `if_free` in error handling.

**Deliverable of Volume III**: A compilable skeleton module that attaches cleanly (`kldload mynic.ko` succeeds).

---

**VOLUME IV – DMA Engine, Memory Management & Descriptor Ring Implementation**  

This volume is the **heart of the port**. It translates the portable NIC core’s abstract ring operations into real FreeBSD kernel memory and DMA semantics. Every byte the NIC sees on the wire is prepared here using only the official `bus_dma(9)` API, `mbuf(9)` clusters, and direct bus-space access. No third-party libraries, no iflib, no LinuxKPI, no pre-allocated bounce buffers beyond what FreeBSD itself decides.  

**Why this volume deserves extreme detail**  
DMA mistakes are the #1 cause of silent data corruption, random panics, IOMMU faults, and performance cliffs in NIC drivers. By making every allocation, mapping, sync, and unload step explicit and heavily commented, we guarantee:
- Zero-copy paths on every packet (the NIC DMAs directly from mbuf clusters).  
- Correct IOMMU handling on systems with VT-d or AMD-Vi.  
- Proper cache coherency (no stale data, no false-sharing).  
- Clean error unwinding on attach failure (no memory leaks).  
- Easy debugging with `bus_dma` tracing and `vmstat -z`.  

**Core Principles Enforced in This Volume**  
1. All descriptor memory must be **coherent** (hardware and CPU see the same view).  
2. Packet buffers must be **mappable** and pre-loaded into the RX ring before the interface is brought up.  
3. Every DMA transaction is bracketed by explicit `bus_dmamap_sync()` calls with the correct direction.  
4. Ring sizes are always powers of two (fast modulo with bitwise AND).  
5. 64-byte cache-line alignment on every ring structure to eliminate false-sharing under multi-queue load.  

**1. DMA Tag Hierarchy (Full Rationale & Code)**  

FreeBSD uses a parent-child DMA tag model. We create one top-level tag from the device, then child tags for descriptors and buffers. This lets the kernel automatically handle bounce buffering on 32-bit systems or when alignment requirements are violated.

```c
/* mynic_dma_init() – called once from mynic_attach() */
void
mynic_dma_init(struct mynic_softc *sc)
{
    int error;

    /* Parent tag – inherits from PCI device. 1-byte alignment, 64 KB max segment
       (modern Intel/Realtek NICs never need larger). No restrictions on address. */
    error = bus_dma_tag_create(
        bus_get_dma_tag(sc->dev),   /* parent from PCI */
        1, 0,                       /* alignment, boundary */
        BUS_SPACE_MAXADDR,          /* lowaddr  (any 64-bit) */
        BUS_SPACE_MAXADDR,          /* highaddr */
        NULL, NULL,                 /* filter, filterarg */
        4096 * 1024,                /* maxsize – generous for multi-queue */
        1,                          /* nsegments */
        BUS_SPACE_MAXSIZE,          /* maxsegsize */
        0,                          /* flags */
        NULL, NULL,                 /* lockfunc, lockarg */
        &sc->dmat);                 /* output tag */

    if (error)
        goto fail;

    /* TX descriptor ring tag – must be coherent (NIC reads/writes status bits) */
    error = bus_dma_tag_create(sc->dmat, 64, 0,
        BUS_SPACE_MAXADDR, BUS_SPACE_MAXADDR,
        NULL, NULL,
        sc->tx_ring_size * sizeof(struct nic_tx_desc),
        1, BUS_SPACE_MAXSIZE, 0, NULL, NULL, &sc->tx_dmat);
    if (error) goto fail;

    /* Same for RX descriptor ring */
    error = bus_dma_tag_create(sc->dmat, 64, 0,
        BUS_SPACE_MAXADDR, BUS_SPACE_MAXADDR,
        NULL, NULL,
        sc->rx_ring_size * sizeof(struct nic_rx_desc),
        1, BUS_SPACE_MAXSIZE, 0, NULL, NULL, &sc->rx_dmat);
    if (error) goto fail;

    /* RX buffer tag – for mbuf clusters (packet payload) */
    error = bus_dma_tag_create(sc->dmat, 1, 0,
        BUS_SPACE_MAXADDR, BUS_SPACE_MAXADDR,
        NULL, NULL, MCLBYTES, 1, MCLBYTES, 0, NULL, NULL, &sc->rx_buf_dmat);
    if (error) goto fail;

    return;

fail:
    device_printf(sc->dev, "DMA tag creation failed: %d\n", error);
    /* cleanup tags already created – see mynic_detach for pattern */
}
```

**2. Descriptor Ring Allocation (TX & RX)**  

We allocate coherent memory once at attach and never resize. The portable core only sees a virtual pointer to the descriptor array.

```c
static int
mynic_tx_ring_alloc(struct mynic_softc *sc, int qid)
{
    struct nic_tx_ring *ring = &sc->tx_rings[qid];

    /* Allocate coherent memory for descriptors */
    ring->desc = NULL;
    int error = bus_dmamem_alloc(sc->tx_dmat, (void **)&ring->desc,
                                 BUS_DMA_COHERENT | BUS_DMA_ZERO,
                                 &ring->desc_map);
    if (error)
        return error;

    /* Load the mapping (gets physical address for hardware) */
    error = bus_dmamap_load(sc->tx_dmat, ring->desc_map, ring->desc,
                            sc->tx_ring_size * sizeof(struct nic_tx_desc),
                            mynic_dmamap_cb, &ring->desc_paddr, 0);
    if (error) {
        bus_dmamem_free(sc->tx_dmat, ring->desc, ring->desc_map);
        return error;
    }

    /* Back-pointer array for mbufs (not DMA-visible) */
    ring->pkts = malloc(sc->tx_ring_size * sizeof(struct nic_packet *),
                        M_DEVBUF, M_WAITOK | M_ZERO);

    ring->head = ring->tail = 0;
    ring->size = sc->tx_ring_size;   /* power-of-two enforced at attach */

    return 0;
}
```

**RX ring allocation** is similar, but we immediately populate it with mbuf clusters (see section 3).

**3. RX Buffer Pre-Population & Refill Strategy**  

This is the most performance-critical part. We pre-fill the entire RX ring at interface-up time and refill on every completion. The portable core’s `nic_rx_desc_write()` function only writes the DMA address into the descriptor – the FreeBSD adapter supplies the address and owns the mbuf lifetime.

```c
static int
mynic_rx_ring_populate(struct mynic_softc *sc, int qid)
{
    struct nic_rx_ring *ring = &sc->rx_rings[qid];

    for (int i = 0; i < ring->size; i++) {
        struct mbuf *m = m_getcl(M_WAITOK, MT_DATA, M_PKTHDR);
        if (!m)
            return ENOBUFS;

        bus_dma_segment_t seg;
        int nsegs;
        int error = bus_dmamap_load_mbuf_sg(sc->rx_buf_dmat,
                                            ring->buf_map[i],
                                            m, &seg, &nsegs, BUS_DMA_NOWAIT);
        if (error) {
            m_freem(m);
            return error;
        }

        /* Store for later free & refill */
        ring->mbuf[i] = m;
        ring->dma_addr[i] = seg.ds_addr;

        /* Tell portable core to write descriptor */
        nic_rx_desc_write(ring, i, seg.ds_addr);
    }

    /* Prime the hardware tail pointer */
    bus_space_write_4(sc->bst, sc->bsh, REG_RDT, ring->size - 1);
    return 0;
}
```

**Refill after packet consumption** (called from taskqueue):
```c
static void
mynic_rx_refill(struct mynic_softc *sc, int qid)
{
    struct nic_rx_ring *ring = &sc->rx_rings[qid];

    while (ring->free_slots > 0) {
        struct mbuf *m = m_getcl(M_NOWAIT, MT_DATA, M_PKTHDR);
        if (!m)
            break;                     /* let next interrupt try again */

        /* ... same load as above ... */

        ring->mbuf[ring->tail] = m;
        nic_rx_desc_write(ring, ring->tail, seg.ds_addr);
        ring->tail = (ring->tail + 1) % ring->size;
        ring->free_slots--;
    }
}
```

**4. DMA Sync Discipline (The Most Important Rule)**  

Never forget sync. The pattern is fixed:

- Before giving a buffer to hardware: `BUS_DMASYNC_PREWRITE`  
- After hardware has written (RX) or read (TX completion): `BUS_DMASYNC_POSTREAD` or `BUS_DMASYNC_POSTWRITE`

```c
/* Before submitting TX descriptor */
bus_dmamap_sync(ring->dmat, ring->map, BUS_DMASYNC_PREWRITE);

/* After hardware completion (TX) */
bus_dmamap_sync(ring->dmat, ring->map, BUS_DMASYNC_POSTWRITE);
bus_dmamap_unload(...);
m_freem(ring->pkts[i]);
```

**5. Unload & Cleanup (Detach Path – Leak-Proof)**  

```c
static void
mynic_tx_ring_free(struct mynic_softc *sc, int qid)
{
    struct nic_tx_ring *ring = &sc->tx_rings[qid];

    if (ring->desc) {
        bus_dmamap_sync(sc->tx_dmat, ring->desc_map, BUS_DMASYNC_POSTWRITE);
        bus_dmamap_unload(sc->tx_dmat, ring->desc_map);
        bus_dmamem_free(sc->tx_dmat, ring->desc, ring->desc_map);
    }

    for (int i = 0; i < ring->size; i++) {
        if (ring->pkts[i] && ring->pkts[i]->os_priv)
            m_freem((struct mbuf *)ring->pkts[i]->os_priv);
    }

    free(ring->pkts, M_DEVBUF);
}
```

**6. Cache-Line Alignment & Performance Tuning**  

Every ring structure is padded:

```c
struct nic_tx_ring {
    struct nic_tx_desc *desc __aligned(64);
    uint16_t head __aligned(64);
    uint16_t tail;
    /* ... */
} __aligned(64);
```

This eliminates false-sharing when multiple queues run on different cores.

**7. Debugging Tools & Common Pitfalls (Expanded)**  

- Enable `hw.pci.enable_msix=1` and `dev.mynic.0.debug=1` (custom sysctl).  
- Use `busdma` tracing: `sysctl debug.busdma=1`.  
- Pitfall: Forgetting to unload DMA map before freeing mbuf → panic in `mbuf` zone. Mitigation: always pair `load` with `unload` inside the completion path.  
- Pitfall: 32-bit systems with >4 GB RAM → bounce buffers appear automatically; monitor `vmstat -z | grep bounce`.  
- Pitfall: RX ring not refilled fast enough under flood → visible as dropped packets in `ifconfig`. Mitigation: pre-allocate 2× ring size mbuf clusters at attach.  

**8. Integration with Portable Core**  

The portable core never sees a `bus_dma` call. It only receives a `uint64_t dma_addr` and writes it into the descriptor. The FreeBSD adapter is the only place that ever calls `bus_dmamap_load` or `bus_dmamap_sync`.

**Deliverables of this Expanded Volume IV**  
- Complete `mynic_dma.c` with all tag creation, ring allocation, population, refill, sync, and unload functions.  
- Heavily commented reference implementation ready to drop into any Intel-style NIC port.  
- Unit-test hooks (CppUTest) that verify every DMA map is loaded/unloaded exactly once.  
- Performance checklist: zero-copy confirmed via `tcpdump -i mynic0` + `netstat -I mynic0` showing no software copies.  

This volume, when combined with Volumes III and V, gives you a rock-solid DMA foundation that survives 100 Gbps line-rate stress, IOMMU-enabled systems, and hot-unplug scenarios. The next volume (Interrupts) builds directly on the rings created here.  

You now have production-grade DMA and ring management using only native FreeBSD kernel APIs.

---

**VOLUME V – Transmit Path Porting & Zero-Copy Handling**

This volume transforms the Linux `ndo_start_xmit` entry point into FreeBSD’s modern `if_transmit` callback while preserving **100 % zero-copy** behaviour and **exact hardware descriptor compatibility** with the original Linux driver.  

The TX path is the **performance-critical producer side**: every packet the stack (or user-space application) hands us must reach the wire with zero memory copies, correct offload flags, and minimal latency. By using only native `bus_dma(9)` + `mbuf(9)` APIs and calling the portable core’s `nic_tx_submit()` function, we guarantee identical wire behaviour to the Linux reference driver while giving the FreeBSD stack full control over packet lifetime.

**Why this volume is the zero-copy gatekeeper**  
Any copy in the TX hot path destroys 10–100 Gbps performance. FreeBSD’s `bus_dmamap_load_mbuf_sg` maps the mbuf cluster directly into the NIC’s DMA address space. The portable core never sees an mbuf — it only receives a `uint64_t dma_addr`. Completion (freeing the mbuf) happens later in the interrupt/taskqueue path (Volume VII), ensuring the mbuf is never freed too early.

**Core Principles Enforced**  
1. **Zero-copy only** — the NIC DMAs straight from the mbuf cluster.  
2. **Per-packet DMA map** (or per-ring slot map) for safe scatter-gather.  
3. **Immediate error unwinding** — if the ring is full or DMA load fails, free the mbuf and return `ENOBUFS`.  
4. **TSO / checksum offload translation** happens before calling the portable core.  
5. **Multi-queue support** with flow-based queue selection (RSS hash or explicit queue).  
6. **Explicit DMA sync** before tail register write.  

**1. From Linux ndo_start_xmit to FreeBSD if_transmit – Full Walkthrough**  

1. Stack calls `if_transmit(ifp, m)` (can be a chain for TSO).  
2. Select TX ring (single-queue or RSS-based multi-queue).  
3. Load mbuf with `bus_dmamap_load_mbuf_sg` → physical address.  
4. Build portable `nic_packet` structure.  
5. Call `nic_tx_submit()` (portable core — identical to Linux).  
6. If successful: `BUS_DMASYNC_PREWRITE` + write tail register.  
7. If ring full or error: unload map + `m_freem(m)` + return error.  

**2. Production-Grade Transmit Function (Multi-Queue, TSO-Aware, Heavily Commented)**  

```c
/* mynic_transmit – the official FreeBSD TX entry point.
   Called by the stack for every packet (or TSO chain). */
static int
mynic_transmit(if_t ifp, struct mbuf *m)
{
    struct mynic_softc *sc = ifp->if_softc;
    int qid;

    /* Multi-queue selection – use RSS hash or explicit queue if set */
    qid = mynic_select_tx_queue(sc, m);   /* portable core can help with hash */
    struct nic_tx_ring *ring = &sc->tx_rings[qid];

    /* Step 1: Zero-copy DMA mapping */
    bus_dma_segment_t segs[MYNIC_MAX_SEGS];   /* support TSO scatter-gather */
    int nsegs;
    int err = bus_dmamap_load_mbuf_sg(ring->dmat, ring->buf_map[ring->tail],
                                      m, segs, &nsegs, BUS_DMA_NOWAIT);
    if (err != 0) {
        m_freem(m);
        ifp->if_oerrors++;
        return ENOBUFS;
    }

    /* Step 2: Prepare portable packet descriptor */
    struct nic_packet pkt = {
        .data     = m,                     /* for debugging only */
        .len      = m->m_pkthdr.len,
        .dma_addr = segs[0].ds_addr,       /* NIC will DMA from here */
        .os_priv  = m,                     /* back-pointer for completion */
        .csum_flags = m->m_pkthdr.csum_flags, /* for offload translation */
    };

    /* Step 3: Let portable core do the hardware work (zero divergence from Linux) */
    if (nic_tx_submit(ring, &pkt) != 0) {
        /* Ring full – hardware has not completed previous packets */
        bus_dmamap_unload(ring->dmat, ring->buf_map[ring->tail]);
        m_freem(m);
        ifp->if_oerrors++;
        return ENOSPC;
    }

    /* Step 4: Sync before hardware sees the descriptor */
    bus_dmamap_sync(ring->dmat, ring->buf_map[ring->tail], BUS_DMASYNC_PREWRITE);

    /* Step 5: Tell hardware new work is ready */
    bus_space_write_4(sc->bst, sc->bsh,
                      REG_TDT + (qid * REG_STRIDE), ring->tail);

    /* Update interface counters */
    ifp->if_opackets++;
    ifp->if_ombytes += m->m_pkthdr.len;

    return 0;
}
```

**3. Queue Selection & TSO / Checksum Offload Translation**  

```c
static int
mynic_select_tx_queue(struct mynic_softc *sc, struct mbuf *m)
{
    /* Simple RSS-style selection or explicit queue */
    if (m->m_pkthdr.flowid)
        return m->m_pkthdr.flowid % sc->num_queues;
    return 0;   /* default queue */
}

/* Offload flags are translated before nic_tx_submit */
if (m->m_pkthdr.csum_flags & CSUM_TSO) {
    pkt.cmd |= CMD_TSO_ENABLE;   /* portable core writes exact bits */
}
if (m->m_pkthdr.csum_flags & (CSUM_IP | CSUM_TCP | CSUM_UDP))
    pkt.cmd |= CMD_CSUM_ENABLE;
```

**4. Per-Descriptor DMA Map Management (Scalable & Safe)**  

Each TX ring slot has its own `bus_dmamap_t` (created in Volume IV). This allows safe unload even if the packet is chained or TSO-segmented.

**5. Completion Path Integration (Called from Taskqueue – Volume VII)**  

```c
/* In mynic_tx_complete (called from taskqueue) */
while (nic_tx_complete(ring) > 0) {   /* portable core */
    struct mbuf *m = (struct mbuf *)ring->pkts[ring->head]->os_priv;
    bus_dmamap_unload(ring->dmat, ring->buf_map[ring->head]);
    m_freem(m);
    ring->pkts[ring->head] = NULL;
    ring->head = (ring->head + 1) % ring->size;
}
```

**6. DMA Sync Discipline for TX**  

- `BUS_DMASYNC_PREWRITE` right before tail write.  
- `BUS_DMASYNC_POSTWRITE` in completion (after hardware has read the buffer).  

**7. Pitfalls & Mitigations (Expanded Production List)**  

- **Pitfall**: mbuf freed before hardware finishes DMA → kernel panic or corruption → **Mitigation**: store `os_priv` in ring and free **only** in `nic_tx_complete`.  
- **Pitfall**: Ring full race under TSO flood → **Mitigation**: check `next == head` **before** DMA load; return `ENOSPC` immediately.  
- **Pitfall**: DMA map leak on error path → **Mitigation**: always pair `load` with `unload` in the failure branch.  
- **Pitfall**: No TSO flag translation → large packets sent as single frame → **Mitigation**: dedicated TDD test sending 64 KB TCP packet and verifying wire capture.  
- **Pitfall**: Single-queue bottleneck → **Mitigation**: RSS-based queue selection + per-queue rings (scales linearly).  

**8. Debugging Tools You Will Use Daily**  

```sh
sysctl dev.mynic.0.tx_debug=1
netstat -I mynic0 -w 1          # watch opackets / obytes
tcpdump -i mynic0 -c 10         # verify TSO segmentation on wire
vmstat -z | grep mbuf           # check cluster usage
busdma -s mynic                 # trace DMA maps
```

**9. Performance Checklist (What “Done” Looks Like)**  

- 64-byte packets: > 14 Mpps per core.  
- 1500-byte TSO: line-rate with < 3 % CPU.  
- Zero `m_copym` or software copies (confirmed by `tcpdump` + `netstat`).  
- `kldunload` succeeds with zero leaks (`vmstat -z`).  

**10. Integration with Other Volumes**  

- Volume IV (DMA) supplies the tags, maps, and `mynic_tx_ring_alloc`.  
- Portable core (Volume II) provides `nic_tx_submit`.  
- Volume VII (Interrupts) calls `nic_tx_complete` from taskqueue.  
- Volume VIII (Offloads) adds the flag translation shown above.  

**Deliverables of this Expanded Volume V**  
- Complete `mynic_tx.c` with `mynic_transmit`, queue selection, TSO translation, multi-queue support, and full error unwinding.  
- Heavily commented reference implementation ready for any modern NIC (Intel, Realtek, Mellanox-style).  
- Sysctl `dev.mynic.0.tx_queue_count` and debug counters.  
- TDD hooks that simulate 1 000 000 packets and verify every mbuf is freed exactly once with correct DMA unload.  
- Ready-to-use zero-copy TX path that achieves wire-speed transmission with zero framework dependencies.

When combined with Volume IV (DMA rings) and Volume VII (interrupts), your driver now has a **complete, production-grade, zero-copy TX path** using only pure native FreeBSD kernel APIs. Packets flow from socket to wire with maximum performance and perfect behavioural fidelity to the original Linux driver.  

The next volume (Receive Path) builds directly on this foundation. You are now one step away from a fully functional driver.

---

**VOLUME VI – Receive Path, Buffer Refill & Packet Delivery**  
**(Expanded Production-Grade Reference – Pure Native FreeBSD Only)**  

This volume is the **RX fast-path heart** of the driver. It is where raw wire packets become mbufs that the FreeBSD networking stack (TCP/IP, sockets, firewalls, etc.) can consume. Every packet the NIC receives must be delivered with zero copies, correct length, checksum status, and VLAN tag information — while the ring is kept 100 % full at all times.  

If the RX path stalls even for a few microseconds, the NIC’s internal FIFO overflows and packets are dropped in hardware. This volume guarantees **zero drops at 100 Gbps line rate** by combining pre-allocation, lock-free refill, direct `if_input` handover, and tight integration with the portable NIC core.

**Why this volume is performance-critical**  
RX is the harder direction: the hardware produces packets asynchronously, the driver must keep the ring populated, and the stack must accept packets without blocking. FreeBSD’s `if_input` callback is the official, zero-overhead handoff point. We never use `mbuf` copying, never allocate inside the hot path, and never touch the portable core’s descriptor logic.

**Core Principles Enforced**  
1. RX ring is **pre-populated** at `if_init` and **refilled immediately** after every packet is delivered.  
2. All buffers are **pre-mapped** with `bus_dmamap_load_mbuf_sg` — the NIC DMAs directly into mbuf cluster memory.  
3. Packet ownership is transferred exactly once: driver → stack via `(*ifp->if_input)`.  
4. DMA sync is explicit and directional (`BUS_DMASYNC_POSTREAD`).  
5. Multi-queue support with per-queue refill (scales to 64 queues).  
6. Pre-allocation pool prevents mbuf exhaustion under flood.

**1. Detailed RX Flow (End-to-End)**  

```
NIC hardware receives Ethernet frame
        ↓ (DMA write into pre-supplied buffer)
Hardware writes length + DD bit into RX descriptor
        ↓
MSI-X interrupt fires (Volume V)
        ↓
Taskqueue schedules mynic_task()
        ↓
nic_rx_poll() walks ring (portable core)
        ↓
if (DD bit set)
    m = ring->mbuf[idx]
    m->m_len = m->m_pkthdr.len = desc->length
    (*sc->ifp->if_input)(sc->ifp, m)   ← ownership transferred
        ↓
mynic_rx_refill() immediately allocates new mbuf + remaps
        ↓
nic_rx_desc_write() updates descriptor (portable core)
        ↓
Advance tail pointer
        ↓
Re-arm hardware interrupt
```

**2. Pre-Allocation Pool (The Anti-Starvation Safety Net)**  

At attach time we allocate a small emergency pool so `m_getcl(M_NOWAIT)` never fails under flood.

```c
/* In mynic_attach() – called once */
static int
mynic_rx_prealloc_pool(struct mynic_softc *sc)
{
    sc->rx_pool = malloc(sizeof(struct mbuf *) * RX_PREALLOC_COUNT,
                         M_DEVBUF, M_WAITOK | M_ZERO);

    for (int i = 0; i < RX_PREALLOC_COUNT; i++) {
        sc->rx_pool[i] = m_getcl(M_WAITOK, MT_DATA, M_PKTHDR);
        if (!sc->rx_pool[i])
            return ENOMEM;
    }
    sc->rx_pool_idx = 0;
    return 0;
}
```

During refill we first try the pool, then fall back to `m_getcl(M_NOWAIT)`.

**3. Full RX Ring Initialization & Population**  

```c
static int
mynic_rx_ring_init(struct mynic_softc *sc, int qid)
{
    struct nic_rx_ring *ring = &sc->rx_rings[qid];

    ring->size       = sc->rx_ring_size;   /* power-of-two */
    ring->head       = 0;
    ring->tail       = 0;
    ring->free_count = ring->size;

    /* Allocate back-pointer array */
    ring->mbuf = malloc(ring->size * sizeof(struct mbuf *),
                        M_DEVBUF, M_WAITOK | M_ZERO);

    /* Allocate per-buffer DMA maps (one per slot) */
    for (int i = 0; i < ring->size; i++) {
        bus_dmamap_create(sc->rx_buf_dmat, 0, &ring->buf_map[i]);
    }

    /* Populate the entire ring at interface-up time */
    return mynic_rx_ring_populate(sc, qid);
}
```

**4. Production Refill Function (Expanded & Heavily Commented)**  

```c
/* Called from taskqueue after every packet is delivered.
   Goal: keep ring 100 % full at all times. */
static void
mynic_rx_refill(struct mynic_softc *sc, int qid)
{
    struct nic_rx_ring *ring = &sc->rx_rings[qid];
    bus_dma_segment_t seg;
    int nsegs, error;

    while (ring->free_count > 0) {
        struct mbuf *m;

        /* First try pre-allocated pool (zero-alloc fast path) */
        if (sc->rx_pool_idx < RX_PREALLOC_COUNT && sc->rx_pool[sc->rx_pool_idx]) {
            m = sc->rx_pool[sc->rx_pool_idx];
            sc->rx_pool[sc->rx_pool_idx++] = NULL;   /* take ownership */
        } else {
            m = m_getcl(M_NOWAIT, MT_DATA, M_PKTHDR);
            if (!m)
                break;   /* ring will temporarily run low – next interrupt will retry */
        }

        /* Map the mbuf cluster for DMA (zero-copy) */
        error = bus_dmamap_load_mbuf_sg(ring->dmat, ring->buf_map[ring->tail],
                                        m, &seg, &nsegs, BUS_DMA_NOWAIT);
        if (error) {
            m_freem(m);
            break;
        }

        /* Store for later free & refill tracking */
        ring->mbuf[ring->tail] = m;

        /* Portable core writes the DMA address into the descriptor */
        nic_rx_desc_write(ring, ring->tail, seg.ds_addr);

        /* Advance our software tail */
        ring->tail = (ring->tail + 1) % ring->size;
        ring->free_count--;
    }

    /* Tell hardware the new tail (only if we added work) */
    if (ring->free_count < ring->size)
        bus_space_write_4(sc->bst, sc->bsh, REG_RDT + qid * REG_STRIDE, ring->tail);
}
```

**5. RX Packet Processing & Delivery (Inside Taskqueue)**  

```c
static void
mynic_rx_process(struct mynic_softc *sc, int qid)
{
    struct nic_rx_ring *ring = &sc->rx_rings[qid];
    struct nic_packet pkt;

    while (nic_rx_poll(ring, &pkt) > 0) {   /* portable core */
        struct mbuf *m = (struct mbuf *)pkt.os_priv;

        /* Finalise mbuf metadata (hardware wrote length & checksum) */
        m->m_len         = pkt.len;
        m->m_pkthdr.len  = pkt.len;
        m->m_pkthdr.csum_flags = pkt.csum_flags;   /* from portable offload */

        /* Hand to FreeBSD stack – ownership transferred forever */
        (*sc->ifp->if_input)(sc->ifp, m);

        /* Immediately refill the slot we just consumed */
        ring->free_count++;   /* make room */
        mynic_rx_refill(sc, qid);
    }
}
```

**6. DMA Sync Discipline for RX**  

```c
/* After nic_rx_poll returns a packet */
bus_dmamap_sync(ring->dmat, ring->buf_map[idx], BUS_DMASYNC_POSTREAD);

/* Before giving the buffer back to hardware in refill */
bus_dmamap_sync(ring->dmat, ring->buf_map[new_tail], BUS_DMASYNC_PREREAD);
```

**7. Multi-Queue RX Support**  

Each queue has its own MSI-X vector and task. The portable core’s RSS logic decides which queue the packet lands in — the adapter only processes the correct ring.

**8. Pitfalls & Mitigations (Expanded Production List)**  

- **Pitfall**: Running out of mbuf clusters under flood → **Mitigation**: pre-allocate 512–1024 clusters at attach + emergency pool + `M_NOWAIT` fallback. Monitored via `sysctl net.mbuf` and driver sysctl `dev.mynic.0.rx_pool_hits`.  
- **Pitfall**: DMA map leak (never unloaded) → **Mitigation**: `bus_dmamap_unload()` in detach and explicit unload before `m_freem`.  
- **Pitfall**: Stale data after DMA write (cache incoherency) → **Mitigation**: mandatory `BUS_DMASYNC_POSTREAD` before reading length.  
- **Pitfall**: Ring tail not updated → packets lost in hardware → **Mitigation**: always write `REG_RDT` after refill.  
- **Pitfall**: `if_input` called with invalid mbuf → kernel panic → **Mitigation**: set `m->m_pkthdr.rcvif = sc->ifp` and validate length > 0.  

**9. Performance Checklist (What “Done” Looks Like)**  

- 64-byte packets at 100 Gbps: zero drops, < 8 % CPU in taskqueue.  
- `netstat -I mynic0` shows `Ipkts` matching wire rate.  
- `vmstat -z | grep mbuf` shows stable cluster usage.  
- Refill loop never hits the slow `m_getcl` path under steady load (pool hit rate > 99 %).  

**10. Integration with Other Volumes**  

- Volume IV (DMA) supplies the tags and maps.  
- Volume V (Interrupts) schedules the taskqueue that calls `mynic_rx_process`.  
- Portable core (Volumes I–II) provides `nic_rx_poll` and `nic_rx_desc_write`.  
- Volume VIII (Offloads) adds checksum/VLAN flags before `if_input`.

**Deliverables of this Expanded Volume VI**  
- Complete `mynic_rx.c` with `mynic_rx_ring_init`, `mynic_rx_process`, `mynic_rx_refill`, pre-allocation pool, and multi-queue support.  
- Heavily commented reference implementation ready for any modern NIC.  
- Sysctl `dev.mynic.0.rx_prealloc` and debug counters.  
- TDD hooks that simulate 1 000 000 packets and verify zero mbuf leaks.  
- Ready-to-use RX path that achieves wire-speed delivery with zero copies.

When combined with other Volumes, your driver now has a **complete, production-grade, zero-copy RX path** using only pure native FreeBSD kernel APIs. Packets flow from wire to socket with maximum performance and zero framework dependencies.  

---

**VOLUME VII – Interrupts, MSI-X, Taskqueues & Completion Handling**

This volume completes the high-performance data path by connecting hardware interrupts to the portable NIC core’s completion routines and the FreeBSD networking stack. Interrupts are the **only** asynchronous bridge between the NIC and the CPU; getting them wrong causes packet drops, high latency, CPU spin, or kernel panics.  

By using **only** official FreeBSD primitives (`pci_alloc_msix(9)`, `bus_setup_intr(9)`, `taskqueue(9)`), we achieve perfect NAPI-style coalescing, zero unnecessary context switches, and full control over moderation — all while the portable core remains completely unaware of the OS.  

**Why this volume is the performance gatekeeper**  
Modern 10–100 GbE NICs can generate millions of interrupts per second. Without proper coalescing and deferred processing, the system either drops packets (RX overrun) or wastes CPU cycles (TX completion flood). FreeBSD’s `taskqueue` is the native, lightweight equivalent of Linux NAPI: it batches work, runs at high priority, and prevents livelock. We tie it directly to the portable core’s `nic_tx_complete()` and `nic_rx_poll()` functions.

**Core Principles Enforced**  
1. MSI-X only (legacy INTx fallback is supported but discouraged for performance).  
2. One MSI-X vector per queue + one shared admin vector (scalable to 64+ queues).  
3. All heavy lifting moved to a dedicated taskqueue thread (no work in hard IRQ context).  
4. Explicit interrupt masking/unmasking via hardware registers (prevents re-entrancy).  
5. Zero-overhead path from interrupt → portable core → `if_input` / TX free.  

**1. MSI-X Vector Allocation & Setup (Full Production Code)**  

```c
/* Called from mynic_attach() after DMA rings are ready */
static int
mynic_intr_setup(struct mynic_softc *sc)
{
    int error, rid;
    int nvec = sc->num_queues + 1;   /* one per queue + admin vector */

    /* Request MSI-X – FreeBSD automatically falls back if not supported */
    error = pci_alloc_msix(sc->dev, &nvec);
    if (error) {
        device_printf(sc->dev, "MSI-X allocation failed (%d), falling back to legacy\n", error);
        nvec = 1;  /* legacy single IRQ */
        /* legacy setup code omitted for brevity – always prefer MSI-X */
    }

    sc->num_msix = nvec;

    /* Allocate per-vector resources */
    for (int i = 0; i < nvec; i++) {
        rid = i + 1;  /* rid 0 is legacy, MSI-X starts at 1 */
        sc->irq_res[i] = bus_alloc_resource_any(sc->dev, SYS_RES_IRQ,
                                                &rid, RF_ACTIVE | RF_SHAREABLE);
        if (!sc->irq_res[i])
            goto fail;

        /* Setup fast interrupt handler – minimal work only */
        error = bus_setup_intr(sc->dev, sc->irq_res[i],
                               INTR_TYPE_NET | INTR_MPSAFE | INTR_EXCL,
                               NULL, mynic_intr, sc, &sc->intr_cookie[i]);
        if (error)
            goto fail;

        /* Name the interrupt for top(1) and dmesg */
        bus_describe_intr(sc->dev, sc->irq_res[i], sc->intr_cookie[i],
                          "q%d", i);
    }

    /* Create taskqueue for deferred processing (NAPI equivalent) */
    sc->tq = taskqueue_create("mynic_taskq", M_WAITOK,
                              taskqueue_thread_enqueue, &sc->tq);
    taskqueue_start_threads(&sc->tq, 1, PI_NET, "%s taskq",
                            device_get_nameunit(sc->dev));

    return 0;

fail:
    mynic_intr_teardown(sc);
    return error;
}
```

**Rationale for INTR_MPSAFE + INTR_EXCL**: Guarantees the handler runs without Giant lock and prevents concurrent execution on the same vector.

**2. The Interrupt Handler – Minimal & Fast**  

```c
/* Hard IRQ context – must be extremely light */
static void
mynic_intr(void *arg)
{
    struct mynic_softc *sc = arg;
    uint32_t icr;

    /* Read Interrupt Cause Register (hardware-specific) */
    icr = bus_space_read_4(sc->bst, sc->bsh, REG_ICR);

    if (icr == 0)               /* spurious */
        return;

    /* Immediately mask interrupts at hardware level */
    bus_space_write_4(sc->bst, sc->bsh, REG_IMC, 0xFFFFFFFF);

    /* Schedule the real work on taskqueue – zero work in IRQ */
    taskqueue_enqueue(sc->tq, &sc->rx_task);   /* single task for all queues */
}
```

**Why no work in IRQ**: Prevents stack overflow, priority inversion, and allows the kernel to coalesce multiple interrupts into one taskqueue run.

**3. Taskqueue Processing – The Real NAPI Heart**  

```c
/* Runs in taskqueue thread context – can sleep, allocate, etc. */
static void
mynic_task(void *arg, int pending)
{
    struct mynic_softc *sc = arg;

    /* Process TX completions first (frees mbufs) */
    for (int q = 0; q < sc->num_queues; q++) {
        nic_tx_complete(&sc->tx_rings[q]);   /* portable core */
    }

    /* Process RX packets */
    for (int q = 0; q < sc->num_queues; q++) {
        struct nic_packet *pkt;
        while (nic_rx_poll(&sc->rx_rings[q], &pkt) > 0) {
            struct mbuf *m = (struct mbuf *)pkt->os_priv;

            /* Final length from hardware */
            m->m_len = m->m_pkthdr.len = pkt->len;

            /* Hand to FreeBSD stack – ownership transferred */
            (*sc->ifp->if_input)(sc->ifp, m);

            /* Refill immediately (keeps ring full) */
            mynic_rx_refill(sc, q);
        }
    }

    /* Re-enable interrupts at hardware level */
    bus_space_write_4(sc->bst, sc->bsh, REG_IMS, 0xFFFFFFFF);
}
```

**Rationale for batching**: `pending` argument tells us how many times the task was scheduled – we can process more packets per run under load.

**4. Completion Handlers from Portable Core (Integration Points)**  

The portable core provides two pure functions:

- `nic_tx_complete(struct nic_tx_ring *r)` – walks from head, frees mbufs when `DESC_DONE` bit is set.  
- `nic_rx_poll(struct nic_rx_ring *r, struct nic_packet **out)` – returns one packet at a time when status bit is set.

Both are **lock-free** and **zero OS calls** — the FreeBSD adapter supplies the mbuf pointer via `os_priv`.

**5. Interrupt Moderation & Coalescing**  

Modern NICs support hardware moderation registers. We expose them via sysctl:

```c
SYSCTL_INT(_dev_mynic, OID_AUTO, itr, CTLFLAG_RW, &sc->itr_value,
           0, "Interrupt Throttle Rate (0 = adaptive)");

/* In attach: */
bus_space_write_4(sc->bst, sc->bsh, REG_ITR, sc->itr_value);
```

Adaptive mode (default) dynamically adjusts based on packet rate — implemented in the taskqueue.

**6. Teardown & Cleanup (Detach Path – Panic-Proof)**  

```c
static void
mynic_intr_teardown(struct mynic_softc *sc)
{
    /* Mask all interrupts first */
    bus_space_write_4(sc->bst, sc->bsh, REG_IMC, 0xFFFFFFFF);

    for (int i = 0; i < sc->num_msix; i++) {
        if (sc->intr_cookie[i]) {
            bus_teardown_intr(sc->dev, sc->irq_res[i], sc->intr_cookie[i]);
            sc->intr_cookie[i] = NULL;
        }
        if (sc->irq_res[i]) {
            bus_release_resource(sc->dev, SYS_RES_IRQ, i+1, sc->irq_res[i]);
        }
    }

    if (sc->tq) {
        taskqueue_drain(sc->tq, &sc->rx_task);
        taskqueue_free(sc->tq);
    }

    pci_release_msi(sc->dev);   /* frees MSI-X vectors */
}
```

**7. Debugging Tools & Common Pitfalls (Expanded Production List)**  

**Pitfalls & Exact Mitigations**  
- **Pitfall**: Interrupt storm after detach → Mitigation: mask hardware interrupts *before* tearing down taskqueue.  
- **Pitfall**: Missed completions under high load → Mitigation: always re-arm `REG_IMS` at the *end* of taskqueue, never in the middle.  
- **Pitfall**: Taskqueue thread pinned to wrong CPU → Mitigation: `taskqueue_start_threads` with PI_NET priority; use `cpuset` for queue affinity if needed.  
- **Pitfall**: Spurious interrupts on legacy IRQ fallback → Mitigation: always check `icr == 0` and return immediately.  
- **Pitfall**: RX starvation (no refill) → Mitigation: call `mynic_rx_refill` inside the same taskqueue loop after every `nic_rx_poll`.  

**Debugging commands you will use daily**  
```sh
sysctl dev.mynic.0.debug=1          # enable driver debug prints
vmstat -i                           # see interrupt rate
top -P                              # watch taskqueue thread CPU
netstat -I mynic0 -w 1              # packets per second
dmesg | grep mynic                  # MSI-X allocation messages
```

**8. Integration with Portable Core & Previous Volumes**  

- Volume IV (DMA rings) must be fully populated before `mynic_intr_setup`.  
- Portable core’s `nic_tx_complete` and `nic_rx_poll` are called directly from the taskqueue — zero glue code needed.  
- TX completion path frees the exact mbuf stored in `ring->pkts[]` (ownership never lost).  

**9. Performance Checklist (What “Done” Looks Like)**  

- Under 100 Gbps flood: < 5 % CPU in softirq/taskqueue.  
- Latency: < 8 µs p99 for 64-byte packets (measured with `pktgen`).  
- No packet drops in `ifconfig mynic0` counters even at line rate.  
- `kldunload` succeeds with zero memory leaks (`vmstat -z | grep mbuf`).  

**Deliverables of this Expanded Volume V**  
- Complete `mynic_intr.c` with MSI-X setup, fast handler, taskqueue, and full teardown.  
- Heavily commented reference implementation ready for any Intel-style or Realtek-style NIC.  
- Sysctl knobs for moderation and debug.  
- Unit-test hooks that simulate 10 000 interrupts and verify every mbuf is freed exactly once.  
- Ready-to-use `mynic_task()` that integrates seamlessly with Volumes III, IV, and VI.  

When you finish this volume, your driver is **fully functional** — packets flow end-to-end at wire speed using only pure native FreeBSD kernel APIs. The next volume (Offloads) simply adds flag translation inside the same paths you just built.  

You now have production-grade interrupt handling that matches or exceeds the original Linux driver’s performance and stability.

---

**VOLUME VIII – Hardware Offloads: RSS, TSO, Checksum**  

**RSS configuration**  
Write the indirection table and hash key registers exactly as the Linux driver does. FreeBSD stack reads the queue via `if_rxr`.

**TSO & checksum offload**  
Set `CSUM_TSO` and `CSUM_IP` flags on mbuf; the portable core translates them into descriptor command bits (identical to Linux).

**Detailed offload flag translation**  
```c
if (m->m_pkthdr.csum_flags & CSUM_TSO)
    desc->cmd |= CMD_TSO;   /* hardware does segmentation */
```

**Pitfall**: Wrong flag mapping → Mitigation: dedicated unit test that sends a 64 KB TCP packet and verifies wire capture shows correct segmentation.

---

**VOLUME IX – Rigorous TDD Strategy, Performance Tuning, Debugging, Validation & Production Readiness**  
**(Expanded Production-Grade Reference – Pure Native FreeBSD Only)**  

This final volume turns your driver from “works on my machine” into **production-deployable, maintainable, and future-proof**. It enforces TDD-first development, applies lock-less performance tuning, maintains a living risk register, provides professional debugging tools, and ends with a comprehensive validation checklist that every release must pass.  

Everything here uses **only** native FreeBSD kernel facilities: `CppUTest` (user-space unit tests), kernel test framework hooks, `sysctl`, `vmstat`, `busdma` tracing, and standard `make`. No external frameworks, no LinuxKPI, no DPDK testpmd — just pure FreeBSD.

**Why this volume is non-negotiable**  
A NIC driver that crashes under flood, leaks memory, or silently corrupts packets is useless in production. TDD catches logic errors before they reach hardware. Lock-less techniques deliver 100 Gbps line-rate. The living risk register prevents regressions forever. The validation checklist guarantees every commit is release-ready. Together they make the driver cheaper to maintain than the original Linux version.

**Core Principles Enforced**  
1. **TDD-first**: Every new function or change starts with a failing test.  
2. **Lock-less everywhere** in hot paths (no mutex in TX/RX).  
3. **Living risk register** updated by every developer and CI run.  
4. **Zero memory leaks** and zero drops under sustained stress.  
5. **Full traceability** via sysctls, debug prints, and hardware counters.  

**1. TDD-First Development Strategy (Full Workflow)**  

Every volume in this guide was built using strict TDD. Here is the exact process you must follow for any new code:

```c
/* tests/mynic_tdd_test.c – CppUTest example (user-space) */
TEST_GROUP(TxPath);
TEST(TxPath, RingFullReturnsENOSPC)
{
    struct nic_tx_ring ring;
    mynic_tx_ring_init_test(&ring, 4);   /* 4-slot test ring */

    struct nic_packet pkt = { .len = 64 };
    CHECK(nic_tx_submit(&ring, &pkt) == 0);   /* first packet OK */
    CHECK(nic_tx_submit(&ring, &pkt) == 0);
    CHECK(nic_tx_submit(&ring, &pkt) == 0);
    CHECK(nic_tx_submit(&ring, &pkt) == 0);
    CHECK(nic_tx_submit(&ring, &pkt) == -ENOSPC);   /* must fail */
}
```

**Kernel-side test hook** (in `mynic.c` for `make test`):
```c
static void
mynic_test_mode(void)
{
    /* Called from sysctl dev.mynic.0.test=1 */
    mynic_run_all_tdd_tests();
}
```

**Workflow**  
1. Write failing test (red).  
2. Implement minimal code to make it pass (green).  
3. Refactor while keeping all tests green.  
4. Commit only when 100 % pass.  

All 500+ tests (unit + integration + stress) are in `tests/` and run with `make test`.

**2. Performance Tuning – Lock-Less Techniques (Production Code)**  

```c
/* 64-byte cache-line alignment on every hot structure */
struct nic_tx_ring {
    struct nic_tx_desc *desc __aligned(64);
    uint16_t head          __aligned(64);   /* hardware progress */
    uint16_t tail;                          /* driver submission */
    /* ... */
} __aligned(64);

/* Lock-less TX submit (called from if_transmit) */
static inline int
mynic_tx_submit_lockless(struct nic_tx_ring *ring, struct nic_packet *pkt)
{
    uint16_t next = (ring->tail + 1) & (ring->size - 1);   /* power-of-two */

    if (next == atomic_load_acq_16(&ring->head))
        return -ENOSPC;

    /* Portable core does descriptor write */
    if (nic_tx_submit(ring, pkt) != 0)
        return -ENOSPC;

    /* Memory barrier + atomic advance */
    atomic_store_rel_16(&ring->tail, next);
    return 0;
}

/* Prefetch in RX poll loop */
while (nic_rx_poll(ring, &pkt) > 0) {
    __builtin_prefetch(ring->mbuf[ring->head + 8]);   /* next 8 packets */
    /* ... deliver packet */
}
```

**Batch processing** (in taskqueue):
```c
#define BATCH_SIZE 32
for (int i = 0; i < BATCH_SIZE && nic_rx_poll(...) > 0; i++) { ... }
```

These three techniques alone deliver > 99.7 % of theoretical line-rate while remaining 100 % portable.

**3. Living Risk Register (Full Production Table Excerpt)**  

The register is a Markdown + JSON file updated by every developer and CI run. Current top risks:

| ID | Risk | Severity | Likelihood | Mitigation (OAL macro + TDD) | Recovery |
|----|------|----------|------------|------------------------------|----------|
| R-01 | DMA sync omitted | Critical | High | `OS_DMA_SYNC()` macro + failing TDD that panics without it | Native Validator auto-rejects |
| R-02 | Ring full race | Critical | Medium | Atomic head/tail + memory barrier | TDD stress test with 1M packets |
| R-03 | mbuf freed too early | Critical | High | Store in `ring->pkts[]`, free only in completion | TDD verifies every mbuf freed exactly once |
| R-04 | mbuf exhaustion under flood | High | High | Pre-alloc pool + `M_NOWAIT` fallback | Monitored via sysctl `dev.mynic.0.rx_pool_hits` |
| R-05 | Interrupt storm on detach | High | Medium | Mask hardware before teardown | Detach TDD runs `kldunload` 1000× |

**Full register** lives in `docs/risk_register.md` and is audited by `make risk-audit`.

**4. Professional Debugging Toolkit**  

```sh
# Enable everything
sysctl dev.mynic.0.debug=3
sysctl debug.busdma=1

# Real-time stats
watch -n 1 "netstat -I mynic0 -w 1"

# DMA map tracing
busdma -s mynic

# Packet capture with hardware timestamps
tcpdump -i mynic0 -j adapter -c 100
```

Custom sysctls you get:
- `dev.mynic.0.tx_batch_size`
- `dev.mynic.0.rx_prealloc`
- `dev.mynic.0.dump_ring` (prints current head/tail)

**5. Final Validation Checklist (All Items Must Pass)**  

**Phase 0–4 Foundation**  
- [ ] Clean compile on FreeBSD HEAD  
- [ ] `kldload` / `kldunload` 1000× without panic  
- [ ] All TDD tests (500+) pass  

**Performance & Stability**  
- [ ] `ifconfig mynic0 up` + `ping -f 192.168.1.1` succeeds  
- [ ] `pktgen` 64-byte flood: ≥ 14 Mpps, zero drops  
- [ ] 1500-byte TSO line-rate sustained 10 minutes  
- [ ] `vmstat -z | grep mbuf` shows stable usage (no leaks)  
- [ ] `vmstat -m | grep mynic` shows zero memory growth  

**Offloads & Features**  
- [ ] Hardware checksum verified with `tcpdump`  
- [ ] TSO verified with 64 KB TCP packet  
- [ ] RSS distributes across all queues (`top -P`)  
- [ ] Multi-queue under flood: < 8 % CPU per core  

**Risk & Safety**  
- [ ] Risk register audit passes (zero critical open)  
- [ ] `make stress` (1M packets + repeated unload) passes  
- [ ] No DMA map leaks (`busdma` trace clean)  

**Production Build & Install**  
```sh
cd /usr/src/sys/modules/mynic
make -j$(sysctl -n hw.ncpu) && make install
kldload mynic
ifconfig mynic0 inet 192.168.1.10/24 up
```

**6. Integration & Release Process**  

- Run `make test-all` (TDD + stress + risk audit).  
- Commit only if checklist is 100 % green.  
- Tag release with `git tag v2026.03-port`.  

**Deliverables of this Expanded Volume IX**  
- Complete `tests/` directory with 500+ TDD tests.  
- Full `docs/risk_register.md` + JSON + audit script.  
- `mynic_sysctl.c` with all debug and tuning knobs.  
- `Makefile` targets: `test`, `stress`, `risk-audit`, `validate-full`.  
- Production-ready release checklist and build script.  
- Final checkpoint that declares the driver production-grade.

**LangGraph Python Orchestrator**: See `ai-agent-orchestration-template.py` in the repository root.

**End of the Nine-Volume Guide**

---

## Appendix A: FPGA Porting Case Study — ixgbe PF Driver (`if_ix`)

> Porting FPGA emulation support from an out-of-tree ixgbe driver into the in-tree FreeBSD ixgbe PF driver (`if_ix`).

### Context

- **Out-of-tree driver**: Legacy ixgbe (non-iflib) with FPGA logic guarded by `#ifdef FPGA_SUPPORT`.
- **In-tree driver**: FreeBSD iflib-based ixgbe PF driver (`sys/dev/ixgbe/if_ix.c`). Shares common HW code with VF (`if_ixv`). Currently lacks FPGA support.
- **Goal**: Integrate FPGA-specific functionality into `if_ix` while maintaining iflib design principles.

### Scope

1. **FPGA Code Discovery** — Extract all `#ifdef FPGA_SUPPORT` guarded code: device ID, alt init/reset, register semantics, PHY/link/autoneg differences, timing/polling workarounds. Track implicit dependencies.

2. **Architecture Mapping (Legacy → iflib)**:

   | Legacy Concept | iflib Target |
   |---------------|-------------|
   | Probe/attach | `ix_if_attach_pre()`, `ix_if_attach_post()` |
   | HW init | `ix_if_init()` |
   | Reset | ixgbe HW reset helpers via iflib callbacks |
   | Link handling | `ix_if_media_status()`, `ix_if_media_change()` |
   | Interrupts | `ifdi_intr_enable`, `ifdi_intr_disable` |
   | TX/RX queues | iflib queue allocation callbacks |

   Rules: No direct `ifnet` manipulation. No iflib bypasses. PF-specific code stays in `if_ix`.

3. **Gap Analysis** — Compare FPGA-enabled behavior vs current `if_ix`. Identify missing probe/init/link functionality.

4. **Integration Principles**:
   - Prefer runtime detection over compile-time `#ifdef`s where possible
   - Use `#ifdef FPGA_SUPPORT` only when compile-time separation is required
   - Production silicon paths must remain unchanged
   - No conditionals in TX/RX fast paths

5. **Build** — `if_ix` must build cleanly with `FPGA_SUPPORT` disabled. FPGA paths activate only when explicitly enabled.

6. **Safety** — FPGA support must not affect init sequences, performance, or feature flags for non-FPGA adapters. Strictly opt-in.

### Git & Commit Requirements

- Dedicated branch on internal FreeBSD source mirror
- Separate refactoring commits from functional FPGA enablement
- Commit messages must reference: `ixgbe`, `if_ix`, FPGA support, legacy out-of-tree origin

### Expected Output

- Modified `if_ix.c` and related ixgbe source files
- Updated common ixgbe headers (if needed)
- Short summary: features added, iflib lifecycle integration, known limitations
