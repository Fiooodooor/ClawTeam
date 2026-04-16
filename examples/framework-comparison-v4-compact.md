# LLM Framework Secure Stack — Compact Reference v4.0

> **Date:** 2026-04-16 | **Scope:** Linux→FreeBSD NIC driver porting — multi-agent orchestration  
> **Full document:** See `LLM-Framework-Secure-Stack-Comparison.md` for implementation details, migration paths, deployment automation, and appendices.  
> **Constraints:** ClawTeam = RETAINED | OpenClaw = PROHIBITED | AutoGen = MAINTENANCE MODE

---

## 1. Recommended 8-Layer Stack

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

## 2. Quick Decision Matrix

| Use Case | Minimum Stack | Full Stack |
|----------|---------------|------------|
| Single-driver port, one developer | LangGraph + Aider | — |
| Multi-file port, TDD pipeline | LangGraph + ClawTeam + Aider | + GitNexus |
| Full production pipeline with CI/CD | All 8 layers | + Temporal + Qdrant |

## 3. Phase-to-Pattern Mapping

| Phase | Name | Pattern | Why |
|:-----:|------|---------|-----|
| 0 | Scope & Baseline Lock | **SEQUENTIAL** | Linear — baseline must lock before analysis |
| 1 | API Inventory & Mapping | **CONCURRENT** | Embarrassingly parallel per source file |
| 2 | Seam Architecture | **SEQUENTIAL** | Depends on complete API mapping |
| 3 | TDD Harness | **SEQUENTIAL** | Tests must compile against seam headers first |
| 4 | Incremental Port | **CONCURRENT** | Parallel worktrees: TX, RX, admin, interrupts |
| 5 | Validation Gates | **GROUP_CHAT** | Adversarial debate: validators + reviewers + auditor |
| 6 | Merge & Sync | **SEQUENTIAL** | Single merge operation |
| 7 | Multi-OS Extension | **MAGENTIC** | Open-ended planning with living task ledger |

## 4. Framework Catalog

### In-Stack (Recommended)

| Framework | Stars | License | Layer | Role |
|-----------|------:|---------|:-----:|------|
| LangGraph | 29.4k | MIT | 0 | State machine orchestration |
| ClawTeam | — | MIT | 1 | Multi-agent coordination (core) |
| Agent Orchestrator | — | Proprietary | 2 | CI/PR/dashboard (secondary) |
| Aider | 43.4k | Apache-2.0 | 3 | Tier 1 coding agent (edit-only, lowest risk) |
| Codex CLI | 75.6k | Apache-2.0 | 3 | Tier 2 coding agent (bubblewrap-sandboxed) |
| OpenHands | 71.3k | MIT | 3 | Tier 3 coding agent (Docker-sandboxed) |
| GitNexus | — | MIT | 4 | Tree-sitter knowledge graph, 14+ MCP tools |
| Langflow | 147k | MIT | 7 | Visual workflow dashboard, MCP-native |

### Evaluated — Not Selected

| Framework | Stars | License | Status | Reason |
|-----------|------:|---------|--------|--------|
| CrewAI | 49k | MIT | Fallback | Backup if ClawTeam risks unacceptable |
| MAF | 9.5k | MIT | Watch | AutoGen successor; not production-ready |
| smolagents | 26.6k | Apache-2.0 | Watch | Lightweight code-first; potential Tier 1 alt |
| AutoGen | 57.1k | MIT | ⚠️ DEPRECATED | Microsoft maintenance mode — do not adopt |
| Dify | ~92k | Apache-2.0 | Replaced | Replaced by Langflow (MCP-native, lighter) |

## 5. Core Capability Matrix

| Capability | LangGraph | ClawTeam | AO | GitNexus | Aider | Codex | OpenHands | Langflow |
|-----------|:---------:|:--------:|:--:|:--------:|:-----:|:-----:|:---------:|:--------:|
| State machine | ✅ | — | — | — | — | — | — | ✅ |
| Task management | — | ✅ | — | — | — | — | — | — |
| Git worktrees | — | ✅ | — | — | — | — | — | — |
| Agent spawn (tmux) | — | ✅ | — | — | — | — | — | — |
| CI/PR integration | — | — | ✅ | — | — | — | — | — |
| Code intelligence | — | — | — | ✅ | — | — | — | — |
| Code editing | — | — | — | — | ✅ | ✅ | ✅ | — |
| Sandbox execution | — | — | — | — | — | ✅ | ✅ | — |
| MCP tools | — | ✅(28) | — | ✅(14+) | — | — | — | ✅ |
| Checkpoints | ✅ | — | — | — | — | — | — | — |

## 6. Security Comparison

| Dimension | v1 (all-in) | v2 (no ClawTeam) | v3/v4 (ClawTeam + mitigations) |
|-----------|:-----------:|:-----------------:|:------------------------------:|
| Supply chain risk | 🔴 High (OpenClaw) | 🟢 Low | 🟡 Medium (mitigated) |
| Agent isolation | 🟡 Medium | 🟢 High | 🟢 High (worktrees + chmod 0700) |
| Network exposure | 🔴 High (0.0.0.0) | 🟢 Low (127.0.0.1) | 🟢 Low (127.0.0.1) |
| Audit trail | 🔴 None | 🟡 Partial | 🟢 Full (event log + sync state) |

## 7. Dual Orchestrator Architecture

### Routing Table

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

Default (no prefix match) → CORE.

### Responsibility Split

| Responsibility | ClawTeam (Core) | AO (Secondary) |
|---------------|:---------------:|:--------------:|
| Phase lifecycle (0–7) | **Owner** | Reads status |
| Worker spawning | `clawteam spawn tmux` | Own sessions |
| Task board / kanban | `TaskStore` | — |
| Inbox messaging | `MailboxManager` | WebSocket |
| CI/PR feedback loop | — | **Owner** (reaction engine) |
| Auto error recovery | Manual replan | **Auto-retry + escalation** |
| Dashboard | WebGUI (:31082) | **React (:3000)** |
| Gate enforcement | LangGraph conditional edges | — |

## 8. RAG Knowledge Layer

| Dimension | TF-IDF (current) | Qdrant (planned) |
|-----------|:-----------------:|:-----------------:|
| Dependencies | None | Docker container |
| Persistence | Rebuilt on start | Disk-backed |
| Search quality | Lexical only | Semantic (dense vectors) |
| Scale | < 10k docs | Millions |

**What gets indexed:** 9 porting guide volumes, driver source docs, API mapping tables, risk register entries, debate logs, phase gate summaries.

**Integration point:** `node_load_guide()` in orchestrator scripts. Replace static text injection with `build_knowledge_store()` + `query_knowledge()`.

## 9. Messaging Bridge

**Model:** Pub/sub with topic-pattern subscriptions (fnmatch globs).

| Direction | Mechanism |
|-----------|-----------|
| ClawTeam → AO | Phase transition broadcasts → bridge → AO dashboard API |
| AO → ClawTeam | Reaction webhooks (ci-failed, changes-requested) → `mailbox.send()` |
| Worker ↔ Worker | ClawTeam inbox (filesystem-based `MailboxManager`) |

**TTL expiration:** CI failure logs (1h), phase completions (permanent), health pings (60s).

**Redis roadmap (ClawTeam v0.4):** Unifies message broker, RAG cache, and event bus into Redis Pub/Sub + Streams.

## 10. Phase-by-Phase Tool & Worker Assignment

| Phase | Primary Tool | Pattern | Worker Roles | Gate Criteria |
|:-----:|-------------|---------|-------------|---------------|
| 0 | ClawTeam | SEQ | `linux-analyst` | Baseline hash locked |
| 1 | ClawTeam | CONC | `api-mapper`, `kpi-auditor` | API mapping complete |
| 2 | ClawTeam | SEQ | `seam-architect` | OAL headers compile |
| 3 | ClawTeam | SEQ | `tdd-writer` | All tests fail (red) |
| 4 | ClawTeam | CONC | `coder` | Tests pass, native ≥ 98 |
| 5 | LangGraph | GC | `native-validator`, `code-reviewer`, `perf-engineer`, `portability-validator`, `risk-auditor`, `verification-executor` | native ≥ 98, portability ≥ 95, tests 100%, risks 0 |
| 6 | ClawTeam | SEQ | `merge-strategist` | Clean merge, no regressions |
| 7 | LangGraph | MAG | `os-extension-validator`, `risk-auditor-final` | Seams extend to ≥ 2 OSes |

### Gate Thresholds

```
native_score       ≥ 98.0   (zero non-native API calls)
portability_score  ≥ 95.0   (cross-compile matrix clean)
test_pass_rate     = 100%   (all tests green)
build_status       = green   (Linux + FreeBSD compile)
critical_risks     = 0       (no open critical risks)
```

## 11. Three-Tier Coding Agents

| Tier | Agent | Sandbox | Risk | Spawn Command | Use When |
|:----:|-------|---------|------|---------------|----------|
| 1 | Aider | None (edit-only) | Lowest | `clawteam spawn tmux aider` | Simple edits, TDD red→green |
| 2 | Codex CLI | bubblewrap | Medium | `clawteam spawn tmux codex` | Multi-file, compilation |
| 3 | OpenHands | Docker | Highest | `clawteam spawn tmux openhands` | Full build/test cycles |

## 12. Deployment Service Matrix

| Service | Port | Bind | Docker | Memory |
|---------|:----:|:----:|:------:|-------:|
| LangGraph | — | — | No | 200 MB |
| ClawTeam | — | — | No | 50 MB |
| Agent Orchestrator | 3000 | 127.0.0.1 | No | 150 MB |
| GitNexus | 4747 | 127.0.0.1 | No | 300 MB |
| Langflow | 7860 | 127.0.0.1 | No | 200 MB |
| Temporal (opt.) | 7233 | 127.0.0.1 | Yes | 300 MB |
| Qdrant (opt.) | 6333 | 127.0.0.1 | Yes | 500 MB |

## 13. Key Decisions

| Decision | Benefit | Cost |
|----------|---------|------|
| Retain ClawTeam | Worktrees, spawn, CLI | Supply chain risk (mitigated) |
| Prohibit OpenClaw | Security, open-source stack | Lost single-tool convenience |
| Codex CLI over Claude Code | Open source + sandbox | Newer, less battle-tested |
| Langflow over Dify | Lighter infra, MCP-native | Smaller ecosystem |
| TF-IDF RAG (default) | Zero dependencies | Lower quality than embeddings |

---

*Compact reference. See the full v4.0 document for: 18-step implementation walkthrough, installer scripts, migration paths from v1/v2/v3, cost analysis, message format JSON specs, and appendices.*
