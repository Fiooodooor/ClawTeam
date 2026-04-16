---
name: nic-phase-2-seam-design
description: "Phase 2: Design the OAL seam architecture and compile-time boundaries."
argument-hint: "Driver name, api_mapping.json path, target OS list"
agent: nic-senior-architect
---
Execute Phase 2 — Seam Architecture & OAL Design for this driver:

${input:Driver name, api_mapping.json path, and target OS list (e.g. FreeBSD, Linux)}

Phase 2 deliverables:
1. `mynic_osdep.h` with `#ifdef __FreeBSD__` / `#elif defined(__linux__)` conditional includes
2. Inline wrapper per API mapping entry (e.g., `oal_dma_map()` wrapping `bus_dmamap_load()`)
3. Weak symbols for optional features
4. Three-layer architecture validation: FreeBSD Native Adapter → Portable NIC Core → Hardware Registers
5. Portable core audit — zero `#include <linux/*>`, zero `sk_buff`, zero `net_device`, zero `napi`
6. `Makefile.multi` with per-OS, per-ARCH CFLAGS and SRCS
7. Compile gate — both Linux and FreeBSD targets build clean

Gate criteria:
- native_score ≥ 98
- Portable core contains zero OS-specific includes
- `#ifdef` nesting ≤ 2 levels
- All OAL wrappers are `static inline`
- Compile gate passes on Linux + FreeBSD

Submit the seam design via `plan_submit` for director approval.
Use `mailbox_send` with key `seam-design-ready` when OAL boundaries are finalized.
