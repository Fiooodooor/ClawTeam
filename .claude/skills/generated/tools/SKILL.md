---
name: tools
description: "Skill for the Tools area of clawteam. 29 symbols across 8 files."
---

# Tools

29 symbols | 8 files | Cohesion: 61%

## When to Use

- Working with code in `clawteam/`
- Understanding how test_to_payload_serializes_pydantic_aliases, test_team_tools_round_trip, test_cost_summary_defaults_to_empty work
- Modifying tools-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/test_mcp_tools.py` | test_to_payload_serializes_pydantic_aliases, test_team_tools_round_trip, test_cost_summary_defaults_to_empty, test_workspace_cross_branch_log_returns_empty_text_payload_without_entries, test_plan_tools (+1) |
| `clawteam/mcp/helpers.py` | to_payload, require_team, cost_store, plan_manager, team_mailbox |
| `clawteam/mcp/tools/team.py` | team_list, team_get, team_members_list, team_create, team_member_add |
| `clawteam/mcp/tools/mailbox.py` | mailbox_send, mailbox_broadcast, mailbox_receive, mailbox_peek, mailbox_peek_count |
| `clawteam/mcp/tools/plan.py` | plan_submit, plan_get, plan_approve, plan_reject |
| `clawteam/team/plan.py` | approve_plan, reject_plan |
| `clawteam/mcp/tools/workspace.py` | workspace_cross_branch_log |
| `clawteam/mcp/tools/cost.py` | cost_summary |

## Entry Points

Start here when exploring this area:

- **`test_to_payload_serializes_pydantic_aliases`** (Function) — `tests/test_mcp_tools.py:28`
- **`test_team_tools_round_trip`** (Function) — `tests/test_mcp_tools.py:35`
- **`test_cost_summary_defaults_to_empty`** (Function) — `tests/test_mcp_tools.py:137`
- **`test_workspace_cross_branch_log_returns_empty_text_payload_without_entries`** (Function) — `tests/test_mcp_tools.py:156`
- **`to_payload`** (Function) — `clawteam/mcp/helpers.py:34`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `test_to_payload_serializes_pydantic_aliases` | Function | `tests/test_mcp_tools.py` | 28 |
| `test_team_tools_round_trip` | Function | `tests/test_mcp_tools.py` | 35 |
| `test_cost_summary_defaults_to_empty` | Function | `tests/test_mcp_tools.py` | 137 |
| `test_workspace_cross_branch_log_returns_empty_text_payload_without_entries` | Function | `tests/test_mcp_tools.py` | 156 |
| `to_payload` | Function | `clawteam/mcp/helpers.py` | 34 |
| `require_team` | Function | `clawteam/mcp/helpers.py` | 52 |
| `cost_store` | Function | `clawteam/mcp/helpers.py` | 74 |
| `workspace_cross_branch_log` | Function | `clawteam/mcp/tools/workspace.py` | 20 |
| `team_list` | Function | `clawteam/mcp/tools/team.py` | 8 |
| `team_get` | Function | `clawteam/mcp/tools/team.py` | 13 |
| `team_members_list` | Function | `clawteam/mcp/tools/team.py` | 18 |
| `team_create` | Function | `clawteam/mcp/tools/team.py` | 24 |
| `team_member_add` | Function | `clawteam/mcp/tools/team.py` | 45 |
| `cost_summary` | Function | `clawteam/mcp/tools/cost.py` | 7 |
| `test_plan_tools` | Function | `tests/test_mcp_tools.py` | 119 |
| `approve_plan` | Function | `clawteam/team/plan.py` | 132 |
| `reject_plan` | Function | `clawteam/team/plan.py` | 147 |
| `plan_manager` | Function | `clawteam/mcp/helpers.py` | 69 |
| `plan_submit` | Function | `clawteam/mcp/tools/plan.py` | 7 |
| `plan_get` | Function | `clawteam/mcp/tools/plan.py` | 24 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Plan_approve → Config_path` | cross_community | 7 |
| `Plan_approve → ClawTeamConfig` | cross_community | 7 |
| `Plan_reject → Config_path` | cross_community | 7 |
| `Plan_reject → ClawTeamConfig` | cross_community | 7 |
| `Plan_approve → Validate_identifier` | cross_community | 6 |
| `Plan_approve → HookManager` | cross_community | 6 |
| `Plan_reject → Validate_identifier` | cross_community | 6 |
| `Plan_reject → HookManager` | cross_community | 6 |
| `Plan_approve → EventBus` | cross_community | 5 |
| `Plan_reject → EventBus` | cross_community | 5 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 19 calls |
| Cli | 2 calls |
| Mcp | 2 calls |
| Transport | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_to_payload_serializes_pydantic_aliases"})` — see callers and callees
2. `gitnexus_query({query: "tools"})` — find related execution flows
3. Read key files listed above for implementation details
