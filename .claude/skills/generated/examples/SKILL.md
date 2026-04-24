---
name: examples
description: "Skill for the Examples area of clawteam. 84 symbols across 5 files."
---

# Examples

84 symbols | 5 files | Cohesion: 70%

## When to Use

- Working with code in `examples/`
- Understanding how persist_checkpoint, load_checkpoint_if_exists, build_chapters work
- Modifying examples-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `examples/nic_porting_orchestrator_v2.py` | compute_gate_scores, _get_task_store, _task_status_map, _task_status_value, _phase_task_payloads (+44) |
| `examples/nic_porting_swarm_runtime.py` | _utc_now, persist_checkpoint, load_checkpoint_if_exists, build_chapters, _derive_resume_task_map (+20) |
| `examples/nic_porting_swarm.py` | run, ensure_dependencies, node_bootstrap, build_graph, parse_args (+3) |
| `clawteam/workspace/manager.py` | list_workspaces |
| `clawteam/cli/commands.py` | workspace_list |

## Entry Points

Start here when exploring this area:

- **`persist_checkpoint`** (Function) — `examples/nic_porting_swarm_runtime.py:201`
- **`load_checkpoint_if_exists`** (Function) — `examples/nic_porting_swarm_runtime.py:219`
- **`build_chapters`** (Function) — `examples/nic_porting_swarm_runtime.py:307`
- **`node_preflight`** (Function) — `examples/nic_porting_swarm_runtime.py:421`
- **`node_bootstrap_team`** (Function) — `examples/nic_porting_swarm_runtime.py:491`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `persist_checkpoint` | Function | `examples/nic_porting_swarm_runtime.py` | 201 |
| `load_checkpoint_if_exists` | Function | `examples/nic_porting_swarm_runtime.py` | 219 |
| `build_chapters` | Function | `examples/nic_porting_swarm_runtime.py` | 307 |
| `node_preflight` | Function | `examples/nic_porting_swarm_runtime.py` | 421 |
| `node_bootstrap_team` | Function | `examples/nic_porting_swarm_runtime.py` | 491 |
| `node_generate_chapters` | Function | `examples/nic_porting_swarm_runtime.py` | 509 |
| `node_reconcile_tasks` | Function | `examples/nic_porting_swarm_runtime.py` | 524 |
| `node_monitor_iterations` | Function | `examples/nic_porting_swarm_runtime.py` | 622 |
| `node_write_artifacts` | Function | `examples/nic_porting_swarm_runtime.py` | 772 |
| `compute_gate_scores` | Function | `examples/nic_porting_orchestrator_v2.py` | 441 |
| `node_monitor` | Function | `examples/nic_porting_orchestrator_v2.py` | 1229 |
| `maybe_prompt_refiner` | Function | `examples/nic_porting_swarm_runtime.py` | 239 |
| `build_worker_task` | Function | `examples/nic_porting_swarm_runtime.py` | 274 |
| `node_spawn_workers` | Function | `examples/nic_porting_swarm_runtime.py` | 570 |
| `build_worker_prompt` | Function | `examples/nic_porting_orchestrator_v2.py` | 530 |
| `run` | Function | `examples/nic_porting_swarm_runtime.py` | 181 |
| `node_package_patches` | Function | `examples/nic_porting_swarm_runtime.py` | 682 |
| `run_cmd` | Function | `examples/nic_porting_orchestrator_v2.py` | 258 |
| `node_package_patches` | Function | `examples/nic_porting_orchestrator_v2.py` | 1295 |
| `list_workspaces` | Function | `clawteam/workspace/manager.py` | 287 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Node_package_patches → Config_path` | cross_community | 8 |
| `Node_package_patches → ClawTeamConfig` | cross_community | 8 |
| `Node_package_patches → Config_path` | cross_community | 8 |
| `Node_package_patches → ClawTeamConfig` | cross_community | 8 |
| `Node_spawn_workers → Config_path` | cross_community | 7 |
| `Node_spawn_workers → ClawTeamConfig` | cross_community | 7 |
| `Node_spawn_workers → Ensure_within_root` | cross_community | 5 |
| `Node_spawn_workers → Validate_identifier` | cross_community | 5 |
| `Node_package_patches → Ensure_within_root` | cross_community | 5 |
| `Node_package_patches → Validate_identifier` | cross_community | 5 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 11 calls |
| Workspace | 4 calls |
| Transport | 4 calls |
| Cli | 3 calls |
| Spawn | 3 calls |

## How to Explore

1. `gitnexus_context({name: "persist_checkpoint"})` — see callers and callees
2. `gitnexus_query({query: "examples"})` — find related execution flows
3. Read key files listed above for implementation details
