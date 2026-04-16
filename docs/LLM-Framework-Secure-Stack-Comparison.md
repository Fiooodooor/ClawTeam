# LLM Framework Secure Stack Comparison — Unified Reference

> **Date:** 2026-04-16  
> **Scope:** Linux-to-FreeBSD NIC driver porting — multi-agent orchestration stack selection  
> **Version:** 4.0 (unified)  
> **Constraints:** ClawTeam = RETAINED | OpenClaw = PROHIBITED | AutoGen = MAINTENANCE MODE  
> **Supersedes:** v1 (`framework-comparison-r-and-d.md`), v2 (`v2-secure-stack.md`), v3 (`v3-clawteam-secure-stack.md`)

---

## Table of Contents

1. [Complexity Spectrum](#1-complexity-spectrum)
2. [Executive Summary](#2-executive-summary)
3. [Orchestration Patterns for NIC Porting](#3-orchestration-patterns-for-nic-porting)
4. [Framework Catalog](#4-framework-catalog)
5. [Deep Dive: In-Stack Frameworks](#5-deep-dive-in-stack-frameworks)
6. [Deep Dive: Evaluated Alternatives](#6-deep-dive-evaluated-alternatives)
7. [Dual Orchestrator Architecture](#7-dual-orchestrator-architecture)
8. [RAG Knowledge Layer](#8-rag-knowledge-layer)
9. [Messaging Bridge](#9-messaging-bridge)
10. [Comparison Matrices](#10-comparison-matrices)
11. [Phase-by-Phase Tool Assignment](#11-phase-by-phase-tool-assignment)
12. [Deployment Automation](#12-deployment-automation)
13. [Comprehensive Implementation Steps](#13-comprehensive-implementation-steps)
14. [Migration & Cost Analysis](#14-migration--cost-analysis)
15. [Conclusion](#15-conclusion)
16. [Appendices](#16-appendices)

---

## 1. Complexity Spectrum

Microsoft's AI Agent Orchestration Patterns define three complexity levels. NIC driver porting sits firmly at the highest level.

| Level | Description | Example | NIC Porting? |
|-------|-------------|---------|:------------:|
| **Direct Model Call** | Single LLM call, no agent loop | Code completion | ✗ |
| **Single Agent** | One agent with tool access, loop until done | Bug investigation | ✗ |
| **Multi-Agent** | Multiple specialized agents coordinating through an orchestrator | **NIC driver porting** | **✓** |

**Why multi-agent is required for NIC porting:**

- **Cross-functional phases**: 8 phases spanning source analysis → TDD → implementation → validation → merge.
- **Security boundaries per agent**: Test writers cannot modify production code; risk auditors cannot approve their own findings.
- **Parallel specialization**: Phases 1 and 4 use embarrassingly-parallel fan-out across files.
- **Maker-checker debate loops**: Phase 5 requires adversarial GROUP_CHAT between native-validator, code-reviewer, and risk-auditor.
- **Gate enforcement**: `native_score >= 98`, `portability_score >= 95` — must be checked by independent validators, not self-reported.

---

## 2. Executive Summary

### 2.1 Evolution

| Version | Date | Key Change | Why |
|---------|------|-----------|-----|
| v1 | 2025-Q4 | 5-framework comparison (ClawTeam, AO, Dify, GitNexus, OpenClaw) | Baseline analysis |
| v2 | 2026-Q1 | Removed ClawTeam + OpenClaw; replaced with CrewAI + Langflow | Security hardening |
| v3 | 2026-Q2 | Restored ClawTeam (with mitigations); removed OpenClaw; added Codex CLI | ClawTeam's git worktree + tmux spawn is irreplaceable |
| **v4 (this)** | 2026-04-16 | Unified all prior R&D; added dual orchestrator, RAG, messaging, pattern mapping | Single deployment-ready reference |

### 2.2 Key Constraints

| Constraint | Status | Rationale |
|-----------|--------|-----------|
| ClawTeam | ✅ RETAINED | Native git worktrees, kanban, `clawteam spawn tmux` — no alternative provides all three |
| OpenClaw | 🚫 PROHIBITED | Proprietary risk, replaced by Aider + Codex CLI + OpenHands |
| AutoGen | ⚠️ MAINTENANCE MODE | Microsoft deprecated; migrate to MAF when stable |

### 2.3 Recommended 8-Layer Stack

```
┌─────────────────────────────────────────────────────────┐
│  Layer 7: Langflow Dashboard (visual workflow + MCP)    │
├─────────────────────────────────────────────────────────┤
│  Layer 6: RAG Knowledge Store (TF-IDF → Qdrant)        │
├─────────────────────────────────────────────────────────┤
│  Layer 5: Messaging Bridge (pub/sub, ClawTeam ↔ AO)    │
├─────────────────────────────────────────────────────────┤
│  Layer 4: GitNexus Code Intelligence (tree-sitter KG)   │
├─────────────────────────────────────────────────────────┤
│  Layer 3: Coding Agents (Aider → Codex CLI → OpenHands) │
├─────────────────────────────────────────────────────────┤
│  Layer 2: Agent Orchestrator (CI/PR/dashboard)          │
├─────────────────────────────────────────────────────────┤
│  Layer 1: ClawTeam (multi-agent coordination, core)     │
├─────────────────────────────────────────────────────────┤
│  Layer 0: LangGraph (state machine, checkpoints)        │
└─────────────────────────────────────────────────────────┘
        Optional: Temporal (durable execution under Layer 0)
```

### 2.4 Quick Decision Matrix

| Use Case | Minimum Stack | Full Stack |
|----------|---------------|------------|
| Single-driver port, one developer | LangGraph + Aider | — |
| Multi-file port, TDD pipeline | LangGraph + ClawTeam + Aider | + GitNexus |
| Full production pipeline with CI/CD | All 8 layers | + Temporal + Qdrant |

---

## 3. Orchestration Patterns for NIC Porting

The `OrchestrationPattern` enum (from `ai-agent-orchestration-template-03-2026.py`) implements all five Microsoft AI Agent Orchestration patterns. Each of the 8 NIC porting phases maps to one pattern:

### 3.1 Phase-to-Pattern Mapping

| Phase | Name | Pattern | Why This Pattern |
|:-----:|------|---------|------------------|
| 0 | Scope & Baseline Lock | **SEQUENTIAL** | Linear dependency — baseline must lock before any analysis |
| 1 | API Inventory & Mapping | **CONCURRENT** | Embarrassingly parallel: each source file analyzed independently |
| 2 | Seam Architecture | **SEQUENTIAL** | Depends on complete API mapping; single architect role |
| 3 | TDD Harness | **SEQUENTIAL** | Tests must compile against seam headers before implementation |
| 4 | Incremental Port | **CONCURRENT** | Multiple subsystems ported in parallel worktrees (TX, RX, admin, interrupts) |
| 5 | Validation Gates | **GROUP_CHAT** | Adversarial debate: native-validator + code-reviewer + performance-engineer + risk-auditor |
| 6 | Merge & Sync | **SEQUENTIAL** | Single merge operation; cannot parallelize |
| 7 | Multi-OS Extension | **MAGENTIC** | Open-ended planning with living task ledger |

### 3.2 Pattern Definitions

**SEQUENTIAL** — Single agent executes, passes result to next. Used when strict ordering is required.
- Debate rounds: N/A
- Handoff: Implicit (phase completion triggers next phase)

**CONCURRENT** (fan-out/fan-in) — Multiple agents execute the same task type in parallel, results aggregated.
- Worker pool: `clawteam spawn tmux` creates one worktree per agent
- Fan-in: Orchestrator collects results, merges, checks completeness

**GROUP_CHAT** (maker-checker) — Multiple agents debate in rounds until consensus or round limit.
- `MAX_DEBATE_ROUNDS = 5`
- `DEBATE_ROUND_TIMEOUT = 300` seconds per round
- Roles: maker (coder), checker (native-validator), reviewer (code-reviewer), auditor (risk-auditor)
- Termination: all checkers approve OR max rounds reached (triggers escalation)

**HANDOFF** — Agent transfers task to a more specialized agent.
- `MAX_HANDOFF_DEPTH = 3` (prevents infinite delegation)
- Examples: code-reviewer → native-validator, seam-architect → portability-validator

**MAGENTIC** — Autonomous task-ledger-based execution. Agent creates/completes tasks from a living ledger.
- Used for Phase 7 (open-ended multi-OS extension planning)
- Risk-auditor-final operates in this pattern, maintaining the living risk register

### 3.3 When to Override the Default Pattern

| Scenario | Override |
|----------|----------|
| Phase 1 has only 1 source file | SEQUENTIAL instead of CONCURRENT |
| Phase 5 has only 1 checker available | SEQUENTIAL instead of GROUP_CHAT |
| Critical risk found in any phase | Inject GROUP_CHAT debate round regardless of default pattern |
| Phase 4 subsystem has cross-dependencies | SEQUENTIAL for that slice, CONCURRENT for independent slices |

---

## 4. Framework Catalog

### 4.1 In-Stack (Recommended)

| Framework | Stars | License | Version | Role in Stack |
|-----------|------:|---------|---------|---------------|
| LangGraph | 29.4k | MIT | ≥0.3.0 | Layer 0: State machine orchestration |
| ClawTeam | — | MIT | 0.3.0 | Layer 1: Multi-agent coordination (core orchestrator) |
| Agent Orchestrator | — | Proprietary (Intel) | — | Layer 2: CI/PR/dashboard (secondary orchestrator) |
| Aider | 43.4k | Apache-2.0 | — | Layer 3: Tier 1 coding agent (edit-only, lowest risk) |
| Codex CLI | 75.6k | Apache-2.0 | — | Layer 3: Tier 2 coding agent (bubblewrap-sandboxed) |
| OpenHands | 71.3k | MIT | — | Layer 3: Tier 3 coding agent (Docker-sandboxed, full execution) |
| GitNexus | — | MIT | — | Layer 4: Tree-sitter knowledge graph, 14+ MCP tools |
| Langflow | 147k | MIT | — | Layer 7: Visual workflow dashboard, MCP-native |

### 4.2 Evaluated — Not Selected

| Framework | Stars | License | Status | Reason |
|-----------|------:|---------|--------|--------|
| CrewAI | 49k | MIT | **Fallback** | Backup if ClawTeam risks become unacceptable |
| MAF (Microsoft Agent Framework) | 9.5k | MIT | **Watch** | AutoGen successor; not production-ready yet |
| smolagents | 26.6k | Apache-2.0 | **Watch** | Lightweight code-first; potential Tier 1 alternative |
| AutoGen | 57.1k | MIT | ⚠️ **MAINTENANCE MODE** | Microsoft deprecated — do not adopt |
| Dify | ~92k | Apache-2.0 | **Replaced** | Replaced by Langflow (MCP-native, lighter infra) |
| n8n | — | Sustainable Use | **Optional glue** | Webhook bridge only; not required |

---

## 5. Deep Dive: In-Stack Frameworks

### 5.1 LangGraph — Orchestration Engine (Layer 0)

LangGraph provides the state machine that drives the 8-phase pipeline. Key capabilities:

- **StateGraph**: Typed state dictionary (`OrchestratorState` — 40+ fields) flows through nodes
- **Conditional edges**: Route based on gate scores, debate outcomes, risk register status
- **Checkpoints**: Resume from any phase after crash (via `nic_porting_checkpoint.py`)
- **Streaming**: Real-time token output for long-running phases
- **Subgraph composition**: Each phase can be a nested subgraph with its own edges

**Temporal enhancement (optional)**: For durable execution guarantees, wrap LangGraph phases in Temporal workflows. Provides automatic retry, cron scheduling, and cross-process state persistence. Not required for local dev; recommended for production CI/CD.

### 5.2 ClawTeam — Multi-Agent Coordination (Layer 1, Core Orchestrator)

ClawTeam is the **core** orchestrator. It owns task management, agent lifecycle, phase progression, inbox messaging, and risk tracking.

**Why ClawTeam over CrewAI:**

| Dimension | ClawTeam v0.3.0 | CrewAI v0.114 |
|-----------|----------------|---------------|
| Git worktrees | ✅ Native (`clawteam workspace create`) | ❌ Requires custom `GitWorktreeTool` |
| Agent spawn | ✅ `clawteam spawn tmux <agent-command>` | ❌ In-process only |
| CLI ergonomics | ✅ Full CLI: task, board, inbox, spawn | ❌ Python API only |
| Kanban board | ✅ Native with status tracking | ❌ External tooling required |
| Community size | Small (pre-release) | Large (49k★) |
| Supply chain risk | Higher (small project, fewer eyes) | Lower (VC-funded, audited) |

**Verdict**: ClawTeam wins on architecture (worktrees + spawn + CLI). CrewAI is the documented fallback.

**Security mitigations (mandatory):**

| Risk | Mitigation |
|------|------------|
| File-system inbox readable by other users | `chmod 0700` on team data dirs |
| ZMQ binds 0.0.0.0 by default | Bind to `127.0.0.1` only; patch upstream or use env override |
| No audit log of agent actions | Enable `_event_log` in `DualOrchestrator` + persist to disk |
| Small contributor base | Pin to known-good commit hash in `requirements.txt` |
| No SECURITY.md upstream | Maintain local `SECURITY.md` with disclosure process |

### 5.3 Agent Orchestrator — CI/PR/Dashboard (Layer 2, Secondary Orchestrator)

The Agent Orchestrator (AO) handles everything outside of core task coordination:

- **CI failure feedback loop** (unique capability): When CI fails, AO automatically sends the failure log to the responsible agent via `send-to-agent`, with up to 2 retries (`configs/ao-nic-porting.yaml`).
- **Reactions config**:
  - `ci-failed` → auto send-to-agent (2 retries)
  - `changes-requested` → auto reassign
  - `agent-stuck` → 10-minute timeout, then escalate
- **Dashboard**: Port 3000 web UI for pipeline visualization
- **Security**: Bind to `127.0.0.1` only. No external exposure.

### 5.4 GitNexus — Code Intelligence (Layer 4)

GitNexus builds a tree-sitter-powered knowledge graph of the codebase and exposes 14+ MCP tools:

- `query`: Natural language search over code structure
- `impact`: Blast-radius analysis for proposed changes
- `detect_changes`: Diff-aware analysis
- `context`: Get surrounding code context
- `rename`: Safe rename with reference tracking

**No replacement exists** — GitNexus is the only framework providing tree-sitter KG + MCP in this stack. Port 4747, local-only, no security concerns.

### 5.5 Coding Agents — Three-Tier Strategy (Layer 3)

All coding agents must be invocable via `clawteam spawn tmux <command>`.

| Tier | Agent | Sandbox | Risk | Spawn Command | Use When |
|:----:|-------|---------|------|---------------|----------|
| 1 | Aider | None (edit-only) | Lowest | `clawteam spawn tmux aider` | Simple edits, line changes, TDD red→green |
| 2 | Codex CLI | bubblewrap | Medium | `clawteam spawn tmux codex` | Multi-file changes, compilation, test runs |
| 3 | OpenHands | Docker | Highest | `clawteam spawn tmux openhands` | Full build/test cycles, environment setup |

**Why Codex CLI replaces Claude Code**: Codex CLI is open source (Apache-2.0, 75.6k★) with bubblewrap sandbox. Claude Code is proprietary with no sandbox. For a security-focused stack, open source + sandbox is strictly preferable.

**OpenClaw removal**: OpenClaw was the default agent in v1 (`DEFAULT_AGENT_COMMAND=openclaw` in `scripts/setup-full-stack.conf`). It is now **prohibited**. The default agent command must be updated to `aider` (Step 9 in Section 13).

### 5.6 Langflow — Visual Dashboard (Layer 7)

Langflow replaces Dify as the visual workflow and dashboard layer:

| Dimension | Langflow | Dify |
|-----------|----------|------|
| MCP support | ✅ Native | ❌ Plugin required |
| License | MIT | Apache-2.0 |
| Infrastructure | Python process | Docker + PostgreSQL + Redis |
| Stars | 147k | ~92k |
| Custom components | Python decorator | YAML DSL |

Langflow provides drag-and-drop workflow visualization, MCP tool integration, and can serve as the monitoring dashboard for the NIC porting pipeline. Lighter infrastructure footprint than Dify — no PostgreSQL or Redis required for Langflow itself.

---

## 6. Deep Dive: Evaluated Alternatives

### 6.1 Microsoft Agent Framework (MAF) — 9.5k★

Enterprise successor to AutoGen. Features graph-based workflows, Azure-native integrations, and OpenTelemetry tracing. **Not yet production-ready** — API is still stabilizing. Reconsider when MAF reaches v1.0 and proves its graph execution model is superior to LangGraph for NIC porting use cases.

### 6.2 CrewAI — 49k★ (Fallback)

The documented fallback if ClawTeam risks become unacceptable. Quick migration path:

1. Replace `clawteam task create` → `Crew.kickoff()` with `Process.sequential`/`.hierarchical`
2. Replace `clawteam spawn tmux` → in-process agent execution (loses worktree isolation)
3. Add custom `GitWorktreeTool` to replicate worktree management
4. Rebuild kanban tracking via callback handlers

**Migration cost**: ~2 days. **Capability loss**: git worktree isolation, tmux-based agent spawn, CLI ergonomics.

### 6.3 smolagents — 26.6k★

Hugging Face's lightweight code-first agent framework. Minimal dependencies, good for simple pipelines. Potential future alternative for Tier 1 coding tasks if Aider proves too heavy. CLI-compatible via `smolagents run`.

### 6.4 AutoGen — 57.1k★

> ⚠️ **MAINTENANCE MODE — DO NOT ADOPT**

Microsoft has deprecated AutoGen in favor of MAF. The codebase receives security patches only. No new features. Existing AutoGen deployments should plan migration to MAF or LangGraph.

### 6.5 Dify — ~92k★ (Replaced by Langflow)

Dify offered excellent RAG and workflow capabilities but required PostgreSQL + Redis + Docker infrastructure. Langflow provides equivalent functionality with lighter infrastructure and native MCP support. Dify remains a valid option as an **optional RAG UI layer** (see Section 8.4) but is not in the recommended stack.

---

## 7. Dual Orchestrator Architecture

**Source**: `nic_porting_dual_orchestrator.py`

The dual orchestrator model splits responsibilities between ClawTeam (core) and Agent Orchestrator (secondary). This avoids either tool trying to do everything and keeps failure domains isolated.

### 7.1 Routing Table

Events are routed by prefix matching (first match wins):

| Prefix | Orchestrator | Domain |
|--------|:------------:|--------|
| `task.*` | **CORE** (ClawTeam) | Task creation, assignment, completion |
| `agent.*` | **CORE** | Agent spawn, health, termination |
| `phase.*` | **CORE** | Phase transitions, gate checks |
| `inbox.*` | **CORE** | Inter-agent messaging |
| `risk.*` | **CORE** | Risk register, mitigations |
| `ci.*` | **SECONDARY** (AO) | CI build triggers, results |
| `pr.*` | **SECONDARY** | Pull request creation, reviews |
| `dashboard.*` | **SECONDARY** | Dashboard updates, metrics |
| `notify.*` | **SECONDARY** | Notifications, alerts |
| `session.*` | **SECONDARY** | Session management |
| `feedback.*` | **SECONDARY** | CI failure feedback loop |

Unknown event prefixes default to CORE.

```python
# From nic_porting_dual_orchestrator.py
class OrchestratorRole(Enum):
    CORE = "clawteam"
    SECONDARY = "agent-orchestrator"

_ROUTING_TABLE: list[tuple[str, OrchestratorRole]] = [
    ("task.", OrchestratorRole.CORE),
    ("agent.", OrchestratorRole.CORE),
    ("phase.", OrchestratorRole.CORE),
    ("inbox.", OrchestratorRole.CORE),
    ("risk.", OrchestratorRole.CORE),
    ("ci.", OrchestratorRole.SECONDARY),
    ("pr.", OrchestratorRole.SECONDARY),
    ("dashboard.", OrchestratorRole.SECONDARY),
    ("notify.", OrchestratorRole.SECONDARY),
    ("session.", OrchestratorRole.SECONDARY),
    ("feedback.", OrchestratorRole.SECONDARY),
]
```

### 7.2 State Synchronization

Both orchestrators share state via JSON file with atomic writes (tmp + rename pattern):

- `sync_state()` — Merge incoming state dict into shared `sync_state.json`
- Supports bidirectional sync: `core_to_secondary` and `secondary_to_core`
- Every sync records `_last_sync_direction` and `_last_sync_timestamp`

```python
# API
orch = build_dual_orchestrator(work_dir, clawteam_team="ice-port", ao_endpoint="http://127.0.0.1:3000")
role = route_event(orch, event)           # → OrchestratorRole.CORE or .SECONDARY
dispatch_to_core(orch, "task.create", {…})
dispatch_to_secondary(orch, "ci.trigger", {…})
sync_state(orch, state_dict, direction="core_to_secondary")
```

### 7.3 Unified Status

`get_unified_status()` provides a combined view:

```json
{
  "core": { "role": "clawteam", "team": "ice-port" },
  "secondary": { "role": "agent-orchestrator", "endpoint": "http://127.0.0.1:3000" },
  "sync_health": {
    "last_sync_direction": "core_to_secondary",
    "last_sync_timestamp": 1744800000.0
  },
  "event_log_count": 42
}
```

---

## 8. RAG Knowledge Layer

**Source**: `nic_porting_rag.py`

The RAG layer provides searchable knowledge to all agents. Rather than re-reading entire porting guides on every query, agents search a pre-indexed knowledge store.

### 8.1 Current: TF-IDF Local Search

Zero external dependencies. Ships today.

- **Document model**: `Document(content, source, metadata, doc_id)`
- **Chunking**: 512 tokens per chunk, 64-token overlap. Splits on paragraph boundaries and markdown headings.
- **Tokenizer**: Lowercase + stop-word removal (no stemming)
- **Index**: `_TFIDFIndex` — in-memory TF-IDF with cosine similarity
- **API**:

```python
store = build_knowledge_store(data_dir=Path("./rag"))
index_directory(store, Path("docs/"), glob="*.md")
index_text(store, "Custom knowledge", source="manual")
results = query_knowledge(store, "DMA ring buffer allocation", top_k=5)
```

### 8.2 LangChain Embedded RAG

When `PORTING_EMBEDDINGS=openai` is set with a valid `OPENAI_API_KEY`, the knowledge store uses OpenAI embeddings for higher-quality semantic retrieval. Falls back to TF-IDF automatically if the API is unreachable.

### 8.3 Qdrant Planned Upgrade

For production workloads, Qdrant replaces the in-memory TF-IDF index:

| Dimension | TF-IDF (current) | Qdrant (planned) |
|-----------|-------------------|-------------------|
| Dependencies | None | Docker container |
| Persistence | None (rebuilt on start) | Disk-backed |
| Search quality | Lexical only | Semantic (dense vectors) |
| Scale | <10k documents | Millions |
| Filtering | Metadata via Python | Native payload filters |

**Migration path**: Replace `_TFIDFIndex` with `QdrantClient` in `nic_porting_rag.py`. The `KnowledgeStore` public API (`build_knowledge_store`, `index_text`, `query_knowledge`) remains unchanged.

### 8.4 Dify as Optional RAG UI

Dify can serve as a richer RAG frontend with document upload UI, knowledge base management, and conversation-based retrieval. This is **not required** for CLI-driven workflows but may benefit teams who prefer visual document management. Dify would sit alongside (not replace) the Python-native RAG layer.

### 8.5 What Gets Indexed

| Content Source | Format | Auto-Indexed |
|---------------|--------|:------------:|
| Porting guides (9 volumes from `.github/skills/`) | Markdown | ✅ |
| Driver source documentation | C headers, comments | ✅ |
| API mapping tables | Markdown tables | ✅ |
| Risk register entries | JSON | ✅ |
| Debate logs | JSON | ✅ |
| Phase gate summaries | Markdown | ✅ |

---

## 9. Messaging Bridge

**Source**: `nic_porting_messaging.py`

The messaging bridge enables communication between ClawTeam (filesystem inbox) and Agent Orchestrator (HTTP events). It is a pure module with no hard dependency on either runtime.

### 9.1 Pub/Sub Model

```python
broker = build_broker(data_dir=Path("./messages"))
sub = subscribe(broker, subscriber="risk-auditor", topic="phase.*")
publish(broker, sender="orchestrator", topic="phase.completed", payload={"phase": 5})
messages = receive_messages(broker, subscriber="risk-auditor")  # Destructive read
```

- **Topic patterns**: fnmatch globs (e.g., `phase.*`, `ci.failed.*`, `*`)
- **Direct messages**: Set `recipient` parameter for point-to-point delivery
- **Broadcast**: `broadcast()` delivers to all matching subscribers
- **TTL expiration**: Messages expire after `ttl_seconds` (stale CI results auto-purged)

### 9.2 ClawTeam → AO Bridge

`bridge_clawteam_to_ao()` transforms ClawTeam inbox messages into AO-compatible events:

```
ClawTeam format:                    AO format:
{from_agent, to, content,    →     {type: "agent_message",
 msg_type, metadata}                 source: "clawteam",
                                     payload: {from_agent, to_agent,
                                               content, msg_type, metadata}}
```

### 9.3 AO → ClawTeam Bridge

`bridge_ao_to_clawteam()` transforms AO events into ClawTeam inbox messages:

```
AO format:                          ClawTeam format:
{type, session_id?,           →     {from_agent: "agent-orchestrator",
 payload: {error?, status?,          to: target_agent,
           log_url?, message?}}      content: "[AO:type] status=... log=...",
                                     msg_type: "message"}
```

AO reactions (e.g., `ci-failed` auto-retry) are translated into `[AO:ci-failed]` prefixed messages that ClawTeam agents can parse and act on.

### 9.4 n8n Webhooks (Optional)

For teams using n8n as integration glue: ClawTeam phase completion events can trigger n8n webhooks, which forward to AO dashboard endpoints. This is optional — the Python bridge handles the same flow without n8n.

### 9.5 TTL Expiration

Messages include optional `ttl_seconds`. The `receive_messages()` function filters expired messages on read (lazy expiration). Use TTL for:

- CI failure logs: 1 hour TTL (stale after retry)
- Phase completion notifications: No TTL (permanent)
- Health check pings: 60-second TTL

### 9.6 Redis Roadmap (ClawTeam v0.4)

When ClawTeam v0.4 ships, Redis serves **triple duty**:

| Function | Current | Redis (planned) |
|----------|---------|------------------|
| Message broker | Filesystem queues | Redis Pub/Sub + Streams |
| RAG cache | None | Redis as vector similarity cache |
| Event bus | In-memory `_event_log` | Redis Streams with persistence |

**Timeline**: Dependent on ClawTeam v0.4 release. No hard date. The current filesystem-based approach works for single-node deployments. Redis becomes necessary for multi-node or high-throughput scenarios.

---

## 10. Comparison Matrices

### 10.1 Core Capabilities

| Capability | LangGraph | ClawTeam | AO | GitNexus | Aider | Codex CLI | OpenHands | Langflow |
|-----------|:---------:|:--------:|:--:|:--------:|:-----:|:---------:|:---------:|:--------:|
| State machine | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Task management | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Git worktrees | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Agent spawn (tmux) | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| CI/PR integration | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Code intelligence | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Code editing | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ |
| Sandbox execution | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| Visual dashboard | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| MCP tools | ❌ | ✅ (28) | ❌ | ✅ (14+) | ❌ | ❌ | ❌ | ✅ |
| Checkpoints | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

### 10.2 Security Comparison

| Dimension | v1 (all-in) | v2 (no ClawTeam) | v3/v4 (ClawTeam + mitigations) |
|-----------|:-----------:|:-----------------:|:------------------------------:|
| Supply chain risk | 🔴 High (OpenClaw) | 🟢 Low | 🟡 Medium (mitigated) |
| Agent isolation | 🟡 Medium | 🟢 High (CrewAI in-process) | 🟢 High (worktrees + chmod 0700) |
| Network exposure | 🔴 High (0.0.0.0 binds) | 🟢 Low (127.0.0.1) | 🟢 Low (127.0.0.1) |
| Data at rest | 🔴 Unprotected | 🟢 Protected | 🟡 Protected (chmod) |
| Audit trail | 🔴 None | 🟡 Partial | 🟢 Full (event log + sync state) |

### 10.3 Infrastructure Requirements

| Component | Process Type | Port | Memory | Docker | Dependencies |
|-----------|:------------|:----:|-------:|:------:|-------------|
| LangGraph | Python | — | 200 MB | No | `langgraph>=0.3.0`, `langchain-core>=0.3.0` |
| ClawTeam | Python | — | 50 MB | No | `clawteam>=0.3.0`, tmux |
| Agent Orchestrator | Node.js | 3000 | 150 MB | No | pnpm, Node 18+ |
| GitNexus | Node.js | 4747 | 300 MB | No | npm, Node 18+ |
| Aider | Python | — | 100 MB | No | `aider-chat` |
| Codex CLI | Rust binary | — | 50 MB | No | npm or brew |
| OpenHands | Python | 3001 | 500 MB | **Yes** | Docker |
| Langflow | Python | 7860 | 200 MB | No | `langflow` |
| Temporal (optional) | Go | 7233 | 300 MB | **Yes** | docker-compose |
| Qdrant (optional) | Rust | 6333 | 500 MB | **Yes** | Docker |

### 10.4 Porting-Specific Capabilities

| Capability | ClawTeam | CrewAI | AO | GitNexus | LangGraph |
|-----------|:--------:|:------:|:--:|:--------:|:---------:|
| Phase-gated pipeline | ✅ (task deps) | ✅ (Process) | ❌ | ❌ | ✅ (edges) |
| TDD-first enforcement | ✅ (task ordering) | ✅ (task deps) | ❌ | ❌ | ✅ (conditional) |
| Maker-checker debate | ✅ (inbox) | ✅ (delegation) | ❌ | ❌ | ✅ (GROUP_CHAT) |
| Risk register | ❌ (manual) | ❌ | ❌ | ❌ | ✅ (state field) |
| Gate enforcement | ❌ (manual) | ❌ | ❌ | ❌ | ✅ (conditional edges) |
| Cross-compile validation | ❌ | ❌ | ✅ (CI) | ❌ | ❌ |
| Blast-radius analysis | ❌ | ❌ | ❌ | ✅ | ❌ |

### 10.5 Orchestration Pattern Suitability

| Framework | SEQUENTIAL | CONCURRENT | GROUP_CHAT | HANDOFF | MAGENTIC |
|-----------|:----------:|:----------:|:----------:|:-------:|:--------:|
| LangGraph | ✅ | ✅ | ✅ | ✅ | ✅ |
| ClawTeam | ✅ | ✅ (worktrees) | ✅ (inbox) | ❌ | ❌ |
| AO | ✅ | ❌ | ❌ | ❌ | ❌ |
| CrewAI | ✅ | ✅ | ✅ | ✅ | ❌ |

---

## 11. Phase-by-Phase Tool Assignment

### Gate Thresholds

```python
GATE_NATIVE_THRESHOLD = 98.0       # Percentage of native API calls (no framework contamination)
GATE_PORTABILITY_THRESHOLD = 95.0   # Cross-compile success rate
# Test pass rate: 100% (non-negotiable)
# Critical risks: 0 (blocks phase transition)
```

### Tool Assignment Table

| Phase | Primary Tool | Supporting Tools | Pattern | Worker Roles | Gate Criteria |
|:-----:|-------------|-----------------|---------|-------------|---------------|
| 0 | ClawTeam | Aider, GitNexus | SEQUENTIAL | `linux-analyst` | File manifest emitted, baseline hash locked |
| 1 | ClawTeam | GitNexus, Aider | CONCURRENT | `api-mapper`, `kpi-auditor` | 1:1 API mapping table complete, auditor approved |
| 2 | ClawTeam | Aider | SEQUENTIAL | `seam-architect` | OAL seam headers compile on both targets |
| 3 | ClawTeam | Aider, Codex CLI | SEQUENTIAL | `tdd-writer` | All tests written, all fail (red) |
| 4 | ClawTeam | Codex CLI, OpenHands | CONCURRENT | `coder` | All tests pass (green), native_score ≥ 98 |
| 5 | LangGraph | ClawTeam, AO, GitNexus | GROUP_CHAT | `native-validator`, `code-reviewer`, `performance-engineer`, `portability-validator`, `risk-auditor`, `verification-executor` | native ≥ 98, portability ≥ 95, tests = 100%, critical_risks = 0 |
| 6 | ClawTeam | AO | SEQUENTIAL | `merge-strategist` | Clean merge, no regressions, portability ≥ 95 |
| 7 | LangGraph | ClawTeam | MAGENTIC | `os-extension-validator`, `risk-auditor-final` | Seam extensibility proven for ≥2 target OSes |

### Worker Roles (18 total)

| Role | Phase | Priority | Pattern | Checker? |
|------|:-----:|----------|---------|:--------:|
| `linux-analyst` | 0 | critical | SEQUENTIAL | ❌ |
| `api-mapper` | 1 | critical | CONCURRENT | ❌ |
| `kpi-auditor` | 1 | critical | CONCURRENT | ✅ |
| `seam-architect` | 2 | high | SEQUENTIAL | ❌ |
| `tdd-writer` | 3 | critical | SEQUENTIAL | ❌ |
| `coder` | 4 | critical | CONCURRENT | ❌ |
| `native-validator` | 5 | critical | GROUP_CHAT | ✅ |
| `code-reviewer` | 5 | high | GROUP_CHAT | ✅ |
| `performance-engineer` | 5 | high | GROUP_CHAT | ❌ |
| `portability-validator` | 5 | high | GROUP_CHAT | ✅ |
| `risk-auditor` | 5 | high | GROUP_CHAT | ❌ |
| `verification-executor` | 5 | critical | CONCURRENT | ❌ |
| `merge-strategist` | 6 | medium | SEQUENTIAL | ❌ |
| `os-extension-validator` | 7 | medium | CONCURRENT | ❌ |
| `risk-auditor-final` | 7 | high | MAGENTIC | ❌ |

---

## 12. Deployment Automation

### 12.1 Service Matrix

| Service | Port | Bind | Start Command | Health Check |
|---------|:----:|:----:|--------------|-------------|
| LangGraph | — | — | Python process (embedded) | Process alive |
| ClawTeam | — | — | `clawteam team create` | `clawteam board show` |
| Agent Orchestrator | 3000 | 127.0.0.1 | `pnpm start` | `curl http://127.0.0.1:3000/health` |
| GitNexus | 4747 | 127.0.0.1 | `npm start` | `curl http://127.0.0.1:4747/health` |
| Langflow | 7860 | 127.0.0.1 | `langflow run --port 7860` | `curl http://127.0.0.1:7860/health` |
| Qdrant (optional) | 6333 | 127.0.0.1 | `docker run qdrant/qdrant` | `curl http://127.0.0.1:6333/health` |
| Temporal (optional) | 7233 | 127.0.0.1 | `docker-compose up` | `tctl cluster health` |

### 12.2 Installer Script Structure

The unified installer (`setup-unified-stack.sh`) follows a 10-phase auto-configuration flow:

```bash
#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

# Phase 1: Prerequisites check
check_prerequisites() {
    command_exists python3 && [[ $(python3 --version | grep -oP '\d+\.\d+') > "3.9" ]]
    command_exists node && [[ $(node --version | grep -oP '\d+') -ge 18 ]]
    command_exists docker
    command_exists git
    command_exists tmux
}

# Phase 2: Python virtualenv + deps
setup_python() {
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements-nic-swarm.txt
    pip install langflow aider-chat
}

# Phase 3: Node services
setup_node_services() {
    (cd submodules/gitnexus && npm install)
    (cd submodules/agent-orchestrator && pnpm install)
}

# Phase 4: Codex CLI
setup_codex() {
    npm install -g @openai/codex 2>/dev/null || brew install codex 2>/dev/null
}

# Phase 5: OpenHands Docker
setup_openhands() {
    docker pull ghcr.io/all-hands-ai/openhands:latest
}

# Phase 6: Security hardening
harden_stack() {
    # ClawTeam
    chmod -R 0700 "${CLAWTEAM_DATA_DIR:-$HOME/.clawteam}"
    # AO — ensure 127.0.0.1 binding
    sed -i 's/0\.0\.0\.0/127.0.0.1/g' configs/ao-nic-porting.yaml
    # Remove OpenClaw references
    sed -i 's/openclaw/aider/g' scripts/setup-full-stack.conf
}

# Phase 7: RAG knowledge store
setup_rag() {
    python3 -c "
from nic_porting_rag import build_knowledge_store, index_directory
from pathlib import Path
store = build_knowledge_store(Path('./rag'))
index_directory(store, Path('.github/skills/nic-porting-guide-references/'), glob='*.md')
index_directory(store, Path('docs/'), glob='*.md')
print(f'Indexed {len(store._index._docs)} chunks')
"
}

# Phase 8: Messaging bridge
setup_messaging() {
    python3 -c "
from nic_porting_messaging import build_broker, subscribe
from pathlib import Path
broker = build_broker(Path('./messages'))
subscribe(broker, 'agent-orchestrator', 'phase.*')
subscribe(broker, 'agent-orchestrator', 'risk.*')
subscribe(broker, 'risk-auditor', 'phase.*')
subscribe(broker, 'risk-auditor', 'ci.*')
print('Messaging bridge configured')
"
}

# Phase 9: Langflow dashboard
setup_langflow() {
    langflow run --port 7860 --host 127.0.0.1 &
    echo "Langflow dashboard: http://127.0.0.1:7860"
}

# Phase 10: Validation
validate_stack() {
    echo "Checking services..."
    curl -sf http://127.0.0.1:3000/health  && echo "✅ AO"
    curl -sf http://127.0.0.1:4747/health  && echo "✅ GitNexus"
    curl -sf http://127.0.0.1:7860/health  && echo "✅ Langflow"
    clawteam team list                      && echo "✅ ClawTeam"
    echo "Stack ready."
}
```

### 12.3 Configuration Template

The team template (`templates/nic-porting.toml`) defines the ClawTeam team structure:

- **Leader**: `orchestrator` — plans/routes only, does not implement
- **4 agents**: `test-writer`, `porting-coder`, `checker`, `risk-auditor`
- **8 tasks**: One per pipeline phase with dependency chains
- **Backend**: `tmux` (default), configurable
- **Agent command**: `claude` (default in template; override with `--agent-command aider`)

### 12.4 MCP Server Configuration

| MCP Server | Tools | Protocol |
|-----------|------:|----------|
| ClawTeam | 28 | stdio |
| GitNexus | 14+ | HTTP (port 4747) |
| Langflow | Dynamic | HTTP (port 7860) |

### 12.5 Dashboard Auto-Publishing

Langflow dashboards are auto-published via:

1. Export workflow as JSON from Langflow UI
2. Import on fresh instance: `langflow import --file nic-porting-dashboard.json`
3. Or serve via MCP: Langflow's MCP mode exposes workflows as tools

AO dashboard (port 3000) auto-publishes pipeline status with no additional configuration.

---

## 13. Comprehensive Implementation Steps

These 18 steps take a fresh environment to a fully operational NIC porting pipeline. Execute in order — each step depends on the previous.

### Step 1: Prerequisites Check

```bash
python3 --version   # >= 3.10
node --version      # >= 18
docker --version
git --version
tmux -V
```

### Step 2: Python Environment

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-nic-swarm.txt
# Includes: langgraph, langchain-core, langchain-openai, clawteam, temporalio
```

### Step 3: Install Codex CLI

```bash
npm install -g @openai/codex
# Or: brew install codex
codex --version
```

### Step 4: Pull OpenHands Docker Image

```bash
docker pull ghcr.io/all-hands-ai/openhands:latest
```

### Step 5: Install GitNexus

```bash
cd submodules/gitnexus && npm install && cd -
# Verify: node submodules/gitnexus/src/index.js --port 4747 &
```

### Step 6: Install Agent Orchestrator

```bash
cd submodules/agent-orchestrator && pnpm install && cd -
# Harden: ensure configs/ao-nic-porting.yaml binds to 127.0.0.1
sed -i 's/0\.0\.0\.0/127.0.0.1/g' configs/ao-nic-porting.yaml
```

### Step 7: Harden ClawTeam

```bash
chmod -R 0700 "${CLAWTEAM_DATA_DIR:-$HOME/.clawteam}"
# Pin to known-good commit in requirements.txt:
# clawteam @ git+https://github.com/…@<known-good-sha>#egg=clawteam
```

Create `SECURITY.md` with disclosure process if not present upstream.

### Step 8: Remove OpenClaw from All Configs

```bash
# .vscode/mcp.json — remove openclaw server entry
# scripts/setup-full-stack.conf — remove OPENCLAW_PORT, references
# scripts/nic-port-launcher.conf — remove openclaw agent option
grep -rl 'openclaw' . --include='*.conf' --include='*.yaml' --include='*.json' | \
    xargs -I{} sed -i 's/openclaw/aider/g' {}
```

### Step 9: Update Default Agent Command

```bash
# In scripts/setup-full-stack.conf:
sed -i 's/DEFAULT_AGENT_COMMAND=openclaw/DEFAULT_AGENT_COMMAND=aider/' scripts/setup-full-stack.conf
# In templates/nic-porting.toml, override at runtime:
# clawteam team create --template templates/nic-porting.toml --agent-command aider
```

### Step 10: Configure RAG Knowledge Store

```bash
python3 -c "
from nic_porting_rag import build_knowledge_store, index_directory
from pathlib import Path
store = build_knowledge_store(Path('./rag'))
index_directory(store, Path('.github/skills/nic-porting-guide-references/'), glob='*.md')
index_directory(store, Path('docs/'), glob='*.md')
"
```

### Step 11: Configure Messaging Bridge

```bash
python3 -c "
from nic_porting_messaging import build_broker, subscribe
from pathlib import Path
broker = build_broker(Path('./messages'))
subscribe(broker, 'agent-orchestrator', 'phase.*')
subscribe(broker, 'agent-orchestrator', 'risk.*')
subscribe(broker, 'risk-auditor', 'phase.*')
subscribe(broker, 'risk-auditor', 'ci.*')
"
```

### Step 12: Configure Langflow Dashboard

```bash
pip install langflow
langflow run --port 7860 --host 127.0.0.1 &
# Import NIC porting workflow if available:
# langflow import --file workflows/nic-porting-dashboard.json
```

### Step 13: Optional — Temporal for Durable Execution

```bash
# Only if production durability is required
git clone https://github.com/temporalio/docker-compose.git /tmp/temporal
cd /tmp/temporal && docker-compose up -d
```

### Step 14: Optional — Qdrant for Production RAG

```bash
docker run -d -p 6333:6333 -v qdrant_data:/qdrant/storage qdrant/qdrant
# Update PORTING_EMBEDDINGS=openai in environment
```

### Step 15: Validate Stack Health

```bash
curl -sf http://127.0.0.1:3000/health && echo "✅ Agent Orchestrator"
curl -sf http://127.0.0.1:4747/health && echo "✅ GitNexus"
curl -sf http://127.0.0.1:7860/health && echo "✅ Langflow"
clawteam team list && echo "✅ ClawTeam"
python3 -c "from nic_porting_rag import build_knowledge_store; print('✅ RAG')"
python3 -c "from nic_porting_messaging import build_broker; print('✅ Messaging')"
```

### Step 16: Create ClawTeam Team + Task Board

```bash
clawteam team create --template templates/nic-porting.toml \
    --name ice-port \
    --agent-command aider \
    --backend tmux
# Or use the bootstrap script:
bash scripts/clawteam-bootstrap.sh ice-port
```

### Step 17: Launch NIC Port Pipeline

```bash
bash scripts/nic-port-launcher.sh \
    --driver-name ice \
    --driver-repo ./submodules/ice \
    --linux-driver-path src/ice \
    --freebsd-target-path src/freebsd/ice \
    --team ice-port \
    --agent-command aider
```

### Step 18: Monitor Pipeline

```bash
# ClawTeam kanban board
clawteam board show ice-port

# Agent Orchestrator dashboard
open http://127.0.0.1:3000

# Langflow visual workflow
open http://127.0.0.1:7860

# Unified management CLI
bash scripts/clawteam-manage.sh status
bash scripts/clawteam-manage.sh phases
bash scripts/clawteam-manage.sh summary
```

---

## 14. Migration & Cost Analysis

### 14.1 Migration Paths

**From v1 (all-in stack)**:
1. Remove OpenClaw from all configs (Step 8)
2. Replace Dify with Langflow (Step 12)
3. Add security hardening (Step 7)
4. Add RAG + messaging layers (Steps 10-11)
5. Estimated effort: **4–6 days**

**From v2 (no-ClawTeam stack)**:
1. Replace CrewAI with ClawTeam (reinstall, reconfigure team templates)
2. Port CrewAI task definitions to ClawTeam TOML format
3. Replace custom `GitWorktreeTool` with native `clawteam workspace create`
4. Estimated effort: **2–3 days**

### 14.2 Runtime Cost

| Component | CPU | Memory | Disk | Docker Containers |
|-----------|:---:|-------:|-----:|:-----------------:|
| Minimum viable stack | 2 cores | 1.5 GB | 500 MB | 0 |
| Full stack (no optional) | 4 cores | 2.0 GB | 1 GB | 0 |
| Full stack + Temporal + Qdrant | 6 cores | 3.5 GB | 5 GB | 3 |
| Full stack + OpenHands | 8 cores | 4.5 GB | 10 GB | 4 |

### 14.3 LLM API Cost Estimate

| Model | Per-Phase Cost (est.) | Full Pipeline (8 phases) |
|-------|---------------------:|-------------------------:|
| GPT-4o | $2–5 | $16–40 |
| Claude Opus 4.6 | $3–8 | $24–64 |
| Local (Codex CLI offline) | $0 | $0 |
| Hybrid (local + API for debate) | $1–3 | $8–24 |

---

## 15. Conclusion

### Recommended Stack

The recommended stack for production NIC driver porting is the **8-layer architecture** described in Section 2.3:

- **LangGraph** drives the state machine and pattern execution
- **ClawTeam** coordinates agents with native worktrees and tmux spawn
- **Agent Orchestrator** handles CI/PR integration with its unique failure feedback loop
- **GitNexus** provides code intelligence via tree-sitter knowledge graph
- **Three-tier coding agents** (Aider → Codex CLI → OpenHands) match task complexity to risk
- **RAG layer** enables knowledge-backed agent decisions
- **Messaging bridge** keeps both orchestrators in sync
- **Langflow** provides visual monitoring and MCP integration

### Minimum Viable Stack

For a quick start with a single developer:

1. LangGraph + ClawTeam + Aider
2. No Docker, no Node services, no dashboard
3. Add layers incrementally as pipeline matures

### Tradeoffs

| Decision | Benefit | Cost |
|----------|---------|------|
| Retain ClawTeam | Worktrees, spawn, CLI | Supply chain risk (mitigated) |
| Prohibit OpenClaw | Security, open-source stack | Lost single-tool convenience |
| Codex CLI over Claude Code | Open source + sandbox | Newer, less battle-tested |
| Langflow over Dify | Lighter infra, MCP-native | Smaller ecosystem |
| TF-IDF RAG (default) | Zero dependencies | Lower search quality than embeddings |

---

## 16. Appendices

### Appendix A: Full Routing Table

From `nic_porting_dual_orchestrator.py`:

| Prefix | Role | Orchestrator |
|--------|------|-------------|
| `task.` | CORE | ClawTeam |
| `agent.` | CORE | ClawTeam |
| `phase.` | CORE | ClawTeam |
| `inbox.` | CORE | ClawTeam |
| `risk.` | CORE | ClawTeam |
| `ci.` | SECONDARY | Agent Orchestrator |
| `pr.` | SECONDARY | Agent Orchestrator |
| `dashboard.` | SECONDARY | Agent Orchestrator |
| `notify.` | SECONDARY | Agent Orchestrator |
| `session.` | SECONDARY | Agent Orchestrator |
| `feedback.` | SECONDARY | Agent Orchestrator |

Default (no prefix match): CORE.

### Appendix B: Worker Role Definitions

From `ai-agent-orchestration-template-03-2026.py` — 18 worker roles across 8 phases. See Section 11 for the complete table.

Additional details per role:

| Role | Handoff Targets | Dependencies |
|------|----------------|--------------|
| `seam-architect` | `portability-validator` | `api-mapper`, `kpi-auditor` |
| `code-reviewer` | `native-validator` | `coder` |
| `performance-engineer` | `native-validator` | `coder` |

### Appendix C: Message Format Specifications

**ClawTeam inbox message**:
```json
{
  "from_agent": "test-writer",
  "to": "orchestrator",
  "content": "Phase 3 TDD harness complete. 47 tests, all red.",
  "msg_type": "message",
  "metadata": {"phase": 3, "test_count": 47, "pass_count": 0}
}
```

**Agent Orchestrator event**:
```json
{
  "type": "ci-failed",
  "source": "github-actions",
  "timestamp": 1744800000.0,
  "payload": {
    "target_agent": "coder",
    "error": "FreeBSD cross-compile failed: missing ice_osdep.h",
    "log_url": "https://ci.example.com/runs/12345",
    "status": "failed"
  }
}
```

**Bridge output (AO → ClawTeam)**:
```json
{
  "from_agent": "agent-orchestrator",
  "to": "coder",
  "content": "[AO:ci-failed] FreeBSD cross-compile failed: missing ice_osdep.h status=failed log=https://ci.example.com/runs/12345",
  "msg_type": "message"
}
```

### Appendix D: Redis Unification Roadmap

**Dependency**: ClawTeam v0.4 (no release date)

| Phase | Component | Current | Redis Target |
|:-----:|-----------|---------|-------------|
| 1 | Message broker | Filesystem queues in `data_dir/` | Redis Pub/Sub + Streams |
| 2 | RAG cache | Rebuilt on every start | Redis vector similarity search |
| 3 | Event bus | In-memory `_event_log` list | Redis Streams with persistence |
| 4 | Session state | JSON file (`sync_state.json`) | Redis hash with TTL |

**Benefits**: Multi-node deployment, sub-millisecond pub/sub, persistent event history, unified monitoring via Redis Insight.

**Risk**: Adds infrastructure dependency (Redis container). For single-node deployments, the filesystem-based approach remains sufficient.

---

*This document supersedes all prior framework comparison documents (v1, v2, v3). It is the single source of truth for stack selection, deployment, and implementation of the LLM-driven NIC driver porting pipeline.*
