---
name: mcp
description: "Skill for the Mcp area of clawteam. 14 symbols across 4 files."
---

# Mcp

14 symbols | 4 files | Cohesion: 79%

## When to Use

- Working with code in `clawteam/`
- Understanding how test_task_tools_round_trip, test_task_update_surfaces_missing_task, test_task_update_surfaces_lock_conflict work
- Modifying mcp-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `clawteam/mcp/helpers.py` | MCPToolError, fail, translate_error, coerce_enum, task_store |
| `clawteam/mcp/tools/task.py` | task_list, task_get, task_stats, task_create, task_update |
| `tests/test_mcp_tools.py` | test_task_tools_round_trip, test_task_update_surfaces_missing_task, test_task_update_surfaces_lock_conflict |
| `clawteam/mcp/server.py` | wrapped |

## Entry Points

Start here when exploring this area:

- **`test_task_tools_round_trip`** (Function) — `tests/test_mcp_tools.py:57`
- **`test_task_update_surfaces_missing_task`** (Function) — `tests/test_mcp_tools.py:80`
- **`test_task_update_surfaces_lock_conflict`** (Function) — `tests/test_mcp_tools.py:86`
- **`wrapped`** (Function) — `clawteam/mcp/server.py:17`
- **`fail`** (Function) — `clawteam/mcp/helpers.py:20`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `MCPToolError` | Class | `clawteam/mcp/helpers.py` | 16 |
| `test_task_tools_round_trip` | Function | `tests/test_mcp_tools.py` | 57 |
| `test_task_update_surfaces_missing_task` | Function | `tests/test_mcp_tools.py` | 80 |
| `test_task_update_surfaces_lock_conflict` | Function | `tests/test_mcp_tools.py` | 86 |
| `wrapped` | Function | `clawteam/mcp/server.py` | 17 |
| `fail` | Function | `clawteam/mcp/helpers.py` | 20 |
| `translate_error` | Function | `clawteam/mcp/helpers.py` | 24 |
| `coerce_enum` | Function | `clawteam/mcp/helpers.py` | 48 |
| `task_store` | Function | `clawteam/mcp/helpers.py` | 64 |
| `task_list` | Function | `clawteam/mcp/tools/task.py` | 8 |
| `task_get` | Function | `clawteam/mcp/tools/task.py` | 27 |
| `task_stats` | Function | `clawteam/mcp/tools/task.py` | 35 |
| `task_create` | Function | `clawteam/mcp/tools/task.py` | 40 |
| `task_update` | Function | `clawteam/mcp/tools/task.py` | 64 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tools | 6 calls |
| Tests | 4 calls |

## How to Explore

1. `gitnexus_context({name: "test_task_tools_round_trip"})` — see callers and callees
2. `gitnexus_query({query: "mcp"})` — find related execution flows
3. Read key files listed above for implementation details
