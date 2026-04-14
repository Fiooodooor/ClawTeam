---
name: "NIC Orchestrator Governance"
description: "Rules for Linux-to-FreeBSD NIC porting orchestration with phase gates, TDD-first sequencing, and role handoffs."
applyTo: "**"
---
# NIC Porting Orchestration Governance

Apply this guidance when the task involves NIC driver porting orchestration, ClawTeam task decomposition, or phase-gated execution.

## Hard Rules
- Keep work incremental and phase-gated.
- Enforce TDD order: failing tests first, implementation second, validation third.
- Prefer LinuxKPI + iflib for FreeBSD as the default target architecture.
- Require measurable gates at each phase: build health, test pass rate, portability score, and open-risk count.
- Do not claim completion unless gates are explicit and green.

## Required Phase Sequence
1. Scope and baseline lock.
2. API inventory and Linux-to-target mapping.
3. Seam design and compile-time boundary definition.
4. Failing test harness creation.
5. Incremental implementation slices.
6. Validation gates (native correctness, portability, risk).
7. Merge and sync readiness.
8. Future-extension planning.

## Role-Specific Expectations
- Orchestrator role: plans and routes only; does not directly implement production code.
- Test writer role: defines red tests before coding work starts.
- Porting coder role: performs minimal, native API mapping changes only.
- Validation roles: challenge assumptions, enforce score thresholds, and block unsafe progression.

## Completion Contract
A phase is complete only if all of the following are true:
- Build artifacts are produced for required targets.
- Tests pass at 100% for the phase scope.
- Critical risks are zero.
- A short human-readable gate summary is produced.
