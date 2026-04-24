---
name: store
description: "Skill for the Store area of clawteam. 18 symbols across 2 files."
---

# Store

18 symbols | 2 files | Cohesion: 78%

## When to Use

- Working with code in `clawteam/`
- Understanding how create, get, update work
- Modifying store-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `clawteam/store/file.py` | _tasks_root, _task_path, _tasks_lock_path, _now_iso, _write_lock (+12) |
| `clawteam/store/base.py` | TaskLockError |

## Entry Points

Start here when exploring this area:

- **`create`** (Function) — `clawteam/store/file.py:76`
- **`get`** (Function) — `clawteam/store/file.py:110`
- **`update`** (Function) — `clawteam/store/file.py:123`
- **`release_stale_locks`** (Function) — `clawteam/store/file.py:227`
- **`list_tasks`** (Function) — `clawteam/store/file.py:244`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `TaskLockError` | Class | `clawteam/store/base.py` | 11 |
| `create` | Function | `clawteam/store/file.py` | 76 |
| `get` | Function | `clawteam/store/file.py` | 110 |
| `update` | Function | `clawteam/store/file.py` | 123 |
| `release_stale_locks` | Function | `clawteam/store/file.py` | 227 |
| `list_tasks` | Function | `clawteam/store/file.py` | 244 |
| `_tasks_root` | Function | `clawteam/store/file.py` | 23 |
| `_task_path` | Function | `clawteam/store/file.py` | 32 |
| `_tasks_lock_path` | Function | `clawteam/store/file.py` | 36 |
| `_now_iso` | Function | `clawteam/store/file.py` | 40 |
| `_write_lock` | Function | `clawteam/store/file.py` | 54 |
| `_get_unlocked` | Function | `clawteam/store/file.py` | 113 |
| `_acquire_lock` | Function | `clawteam/store/file.py` | 215 |
| `_list_tasks_unlocked` | Function | `clawteam/store/file.py` | 258 |
| `_validate_blocked_by_unlocked` | Function | `clawteam/store/file.py` | 290 |
| `_visit` | Function | `clawteam/store/file.py` | 303 |
| `_save_unlocked` | Function | `clawteam/store/file.py` | 320 |
| `_resolve_dependents_unlocked` | Function | `clawteam/store/file.py` | 336 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Update → Ensure_within_root` | cross_community | 6 |
| `Release_stale_locks → Config_path` | cross_community | 6 |
| `Update → Validate_identifier` | cross_community | 5 |
| `Update → _load` | cross_community | 5 |
| `Release_stale_locks → Ensure_within_root` | cross_community | 5 |
| `Release_stale_locks → Validate_identifier` | cross_community | 5 |
| `Update → FakeResponse` | cross_community | 4 |
| `Update → _tmux_pane_alive` | cross_community | 4 |
| `Update → _pid_alive` | cross_community | 4 |
| `Update → _wsh_block_alive` | cross_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 8 calls |
| Events | 3 calls |
| Spawn | 2 calls |
| Transport | 1 calls |
| Board | 1 calls |

## How to Explore

1. `gitnexus_context({name: "create"})` — see callers and callees
2. `gitnexus_query({query: "store"})` — find related execution flows
3. Read key files listed above for implementation details
