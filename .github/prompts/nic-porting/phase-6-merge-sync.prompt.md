---
name: nic-phase-6-merge-sync
description: "Phase 6: Merge readiness verification and upstream sync planning."
argument-hint: "Driver name, target branch, patch set path"
agent: nic-porting-director
---
Execute Phase 6 — Merge & Upstream Sync for this driver:

${input:Driver name, target FreeBSD branch (e.g. main), and patch set directory}

Phase 6 deliverables:
1. Rebase onto latest FreeBSD HEAD with portable core integrity preserved
2. One commit per Phase 4 slice in format: `mynic: port <subsystem> to native FreeBSD APIs`
3. Bisect-safety verification — every commit compiles and passes tests independently
4. Full CI pipeline post-merge (build-linux, build-freebsd, test-unit, test-integration, gate-check)
5. CHANGES.md with per-slice entries and gate results
6. Upstream sync strategy — periodic rebase protocol with conflict resolution procedures
7. Final patch set (`git format-patch`) for FreeBSD src committer review

Gate criteria:
- portability_score ≥ 95
- All commits bisect-safe
- Full CI pipeline green post-merge
- No portable core modifications during rebase

Delegate merge work to #tool:agent nic-merge-engineer.
Use `mailbox_broadcast` with key `phase-6-ci-results` to share post-merge CI results.
Use `workspace_agent_diff` to verify per-agent contribution stats.
