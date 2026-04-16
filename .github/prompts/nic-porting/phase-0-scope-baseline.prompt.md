---
name: nic-phase-0-scope-baseline
description: "Phase 0: Lock scope and baseline for a NIC driver porting run."
argument-hint: "Driver name, Linux source path, target OS"
agent: nic-porting-director
---
Execute Phase 0 — Scope & Baseline Lock for this driver:

${input:Driver name, Linux source path (e.g. drivers/net/ethernet/intel/ice/), and target OS}

Phase 0 deliverables:
1. File inventory of dataplane scope (RX/TX, DMA, interrupts, RSS, TSO, checksum)
2. Out-of-scope exclusion list (PHY, firmware loading, devlink, debugfs)
3. Dependency graph of in-scope files
4. Baseline commit SHA lock (git hash)
5. Linux API call frequency table (hot calls vs cold calls per file)
6. Build verification on Linux (make modules, zero warnings)

Gate criteria:
- build_status = green
- Scope document reviewed and locked
- Baseline hash recorded

Delegate file analysis to #tool:agent nic-linux-analyst.
