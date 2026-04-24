---
name: harness
description: "Skill for the Harness area of clawteam. 109 symbols across 20 files."
---

# Harness

109 symbols | 20 files | Cohesion: 68%

## When to Use

- Working with code in `clawteam/`
- Understanding how test_default_values, test_with_criteria, test_round_robin_assignment work
- Modifying harness-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/test_harness.py` | test_default_values, test_with_criteria, test_round_robin_assignment, test_create_tasks_from_contracts_assigns_owner_round_robin, Orch (+16) |
| `clawteam/harness/phases.py` | save, load, register_gate, can_advance, _now_iso (+6) |
| `clawteam/harness/artifacts.py` | write_sprint_contract, ArtifactStore, read, exists, list_artifacts (+5) |
| `clawteam/harness/orchestrator.py` | _harness_dir, advance, register_artifact, abort, load (+5) |
| `clawteam/harness/conductor.py` | _prepare_execute, RegistryHealthCheck, __init__, NoRespawn, should_respawn (+4) |
| `clawteam/cli/commands.py` | harness_status, harness_advance, harness_abort, harness_approve, run_command (+3) |
| `clawteam/harness/contract_executor.py` | RoundRobinAssigner, assign, ContractExecutor, __init__, load_contracts (+2) |
| `clawteam/harness/spawner.py` | respawn, _build_resume_command, spawn_for_phase, _agent_count_for_role, _build_task_prompt (+1) |
| `clawteam/harness/strategies.py` | AssignmentStrategy, ExitNotifier, SpawnStrategy, HealthStrategy, RespawnStrategy |
| `clawteam/harness/context_recovery.py` | ContextRecovery, build_recovery_prompt, _task_progress, _git_summary, _artifact_context |

## Entry Points

Start here when exploring this area:

- **`test_default_values`** (Function) — `tests/test_harness.py:146`
- **`test_with_criteria`** (Function) — `tests/test_harness.py:151`
- **`test_round_robin_assignment`** (Function) — `tests/test_harness.py:216`
- **`test_create_tasks_from_contracts_assigns_owner_round_robin`** (Function) — `tests/test_harness.py:229`
- **`test_create_tasks_from_contracts_prefers_contract_assignee`** (Function) — `tests/test_harness.py:264`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `Orch` | Class | `tests/test_harness.py` | 235 |
| `AssignmentStrategy` | Class | `clawteam/harness/strategies.py` | 69 |
| `SuccessCriterion` | Class | `clawteam/harness/contracts.py` | 14 |
| `SprintContract` | Class | `clawteam/harness/contracts.py` | 24 |
| `RoundRobinAssigner` | Class | `clawteam/harness/contract_executor.py` | 11 |
| `ContractExecutor` | Class | `clawteam/harness/contract_executor.py` | 28 |
| `ContextRecovery` | Class | `clawteam/harness/context_recovery.py` | 10 |
| `ArtifactStore` | Class | `clawteam/harness/artifacts.py` | 14 |
| `ExitNotifier` | Class | `clawteam/harness/strategies.py` | 52 |
| `FileExitJournal` | Class | `clawteam/harness/exit_journal.py` | 12 |
| `BeforeWorkerSpawn` | Class | `clawteam/events/types.py` | 24 |
| `PhaseTransition` | Class | `clawteam/events/types.py` | 169 |
| `SpawnStrategy` | Class | `clawteam/harness/strategies.py` | 8 |
| `HealthStrategy` | Class | `clawteam/harness/strategies.py` | 44 |
| `PhaseRoleSpawner` | Class | `clawteam/harness/spawner.py` | 12 |
| `RegistryHealthCheck` | Class | `clawteam/harness/conductor.py` | 20 |
| `PhaseGate` | Class | `clawteam/harness/phases.py` | 55 |
| `ArtifactRequiredGate` | Class | `clawteam/harness/phases.py` | 63 |
| `AllTasksCompleteGate` | Class | `clawteam/harness/phases.py` | 76 |
| `HumanApprovalGate` | Class | `clawteam/harness/phases.py` | 90 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Spawn_for_phase → Resolve_event_type` | cross_community | 7 |
| `Run_command → Ensure_within_root` | cross_community | 6 |
| `Run_command → Validate_identifier` | cross_community | 6 |
| `Spawn_for_phase → _make_shell_handler` | cross_community | 6 |
| `Spawn_for_phase → _resolve_python_callable` | cross_community | 6 |
| `Harness_conduct → Config_path` | cross_community | 6 |
| `Harness_conduct → ClawTeamConfig` | cross_community | 6 |
| `Spawn_for_phase → Config_path` | cross_community | 5 |
| `Spawn_for_phase → ClawTeamConfig` | cross_community | 5 |
| `Run_command → WorkspaceManager` | cross_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 36 calls |
| Cli | 4 calls |
| Spawn | 3 calls |
| Plugins | 2 calls |
| Workspace | 2 calls |
| Team | 1 calls |
| Board | 1 calls |
| Transport | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_default_values"})` — see callers and callees
2. `gitnexus_query({query: "harness"})` — find related execution flows
3. Read key files listed above for implementation details
