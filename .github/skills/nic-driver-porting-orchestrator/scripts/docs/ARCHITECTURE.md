# NIC Driver Porting Orchestrator — Pipeline Architecture

## Overview

The NIC Driver Porting Orchestrator uses a **multi-phase LangGraph pipeline** to
autonomously port Linux NIC driver data-plane code to FreeBSD, Windows, or ESXi.
Each phase uses autonomous ReAct agents that reason about tasks and select
appropriate tools without prescriptive instructions.

## Architecture Diagrams

### Orchestrator and Phases

```text
                       ┌───────────────────────────────┐
                       │     Porting Orchestrator       │
                       │    (Pipeline Coordinator)      │
                       │                                │
                       │  • 8 phase nodes (0–7)         │
                       │  • Conditional gate edges      │
                       │  • Score & risk thresholds     │
                       └───────────────┬────────────────┘
                                       │
    ┌──────────┬──────────┬────────────┼───────────┬───────────┬──────────┬──────────┐
    │          │          │            │           │           │          │          │
    ▼          ▼          ▼            ▼           ▼           ▼          ▼          ▼
┌────────┐┌────────┐┌────────┐┌────────────┐┌────────┐┌──────────┐┌────────┐┌────────┐
│Phase 0 ││Phase 1 ││Phase 2 ││  Phase 3   ││Phase 4 ││ Phase 5  ││Phase 6 ││Phase 7 │
│ Source ││  API   ││  TDD   ││   Coder    ││ Native ││Perf/Port ││ Risk / ││ Final  │
│Analysis││Mapping ││ Tests  ││            ││Validate││ Validate ││ Verify ││Checkl. │
└────────┘└────────┘└────────┘└────────────┘└────────┘└──────────┘└────────┘└────────┘
```

### Pipeline Flow

```text
┌─────────────────────────────────────────────────────────────────────┐
│                         Pipeline Flow                               │
│                                                                     │
│  [START]                                                            │
│     │                                                               │
│     ▼                                                               │
│  ┌──────────────────────┐                                           │
│  │ Phase 0: Source      │  Analyse Linux source, scaffold layout    │
│  │         Analysis     │                                           │
│  └──────────┬───────────┘                                           │
│             │ GATE: source_analysis populated                       │
│             ▼                                                       │
│  ┌──────────────────────┐                                           │
│  │ Phase 1: API         │  Build Linux→target-OS mapping tables     │
│  │         Inventory    │                                           │
│  └──────────┬───────────┘                                           │
│             │ GATE: api_mappings non-empty                          │
│             ▼                                                       │
│  ┌──────────────────────┐                                           │
│  │ Phase 2: TDD Tests   │  Write failing CppUTest tests (red)      │
│  └──────────┬───────────┘                                           │
│             │                                                       │
│             ▼                                                       │
│  ┌──────────────────────┐                                           │
│  │ Phase 3: Coder       │  Implement ported code (green)            │
│  └──────────┬───────────┘                                           │
│             │                                                       │
│             ▼                                                       │
│  ┌──────────────────────┐                                           │
│  │ Phase 4: Validation  │  NativeValidator + CodeReviewer           │
│  │                      │  → native_score                           │
│  └──────────┬───────────┘                                           │
│             │                                                       │
│             ▼                                                       │
│  ┌──────────────────────┐                                           │
│  │ Phase 5: Perf &      │  PerformanceEngineer + PortabilityValid.  │
│  │  Portability         │  → portability_score                      │
│  └──────────┬───────────┘                                           │
│             │ GATE: native ≥ 98, portability ≥ 95                   │
│             ▼                                                       │
│  ┌──────────────────────┐                                           │
│  │ Phase 6: Risk &      │  RiskAuditor + VerificationExecutor       │
│  │  Verification        │  Build & test on target VM                │
│  └──────────┬───────────┘                                           │
│             │ GATE: zero CRITICAL open risks                        │
│             ▼                                                       │
│  ┌──────────────────────┐                                           │
│  │ Phase 7: Final       │  Section 14 checklist (14 items)          │
│  │  Checklist           │  porting_report.md + porting_results.json │
│  └──────────┬───────────┘                                           │
│             │                                                       │
│             ▼                                                       │
│          [END]                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Pipeline Phases

### Phase 0: Source Analysis

Analyses the Linux driver source tree. The agent autonomously:

- Identifies all data-plane source files (Rx, Tx, ring, DMA, interrupt)
- Maps the three-layer separation: Portable Core / Native Adapter / HW Registers
- Scaffolds the output directory layout
- Counts Linux-specific APIs for porting scope estimation

### Phase 1: API Inventory & Mapping Tables

Builds a complete mapping table of Linux kernel APIs to target-OS equivalents:

- `dma_map_single` → `bus_dmamap_load` (FreeBSD) / `NdisMAllocateSharedMemory` (Windows)
- `sk_buff` → `mbuf` (FreeBSD) / `NET_BUFFER_LIST` (Windows)
- Risk-annotated per mapping: LOW / MEDIUM / HIGH

### Phase 2: TDD Test Writing

Writes failing CppUTest tests **before** any porting code (red phase):

- One test group per source module
- Mocks for OS/HW dependencies
- Coverage targets: ring alloc/free, Tx/Rx path, register access, error paths

### Phase 3: Coder

Implements the actual ported driver code (green phase):

- Portable core: zero OS headers, `stdint.h` types only
- Native adapter: idiomatic FreeBSD `bus_dma`, `mbuf`, `DRIVER_MODULE`
- HW layer: register definitions and BAR access

### Phase 4: Native Validation & Code Review

Two specialist agents score the ported code:

- **NativeValidatorAgent**: computes `native_score` (target ≥ 98)
- **CodeReviewerAgent**: checks correctness, use-after-free, ring wrap-around

### Phase 5: Performance & Portability

Two specialist agents validate non-functional quality:

- **PerformanceEngineerAgent**: hot-path analysis, cache alignment, lock contention
- **PortabilityValidatorAgent**: computes `portability_score` (target ≥ 95)

**Gate**: Both scores must pass thresholds before proceeding.

### Phase 6: Risk Audit & Verification

- **RiskAuditorAgent**: audits the risk register (DMA, locking, memory, compliance)
- **VerificationExecutorAgent**: builds on target VM, runs CppUTest suite, loads module

**Gate**: Zero CRITICAL open risks.

### Phase 7: Final Validation Checklist (Section 14)

Evaluates 14 checklist items and generates:

- `porting_report.md` — human-readable report with pass/fail checklist
- `porting_results.json` — structured JSON for automation

## Output Artifacts

| File | Purpose |
| ---- | ------- |
| `porting_report.md` | Human-readable report with Section 14 checklist |
| `porting_results.json` | Structured pipeline data |
| `portable_core/` | Framework-independent C data-plane code |
| `freebsd_adapter/` | Native OS adapter layer |
| `hw/` | Hardware register definitions |
| `tests/` | CppUTest test suite |
| `pipeline.log` | Execution log at DEBUG level |

## Agent Prompt Composition

Each agent's prompt is composed from two layers:

```text
┌─────────────────────────────────────────────────────────────────┐
│                        Any Agent                                │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                 Hard Prompt (*.py)                        │  │
│  │  • Phase objectives and output requirements               │  │
│  │  • Gate thresholds and constraints                        │  │
│  │  • Three-layer architecture rules                         │  │
│  │                                                           │  │
│  │  ➜ Fixed, defines WHAT the agent must achieve             │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              +                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │               Skills Prompt (*_skills.md)                 │  │
│  │  • API mapping tables, porting patterns                   │  │
│  │  • Native idiom examples per target OS                    │  │
│  │  • Known pitfalls and false-positive risks                │  │
│  │                                                           │  │
│  │  ➜ Evolvable, treated as guidance NOT absolute rules      │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Specialist Worker Agents

