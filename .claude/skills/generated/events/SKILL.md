---
name: events
description: "Skill for the Events area of clawteam. 29 symbols across 6 files."
---

# Events

29 symbols | 6 files | Cohesion: 72%

## When to Use

- Working with code in `clawteam/`
- Understanding how test_event_type_registry, test_shell_hook, test_disabled_hook_not_loaded work
- Modifying events-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `clawteam/events/types.py` | HarnessEvent, AfterWorkerSpawn, WorkerCrash, BeforeTaskCreate, AfterTaskUpdate (+8) |
| `clawteam/events/hooks.py` | HookDef, HookManager, load_hooks, register_hook, unregister_all (+3) |
| `tests/test_event_bus.py` | test_shell_hook, test_disabled_hook_not_loaded, test_unknown_event_type, test_unregister_all |
| `tests/test_harness.py` | test_event_type_registry, CustomEvent |
| `clawteam/events/global_bus.py` | _load_hooks_from_config |
| `clawteam/events/bus.py` | resolve_event_type |

## Entry Points

Start here when exploring this area:

- **`test_event_type_registry`** (Function) — `tests/test_harness.py:347`
- **`test_shell_hook`** (Function) — `tests/test_event_bus.py:103`
- **`test_disabled_hook_not_loaded`** (Function) — `tests/test_event_bus.py:119`
- **`test_unknown_event_type`** (Function) — `tests/test_event_bus.py:129`
- **`test_unregister_all`** (Function) — `tests/test_event_bus.py:136`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `HookDef` | Class | `clawteam/events/hooks.py` | 17 |
| `HookManager` | Class | `clawteam/events/hooks.py` | 27 |
| `CustomEvent` | Class | `tests/test_harness.py` | 354 |
| `HarnessEvent` | Class | `clawteam/events/types.py` | 13 |
| `AfterWorkerSpawn` | Class | `clawteam/events/types.py` | 34 |
| `WorkerCrash` | Class | `clawteam/events/types.py` | 53 |
| `BeforeTaskCreate` | Class | `clawteam/events/types.py` | 64 |
| `AfterTaskUpdate` | Class | `clawteam/events/types.py` | 72 |
| `TaskCompleted` | Class | `clawteam/events/types.py` | 82 |
| `BeforeInboxSend` | Class | `clawteam/events/types.py` | 94 |
| `AfterInboxReceive` | Class | `clawteam/events/types.py` | 103 |
| `TeamLaunch` | Class | `clawteam/events/types.py` | 132 |
| `AgentIdle` | Class | `clawteam/events/types.py` | 150 |
| `HeartbeatTimeout` | Class | `clawteam/events/types.py` | 158 |
| `TransportFallback` | Class | `clawteam/events/types.py` | 181 |
| `BoardAttach` | Class | `clawteam/events/types.py` | 190 |
| `test_event_type_registry` | Function | `tests/test_harness.py` | 347 |
| `test_shell_hook` | Function | `tests/test_event_bus.py` | 103 |
| `test_disabled_hook_not_loaded` | Function | `tests/test_event_bus.py` | 119 |
| `test_unknown_event_type` | Function | `tests/test_event_bus.py` | 129 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Lifecycle_request_shutdown → _make_shell_handler` | cross_community | 8 |
| `Lifecycle_request_shutdown → _resolve_python_callable` | cross_community | 8 |
| `Spawn_for_phase → Resolve_event_type` | cross_community | 7 |
| `Plan_approve → Config_path` | cross_community | 7 |
| `Plan_approve → ClawTeamConfig` | cross_community | 7 |
| `Plan_reject → Config_path` | cross_community | 7 |
| `Plan_reject → ClawTeamConfig` | cross_community | 7 |
| `Lifecycle_approve_shutdown → Config_path` | cross_community | 7 |
| `Lifecycle_approve_shutdown → ClawTeamConfig` | cross_community | 7 |
| `Lifecycle_reject_shutdown → Config_path` | cross_community | 7 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 8 calls |

## How to Explore

1. `gitnexus_context({name: "test_event_type_registry"})` — see callers and callees
2. `gitnexus_query({query: "events"})` — find related execution flows
3. Read key files listed above for implementation details
