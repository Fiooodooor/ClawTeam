---
name: nic-porting-role-identities
description: "Use when: defining NIC porting role identities, selecting worker responsibilities, assigning handoffs, creating phase-owner matrices, or standardizing multi-agent Linux-to-FreeBSD driver workflows."
argument-hint: "Driver name, target OS, current phase, and what role identity output you need"
---

# NIC Porting Role Identities

This skill defines reusable role identities for NIC driver porting programs with strict phase gates and measurable handoff criteria.

## Use This Skill When
- You need a role matrix for a new driver porting run.
- You need to split a large objective into phase-owned tasks.
- You need explicit handoff boundaries between makers and checkers.
- You need a predefined staffing profile for ClawTeam execution.

## Canonical Role Set (aligned to nic-port-v2-rerun7 board)

| Role | Phase(s) | Pattern | Checker | Hands Off To | Agent File |
|------|----------|---------|---------|--------------|------------|
| linux-analyst | 0 (scope-baseline) | sequential | No | — | nic-porting-worker |
| api-mapper | 1 (api-mapping) | concurrent | No | — | nic-porting-worker |
| kpi-auditor | 1 (api-mapping) | concurrent | **Yes** | — | nic-porting-checker |
| seam-architect | 2 (seam-design) | sequential | No | portability-validator | nic-porting-worker |
| tdd-writer | 3 (tdd-harness) | sequential | No | — | nic-porting-worker |
| coder | 4 (incremental-port) | concurrent | No | performance-engineer, seam-architect | nic-porting-worker |
| native-validator | 4 (incremental-port) | group_chat | **Yes** | portability-validator | nic-porting-checker |
| code-reviewer | 4 (incremental-port) | group_chat | **Yes** | — | nic-porting-checker |
| performance-engineer | 5 (gates) | concurrent | No | — | nic-porting-worker |
| portability-validator | 5 (gates) | concurrent | No | — | nic-porting-checker |
| verification-executor | 5 (gates) | sequential | No | — | nic-porting-worker |
| merge-strategist | 6 (merge-sync) | sequential | No | — | nic-porting-worker |
| risk-auditor | 7 (multi-os-extension) | magentic | No | — | nic-porting-risk-auditor |
| os-extension-validator | 7 (multi-os-extension) | concurrent | No | — | nic-porting-worker |

## Phase-to-Role Ownership

| Phase | Key | Makers | Checkers | Gate Owner |
|-------|-----|--------|----------|------------|
| 0 | scope-baseline | linux-analyst | — | orchestrator |
| 1 | api-mapping | api-mapper | kpi-auditor | orchestrator |
| 2 | seam-design | seam-architect | — | orchestrator |
| 3 | tdd-harness | tdd-writer | — | orchestrator |
| 4 | incremental-port | coder | native-validator, code-reviewer | orchestrator |
| 5 | gates | performance-engineer, portability-validator, verification-executor | — | orchestrator |
| 6 | merge-sync | merge-strategist | — | orchestrator |
| 7 | multi-os-extension | os-extension-validator | — | risk-auditor |

## Agent-to-Role Mapping

| Agent File | Roles It Serves |
|------------|----------------|
| nic-porting-orchestrator | root-orchestrator (phase transitions, gate decisions) |
| nic-porting-worker | linux-analyst, api-mapper, seam-architect, tdd-writer, coder, performance-engineer, verification-executor, merge-strategist, os-extension-validator |
| nic-porting-checker | kpi-auditor, native-validator, code-reviewer, portability-validator |
| nic-porting-risk-auditor | risk-auditor |

## Required Handoff Contracts
- Every handoff must include: objective, changed files, gate criteria, and blockers.
- Maker-to-checker handoff must include evidence artifacts, not just claims.
- A failed gate returns ownership to the previous maker with actionable deltas.
- Checker agents follow the structured debate protocol (up to 5 rounds).
- Risk-auditor has cross-phase veto power on critical risks.

## Gate Metrics

| Metric | Threshold | Enforced By |
|--------|-----------|-------------|
| native_score | >= 98.0 | nic-porting-checker |
| portability_score | >= 95.0 | nic-porting-checker |
| test_pass_rate | = 100% | nic-porting-checker |
| critical_risks | = 0 | nic-porting-risk-auditor |
| build_status | = green | nic-porting-orchestrator |

## Output Template
Produce outputs with these sections:
1. Role Matrix (from canonical table above)
2. Phase Owners (maker/checker/gate-owner per phase)
3. Handoff Graph (who hands off to whom with `can_handoff_to` links)
4. Gate Thresholds (metric, threshold, enforcer)
5. Recovery Paths (what happens on gate failure per phase)
6. Agent File Mapping (which `.agent.md` serves each role)
