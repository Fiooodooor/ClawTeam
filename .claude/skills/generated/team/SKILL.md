---
name: team
description: "Skill for the Team area of clawteam. 68 symbols across 9 files."
---

# Team

68 symbols | 9 files | Cohesion: 80%

## When to Use

- Working with code in `clawteam/`
- Understanding how test_default_routing_policy_throttles_same_source_target_and_tracks_pending_state, test_runtime_router_dispatches_and_flushes_aggregated_messages, test_runtime_router_resolves_registered_backend_for_runtime_injection work
- Modifying team-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `clawteam/team/routing_policy.py` | _utcnow, _ensure_datetime, _isoformat, _parse_iso, _runtime_state_path (+18) |
| `clawteam/team/costs.py` | _CostCacheEntry, _CostSummaryCache, _costs_root, _summary_cache_path, _read_event_file (+9) |
| `clawteam/team/plan.py` | _plans_root, _plans_root_path, _team_plans_root, _plan_filename, _team_plan_path (+4) |
| `tests/test_runtime_routing.py` | _utc, test_default_routing_policy_throttles_same_source_target_and_tracks_pending_state, test_runtime_router_dispatches_and_flushes_aggregated_messages, StubBackend, test_runtime_router_resolves_registered_backend_for_runtime_injection (+3) |
| `clawteam/team/router.py` | __init__, route_message, flush_due, dispatch, normalize_message (+2) |
| `clawteam/team/manager.py` | _load_config, team_exists, get_member, get_leader_name |
| `tests/test_cli_commands.py` | test_runtime_state_cli_reports_pending_routes |
| `clawteam/cli/commands.py` | runtime_state |
| `tests/test_manager.py` | test_get_leader_name |

## Entry Points

Start here when exploring this area:

- **`test_default_routing_policy_throttles_same_source_target_and_tracks_pending_state`** (Function) — `tests/test_runtime_routing.py:39`
- **`test_runtime_router_dispatches_and_flushes_aggregated_messages`** (Function) — `tests/test_runtime_routing.py:63`
- **`test_runtime_router_resolves_registered_backend_for_runtime_injection`** (Function) — `tests/test_runtime_routing.py:108`
- **`test_default_routing_policy_failed_initial_injection_uses_retry_backoff`** (Function) — `tests/test_runtime_routing.py:132`
- **`test_default_routing_policy_failed_flush_uses_retry_backoff`** (Function) — `tests/test_runtime_routing.py:154`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `StubBackend` | Class | `tests/test_runtime_routing.py` | 66 |
| `RouteDecision` | Class | `clawteam/team/routing_policy.py` | 74 |
| `RoutingPolicy` | Class | `clawteam/team/routing_policy.py` | 84 |
| `DefaultRoutingPolicy` | Class | `clawteam/team/routing_policy.py` | 92 |
| `test_default_routing_policy_throttles_same_source_target_and_tracks_pending_state` | Function | `tests/test_runtime_routing.py` | 39 |
| `test_runtime_router_dispatches_and_flushes_aggregated_messages` | Function | `tests/test_runtime_routing.py` | 63 |
| `test_runtime_router_resolves_registered_backend_for_runtime_injection` | Function | `tests/test_runtime_routing.py` | 108 |
| `test_default_routing_policy_failed_initial_injection_uses_retry_backoff` | Function | `tests/test_runtime_routing.py` | 132 |
| `test_default_routing_policy_failed_flush_uses_retry_backoff` | Function | `tests/test_runtime_routing.py` | 154 |
| `test_runtime_state_cli_reports_pending_routes` | Function | `tests/test_cli_commands.py` | 408 |
| `to_dict` | Function | `clawteam/team/routing_policy.py` | 65 |
| `decide` | Function | `clawteam/team/routing_policy.py` | 99 |
| `flush_due` | Function | `clawteam/team/routing_policy.py` | 157 |
| `record_dispatch_result` | Function | `clawteam/team/routing_policy.py` | 204 |
| `read_state` | Function | `clawteam/team/routing_policy.py` | 257 |
| `route_message` | Function | `clawteam/team/router.py` | 69 |
| `flush_due` | Function | `clawteam/team/router.py` | 80 |
| `dispatch` | Function | `clawteam/team/router.py` | 86 |
| `runtime_state` | Function | `clawteam/cli/commands.py` | 2015 |
| `team_plans_path` | Function | `clawteam/team/plan.py` | 59 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Inbox_peek → Config_path` | cross_community | 10 |
| `Inbox_peek → ClawTeamConfig` | cross_community | 10 |
| `Inbox_broadcast → Load_config` | cross_community | 10 |
| `Inbox_watch → Config_path` | cross_community | 10 |
| `Inbox_watch → ClawTeamConfig` | cross_community | 10 |
| `Board_show → Config_path` | cross_community | 10 |
| `Board_show → ClawTeamConfig` | cross_community | 10 |
| `Board_overview → Config_path` | cross_community | 10 |
| `Board_overview → ClawTeamConfig` | cross_community | 10 |
| `Board_overview → Load_config` | cross_community | 10 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 30 calls |
| Harness | 1 calls |
| Cli | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_default_routing_policy_throttles_same_source_target_and_tracks_pending_state"})` — see callers and callees
2. `gitnexus_query({query: "team"})` — find related execution flows
3. Read key files listed above for implementation details