| Agent | Phase | Responsibility |
| ----- | ----- | -------------- |
| SourceAnalysisAgent | 0, 1 | Source analysis, directory scaffold, API inventory |
| TDDWriterAgent | 2 | Write failing CppUTest tests |
| CoderAgent | 3 | Implement ported code |
| NativeValidatorAgent | 4 | Compute native_score |
| CodeReviewerAgent | 4 | Correctness review |
| PerformanceEngineerAgent | 5 | Hot-path analysis |
| PortabilityValidatorAgent | 5 | Compute portability_score |
| RiskAuditorAgent | 6 | Risk register audit |
| VerificationExecutorAgent | 6 | Build & test on target VM |
| FinalChecklistGenerator | 7 | Section 14 checklist & report |

## Key Design Principles

### Autonomous Agents

Agents use the ReAct pattern (Reason + Act) to autonomously decide which tools
to use. Prompts describe **what** to achieve, not **how** to achieve it.

### Three-Layer Architecture

All ported code is separated into Portable Core (zero OS calls), Native Adapter
(idiomatic target-OS code), and Hardware Registers (BAR/register definitions).

### Gate-Driven Progression

Phases advance only when quality gates pass:

- `native_score ≥ 98`
- `portability_score ≥ 95`
- Zero CRITICAL open risks

### Skills-Based Knowledge

Domain knowledge (API mappings, native idiom patterns, risk categories) is in
separate skills files, keeping prompts clean and knowledge modular.

## Project Structure

```text
agent/
├── pipeline/                # Pipeline phases and orchestration
│   ├── orchestrator.py      # Main pipeline graph (StateGraph, 8 phases)
│   ├── state.py             # TypedDict state definitions
│   ├── data_collector.py    # Phases 0–1: Source analysis & API inventory
│   ├── log_analyzer.py      # Phases 2–6: 8 specialist worker agents
│   ├── fusioner.py          # Cross-phase validation agent
│   ├── summarizer.py        # Phase 7: Final checklist & report
│   ├── callbacks.py         # Tool call logging utility
│   └── json_utils.py        # JSON parsing utility
├── skills/                  # Domain-specific knowledge (BKMs)
│   ├── source_analysis_skills.md
│   ├── api_mapping_skills.md
│   ├── tdd_writer_skills.md
│   ├── coder_skills.md
│   ├── validation_skills.md
│   └── risk_auditor_skills.md
└── analyze_build.py         # CLI entry point

service/
└── app.py                   # FastAPI microservice wrapper
```
