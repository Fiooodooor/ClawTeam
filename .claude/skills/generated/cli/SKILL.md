---
name: cli
description: "Skill for the Cli area of clawteam. 75 symbols across 23 files."
---

# Cli

75 symbols | 23 files | Cohesion: 44%

## When to Use

- Working with code in `clawteam/`
- Understanding how test_board_tools, test_lifecycle_idle_routes_to_prefixed_leader_inbox, test_collect_team_preserves_conflicts_field work
- Modifying cli-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `clawteam/cli/commands.py` | _output, preset_remove, preset_remove_client, profile_show, profile_remove (+33) |
| `tests/test_board.py` | test_collect_team_preserves_conflicts_field, test_collect_team_exposes_member_inbox_identity, test_collect_team_normalizes_message_participants |
| `clawteam/workspace/context.py` | file_owners, cross_branch_log, inject_context |
| `clawteam/board/renderer.py` | BoardRenderer, render_overview, render_team_board_live |
| `tests/test_identity.py` | test_from_env_with_oh_vars, test_from_env_with_claude_code_fallback, test_from_env_defaults |
| `clawteam/team/models.py` | MessageType, TaskStatus, TaskPriority |
| `clawteam/workspace/conflicts.py` | detect_overlaps, auto_notify |
| `clawteam/board/gource.py` | _agent_color, generate_user_colors |
| `clawteam/board/collector.py` | BoardCollector, collect_team |
| `clawteam/mcp/tools/board.py` | board_overview, board_team |

## Entry Points

Start here when exploring this area:

- **`test_board_tools`** (Function) — `tests/test_mcp_tools.py:146`
- **`test_lifecycle_idle_routes_to_prefixed_leader_inbox`** (Function) — `tests/test_inbox_routing.py:13`
- **`test_collect_team_preserves_conflicts_field`** (Function) — `tests/test_board.py:113`
- **`test_collect_team_exposes_member_inbox_identity`** (Function) — `tests/test_board.py:127`
- **`test_collect_team_normalizes_message_participants`** (Function) — `tests/test_board.py:144`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `LifecycleManager` | Class | `clawteam/team/lifecycle.py` | 11 |
| `BoardRenderer` | Class | `clawteam/board/renderer.py` | 17 |
| `BoardCollector` | Class | `clawteam/board/collector.py` | 11 |
| `MessageType` | Class | `clawteam/team/models.py` | 49 |
| `TaskStatus` | Class | `clawteam/team/models.py` | 35 |
| `TaskPriority` | Class | `clawteam/team/models.py` | 42 |
| `test_board_tools` | Function | `tests/test_mcp_tools.py` | 146 |
| `test_lifecycle_idle_routes_to_prefixed_leader_inbox` | Function | `tests/test_inbox_routing.py` | 13 |
| `test_collect_team_preserves_conflicts_field` | Function | `tests/test_board.py` | 113 |
| `test_collect_team_exposes_member_inbox_identity` | Function | `tests/test_board.py` | 127 |
| `test_collect_team_normalizes_message_participants` | Function | `tests/test_board.py` | 144 |
| `file_owners` | Function | `clawteam/workspace/context.py` | 123 |
| `cross_branch_log` | Function | `clawteam/workspace/context.py` | 154 |
| `inject_context` | Function | `clawteam/workspace/context.py` | 227 |
| `detect_overlaps` | Function | `clawteam/workspace/conflicts.py` | 14 |
| `auto_notify` | Function | `clawteam/workspace/conflicts.py` | 188 |
| `load_profile` | Function | `clawteam/spawn/profiles.py` | 10 |
| `validate_spawn_command` | Function | `clawteam/spawn/command_validation.py` | 253 |
| `preset_remove` | Function | `clawteam/cli/commands.py` | 454 |
| `preset_remove_client` | Function | `clawteam/cli/commands.py` | 473 |

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
| Tests | 65 calls |
| Workspace | 11 calls |
| Spawn | 5 calls |
| Tools | 3 calls |
| Team | 2 calls |
| Transport | 2 calls |
| Board | 2 calls |
| Harness | 2 calls |

## How to Explore

1. `gitnexus_context({name: "test_board_tools"})` — see callers and callees
2. `gitnexus_query({query: "cli"})` — find related execution flows
3. Read key files listed above for implementation details
