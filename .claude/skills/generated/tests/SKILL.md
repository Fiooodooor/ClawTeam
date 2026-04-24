---
name: tests
description: "Skill for the Tests area of clawteam. 649 symbols across 80 files."
---

# Tests

649 symbols | 80 files | Cohesion: 67%

## When to Use

- Working with code in `tests/`
- Understanding how test_format_timestamp_defaults_to_utc_without_suffix, test_format_timestamp_converts_to_configured_timezone, test_format_timestamp_falls_back_for_invalid_timezone work
- Modifying tests-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/test_spawn_backends.py` | test_tmux_backend_exports_spawn_path_for_agent_commands, test_tmux_backend_uses_configured_timeout_for_workspace_trust_prompt, test_tmux_backend_returns_error_when_command_missing, test_tmux_backend_normalizes_bare_nanobot_to_agent, test_tmux_backend_supports_docker_wrapped_nanobot (+45) |
| `clawteam/cli/commands.py` | _parse_key_value_items, config_set, preset_show, preset_set, preset_set_client (+41) |
| `tests/test_mailbox.py` | _make_mailbox, _inbox_path, _dead_letter_root, test_send_and_receive_single, test_receive_consumes_messages (+27) |
| `tests/test_manager.py` | test_create_basic, test_create_sets_up_directories, test_create_with_user_prefix, test_create_duplicate_raises, test_rejects_path_traversal_team_name (+23) |
| `tests/test_snapshots.py` | _setup_team, test_basic, test_with_tag, test_with_path_like_tag_uses_safe_snapshot_id, test_snapshot_file_written (+18) |
| `tests/test_waiter.py` | _make_task, _make_message, waiter, test_zero_tasks_completes_immediately, test_zero_tasks_returns_empty_details (+18) |
| `tests/test_registry.py` | test_skips_legacy_entries_without_spawned_at, test_returns_only_long_running_alive_agents, test_save_and_load_roundtrip, test_load_missing_file, test_load_corrupt_file (+18) |
| `tests/test_templates.py` | test_load_hedge_fund, test_leader_type, test_agents_have_tasks, test_task_owners_match_agents, test_load_strategy_room (+17) |
| `tests/test_spawn_cli.py` | test_spawn_cli_applies_profile_command_and_env, test_spawn_cli_uses_configured_default_profile_when_no_profile_or_command, test_spawn_cli_uses_single_profile_implicitly, test_spawn_cli_errors_when_multiple_profiles_exist_without_default, test_launch_cli_applies_profile_to_template_agents (+15) |
| `tests/test_cli_commands.py` | test_config_cli_supports_all_keys_and_bool_values, test_team_status_uses_configured_timezone, test_team_request_join_supports_no_wait_mode, test_team_request_join_timeout_returns_pending_instead_of_error, test_board_update_cli_is_a_compatibility_alias (+13) |

## Entry Points

Start here when exploring this area:

- **`test_format_timestamp_defaults_to_utc_without_suffix`** (Function) — `tests/test_timefmt.py:6`
- **`test_format_timestamp_converts_to_configured_timezone`** (Function) — `tests/test_timefmt.py:11`
- **`test_format_timestamp_falls_back_for_invalid_timezone`** (Function) — `tests/test_timefmt.py:17`
- **`test_task_store_in_config`** (Function) — `tests/test_store.py:122`
- **`test_spawn_cli_applies_profile_command_and_env`** (Function) — `tests/test_spawn_cli.py:121`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `AgentProfile` | Class | `clawteam/config.py` | 13 |
| `AgentPreset` | Class | `clawteam/config.py` | 29 |
| `HookDef` | Class | `clawteam/config.py` | 39 |
| `ClawTeamConfig` | Class | `clawteam/config.py` | 49 |
| `SnapshotMeta` | Class | `clawteam/team/snapshot.py` | 35 |
| `SnapshotManager` | Class | `clawteam/team/snapshot.py` | 108 |
| `WaitResult` | Class | `clawteam/team/waiter.py` | 15 |
| `TaskWaiter` | Class | `clawteam/team/waiter.py` | 29 |
| `HarnessContext` | Class | `clawteam/harness/context.py` | 12 |
| `WorkerExit` | Class | `clawteam/events/types.py` | 44 |
| `EventBus` | Class | `clawteam/events/bus.py` | 41 |
| `CostEvent` | Class | `clawteam/team/costs.py` | 20 |
| `CostSummary` | Class | `clawteam/team/costs.py` | 35 |
| `CostStore` | Class | `clawteam/team/costs.py` | 221 |
| `DummyMailbox` | Class | `tests/test_runtime_routing.py` | 183 |
| `DummyRouter` | Class | `tests/test_runtime_routing.py` | 205 |
| `FailingRouter` | Class | `tests/test_runtime_routing.py` | 227 |
| `InboxWatcher` | Class | `clawteam/team/watcher.py` | 13 |
| `RuntimeRouter` | Class | `clawteam/team/router.py` | 13 |
| `TmuxBackend` | Class | `clawteam/spawn/tmux_backend.py` | 33 |

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
| Cli | 71 calls |
| Spawn | 37 calls |
| Transport | 20 calls |
| Team | 19 calls |
| Harness | 12 calls |
| Events | 8 calls |
| Board | 2 calls |
| Templates | 2 calls |

## How to Explore

1. `gitnexus_context({name: "test_format_timestamp_defaults_to_utc_without_suffix"})` — see callers and callees
2. `gitnexus_query({query: "tests"})` — find related execution flows
3. Read key files listed above for implementation details
