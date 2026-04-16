---
name: nic-phase-4-incremental-port
description: "Phase 4: Implement incremental port slices to pass TDD tests."
argument-hint: "Driver name, slice number (4.1-4.7), test file path"
agent: nic-porting-director
---
Execute Phase 4 — Incremental Port Slices for this driver:

${input:Driver name, slice number or subsystem, and path to failing tests}

Phase 4 slices:
- 4.1: Admin queue (control plane) → nic-senior-sde
- 4.2: TX ring (if_transmit, TSO flags, multi-queue) → nic-senior-sde-datapath
- 4.3: RX ring (m_getcl, refill, if_input) → nic-senior-sde-datapath
- 4.4: DMA engine (bus_dma lifecycle) → nic-senior-sde-datapath
- 4.5: Interrupts/MSI-X (bus_setup_intr, taskqueue) → nic-senior-sde-datapath
- 4.6: Offloads (RSS, TSO, checksum flags) → nic-senior-sde-datapath
- 4.7: Stats/counters (sysctl) → nic-senior-sde

Per-slice protocol:
1. Implement native OAL code to pass failing tests
2. Touch ONLY OS-specific calls — preserve Linux logic
3. Use compile-time seams (#ifdef __FreeBSD__)
4. Verify tests go green for this slice
5. Cross-compile check (Linux + FreeBSD)

Gate criteria per slice:
- All slice tests pass (green)
- native_score >= 98.0
- No regressions in prior slices
- Zero memcpy/bcopy/m_copydata in hot paths (slices 4.2-4.5)
