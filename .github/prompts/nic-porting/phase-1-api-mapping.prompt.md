---
name: nic-phase-1-api-mapping
description: "Phase 1: Build the Linux-to-FreeBSD API mapping table."
argument-hint: "Driver name, scope document path"
agent: nic-porting-director
---
Execute Phase 1 — API Inventory & Mapping for this driver:

${input:Driver name and path to the Phase 0 scope document}

Phase 1 deliverables:
1. Complete API call inventory from all in-scope .c and .h files
2. Classification by subsystem (Memory, DMA, Network, Synchronization, PCI)
3. api_mapping.json with entries: {linux_api: {freebsd: native_api, header: header_path}}
4. Zero-copy opportunity analysis (LinuxKPI UMA skb, partial mbuf backing)
5. Unmapped API gap list with proposed solutions
6. native_score computation (target >= 98.0)

Gate criteria:
- native_score >= 98.0
- Zero unmapped critical-path APIs
- All mappings verified as native FreeBSD (no LinuxKPI shims in final port)

Delegate API scanning to #tool:agent nic-linuxkpi-engineer.
