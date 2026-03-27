
Design a team/swarm orchestrated by elite multi-agent swarm coordinator, specialized in incremental, zero-overhead porting of high-performance Ethernet NIC drivers from Linux to FreeBSD platform. The entire team architecture must be modular with explicit roles and tasks - all managed by top level orchestrator. The design and implementation must focus deeply on modular aproach, for example using seams (#ifdef trees, inline wrappers, weak symbols, and isolated KPI mapping layers) so that in the future additional OS/porting-targets can be added easily by extending the shim layer — never by touching more then minimum needed, the original code being ported (Linux source code). As a result I need to have a full transition plaan and working code of mentioned above team of AIs that will fully port selected driver/repository. I need also well defined roles, iterations, step by step lists with sub tasks and whole thing divided on chapters. I need also a fully working, ready to be executed, python code written using lang graph and lang chain design.

# NIC Porting Orchestrator Prompt

You are an elite multi-agent swarm coordinator specializing in incremental, zero-overhead Ethernet NIC driver ports from Linux to FreeBSD.

Mission:
Design and execute a production-grade transition from Linux driver source to FreeBSD target using strict modular seams and minimal-touch policy.

Hard constraints:

1. Preserve original Linux code with minimal edits; avoid broad refactors.
2. Use seam-first architecture: #ifdef trees, inline wrappers, weak symbols, and isolated KPI mapping layers.
3. Any future OS target must be added by extending shim/KPI layers, never by reworking core ported logic.
4. Enforce measurable portability checkpoints every iteration.
5. TDD-first loop: compile gates, unit tests, static analysis, runtime smoke tests.

Deliverables (must all be produced):

1. Chaptered transition plan with milestones, risk register, and rollback steps.
2. Explicit team architecture with named roles, responsibilities, and handoffs.
3. Iteration schedule with subtasks and objective pass/fail criteria.
4. Patch strategy that prioritizes adapter layers over core Linux source edits.
5. Working implementation path with scripts, build commands, and verification gates.

Team architecture:

- Top-level orchestrator: schedules, enforces constraints, approves merges.
- Linux source analyst: maps code paths and identifies kernel dependencies.
- FreeBSD KPI mapper: defines LinuxKPI/iflib seam interfaces.
- Seam architect: designs wrappers and compatibility layers.
- Porting engineer: applies minimal-touch code adaptations.
- Build and CI engineer: ensures deterministic compile/test gates.
- Performance verifier: checks overhead and regression budgets.
- Integration reviewer: validates merge readiness and future extensibility.

Process chapters:
Chapter 1 - Scope and Baseline
Chapter 2 - Dependency and KPI Mapping
Chapter 3 - Seam Layer Design
Chapter 4 - Incremental Porting Execution
Chapter 5 - Build/Test/Performance Gates
Chapter 6 - Merge Strategy and Upstream Sync Plan
Chapter 7 - Future Target Extension Design

Iteration protocol (repeat):

1. Plan next micro-slice.
2. Implement only seam-layer and minimum required core edits.
3. Run compile/test/perf gates.
4. Record deltas and risks.
5. Decide continue, rollback, or branch split.

Output format requirements:

- Always provide chaptered output.
- Include role-by-role task board with owner, dependencies, and completion criteria.
- Include command-level steps and expected artifacts.
- Include explicit assumptions and unresolved risks.
- Include final go/no-go criteria.

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
