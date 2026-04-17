# Risk Auditor Agent Skills

Best Known Methods (BKMs) for Phase 6: risk register audit and verification execution.

## Domain Knowledge

### Risk Register Categories

| Category | Example Risks |
| -------- | ------------- |
| DMA | Incorrectly sized DMA tags; missing sync barriers |
| Locking | Priority inversion; lock contention on multi-queue drivers |
| Memory | Fragmentation from repeated mbuf alloc/free; NUMA affinity |
| Interrupt | MSI-X vector allocation failure fallback; spurious interrupts |
| Compliance | Missing `SYSCTL` for tunable parameters; `kld` versioning |
| Portability | Residual Linux types in portable core; endianness assumptions |

### Risk Severity Matrix

| Likelihood↓ / Impact→ | Low | Medium | High |
| ---------------------- | --- | ------ | ---- |
| High | MEDIUM | HIGH | CRITICAL |
| Medium | LOW | MEDIUM | HIGH |
| Low | LOW | LOW | MEDIUM |

Gate rule: **zero CRITICAL open risks** to proceed from Phase 6 to Phase 7.

### Verification Execution Checklist

1. **Build on target OS** — `make` or `cmake --build .` must succeed with zero warnings (`-Werror`)
2. **Run CppUTest suite** — all TDD tests from Phase 2 must pass (green)
3. **Load module** — `kldload <driver>.ko` (FreeBSD) or verify NDIS miniport registration
4. **Basic traffic** — send/receive 64-byte, 1518-byte, and 9000-byte (jumbo) frames
5. **Stress** — 10M packets at line rate with no drops (if VM environment supports it)
6. **Unload** — `kldunload <driver>.ko` cleanly (no panics, no leaked memory)

### Common False-Positive Risks

- "Missing NUMA awareness" — acceptable on single-socket test VMs
- "No SR-IOV support" — out of scope for initial data-plane port
- "TSO not implemented" — fine if LRO/GRO are not in porting scope

### Mitigation Documentation

For every MEDIUM or higher risk, document:

- **Risk ID** — sequential `RISK-001`
- **Description** — one sentence
- **Mitigation** — concrete action or accepted rationale
- **Owner** — `coder` / `reviewer` / `deferred`
- **Status** — `open` / `mitigated` / `accepted`
