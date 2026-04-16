---
name: nic-phase-3-tdd-harness
description: "Phase 3: Create the TDD test harness with failing tests for all subsystems."
argument-hint: "Driver name, subsystems to test, api_mapping.json path"
agent: nic-tdd-tech-lead
---
Execute Phase 3 — TDD Harness & Failing Tests for this driver:

${input:Driver name, target subsystems (TX/RX/DMA/interrupts/offloads), and api_mapping.json path}

Phase 3 deliverables:
1. Test taxonomy (unit, integration, smoke, stress) with coverage targets
2. CppUTest framework setup with native FreeBSD mock stubs
3. Failing test files per subsystem (>= 50 tests each):
   - tests/test_tx_ring.c (submit, complete, wrap-around, full-ring)
   - tests/test_rx_ring.c (poll, refill, checksum, RSS)
   - tests/test_dma_engine.c (map, unmap, sync, bounce buffer)
   - tests/test_interrupts.c (MSI-X alloc, dispatch, coalescing, teardown)
   - tests/test_offloads.c (TSO, checksum, VLAN, RSS indirection)
4. Every test must fail with clear assertion message
5. TDD traceability matrix linking tests to api_mapping entries

Gate criteria:
- native_score >= 98.0
- All tests compile and fail (red state confirmed)
- Zero implementation code present

Delegate test writing to nic-tdd-senior-dev via handoff.
