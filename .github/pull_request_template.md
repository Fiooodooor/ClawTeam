# Summary

- Problem:
- Why it matters:
- What changed:
- What did NOT change (scope boundary):

## Change Type

- [ ] Bug fix
- [ ] Feature
- [ ] Refactor
- [ ] NIC porting slice (specify phase + role below)
- [ ] Docs
- [ ] Security hardening
- [ ] Chore/infra

## Scope

- [ ] ClawTeam CLI / orchestration
- [ ] Spawn / backends
- [ ] Skills / tool execution
- [ ] MCP server / transport
- [ ] Task board / inbox
- [ ] NIC porting agents / identities
- [ ] Templates / profiles
- [ ] Tests
- [ ] CI/CD / infra
- [ ] Docs

## NIC Porting Context (if applicable)

| Field         | Value |
| ------------- | ----- |
| Driver        |       |
| Target OS     |       |
| Phase         |       |
| Role          |       |
| Board Task ID |       |

## Gate Checklist (NIC porting PRs)

- [ ] native_score >= 98.0 (no framework/non-native API calls)
- [ ] portability_score >= 95.0 (cross-compile matrix clean)
- [ ] test_pass_rate = 100% (all TDD tests green)
- [ ] build_status = green (Linux + FreeBSD compile)
- [ ] critical_risks = 0 (no open critical risks in register)
- [ ] Zero-copy verified (no memcpy in hot paths)
- [ ] DMA sync discipline followed (PREWRITE/POSTREAD bracketing)
- [ ] Checker agent PASS verdict attached

## Linked Issue/PR

- Closes #
- Related #
- [ ] This PR fixes a bug or regression

## Root Cause / Regression History (if applicable)

- Root cause:
- Missing detection / guardrail:
- Prior context:
- Why this regressed now:

## Risk Register Impact

- [ ] No new risks introduced
- [ ] New risk(s) added to register with mitigation owner
- [ ] Existing risk(s) mitigated or closed (specify IDs):

## Regression Test Plan

For bug fixes, name the test(s) that would have caught this. For porting slices,
list the TDD tests that validate the change. Otherwise write `N/A`.

- Coverage level that should have caught this:
  - [ ] Unit test
  - [ ] Seam / integration test
  - [ ] End-to-end test
  - [ ] Existing coverage already sufficient
- Target test or file:
- Scenario the test should lock in:
- Why this is the smallest reliable guardrail:
- Existing test that already covers this (if any):
- If no new test is added, why not:

## User-visible / Behavior Changes

List user-visible changes (including defaults/config).  
If none, write `None`.

## Diagram (if applicable)

For UI changes or non-trivial logic flows, include a small ASCII diagram reviewers can scan quickly. Otherwise write `N/A`.

```text
Before:
[user action] -> [old state]

After:
[user action] -> [new state] -> [result]
```

## Security Impact (required)

- New permissions/capabilities? (`Yes/No`)
- Secrets/tokens handling changed? (`Yes/No`)
- New/changed network calls? (`Yes/No`)
- Command/tool execution surface changed? (`Yes/No`)
- Data access scope changed? (`Yes/No`)
- If any `Yes`, explain risk + mitigation:

## Repro + Verification

### Environment

- OS:
- Runtime/container:
- Model/provider:
- Integration/channel (if any):
- Relevant config (redacted):

### Steps

1.
2.
3.

### Expected

-

### Actual

-

## Evidence

Attach at least one:

- [ ] Failing test/log before + passing after
- [ ] Trace/log snippets
- [ ] Screenshot/recording
- [ ] Perf numbers (if relevant)

## Human Verification (required)

What you personally verified (not just CI), and how:

- Verified scenarios:
- Edge cases checked:
- What you did **not** verify:

## Review Conversations

- [ ] I replied to or resolved every bot review conversation I addressed in this PR.
- [ ] I left unresolved only the conversations that still need reviewer or maintainer judgment.

If a bot review conversation is addressed by this PR, resolve that conversation yourself. Do not leave bot review conversation cleanup for maintainers.

## Compatibility / Migration

- Backward compatible? (`Yes/No`)
- Config/env changes? (`Yes/No`)
- Migration needed? (`Yes/No`)
- If yes, exact upgrade steps:

## Risks and Mitigations

List only real risks for this PR. Add/remove entries as needed. If none, write `None`.

- Risk:
  - Mitigation:
