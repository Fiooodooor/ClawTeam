---
name: board
description: "Skill for the Board area of clawteam. 34 symbols across 8 files."
---

# Board

34 symbols | 8 files | Cohesion: 78%

## When to Use

- Working with code in `clawteam/`
- Understanding how poll, test_collect_live_log_lines_returns_only_unseen, test_append_log_lines_writes_and_flushes work
- Modifying board-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `clawteam/board/gource.py` | _virtual_path, _parse_iso, generate_event_log, generate_git_log, generate_combined_log (+5) |
| `tests/test_gource.py` | test_collect_live_log_lines_returns_only_unseen, test_append_log_lines_writes_and_flushes, DummyStream, write, flush (+3) |
| `clawteam/board/server.py` | do_GET, do_POST, _serve_static, _serve_json, _serve_team (+1) |
| `clawteam/board/renderer.py` | render_team_board, _build_team_board, _build_conflict_panel, _build_task_kanban |
| `tests/test_board.py` | test_serve_team_reads_fresh_snapshot_without_cache, FakeCache, test_serve_sse_uses_shared_team_snapshot_cache |
| `tests/test_spawn_backends.py` | poll |
| `clawteam/spawn/subprocess_backend.py` | list_running |
| `clawteam/cli/commands.py` | board_gource |

## Entry Points

Start here when exploring this area:

- **`poll`** (Function) — `tests/test_spawn_backends.py:33`
- **`test_collect_live_log_lines_returns_only_unseen`** (Function) — `tests/test_gource.py:11`
- **`test_append_log_lines_writes_and_flushes`** (Function) — `tests/test_gource.py:24`
- **`write`** (Function) — `tests/test_gource.py:30`
- **`flush`** (Function) — `tests/test_gource.py:33`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `DummyStream` | Class | `tests/test_gource.py` | 25 |
| `FakeCache` | Class | `tests/test_board.py` | 233 |
| `poll` | Function | `tests/test_spawn_backends.py` | 33 |
| `test_collect_live_log_lines_returns_only_unseen` | Function | `tests/test_gource.py` | 11 |
| `test_append_log_lines_writes_and_flushes` | Function | `tests/test_gource.py` | 24 |
| `write` | Function | `tests/test_gource.py` | 30 |
| `flush` | Function | `tests/test_gource.py` | 33 |
| `test_launch_gource_live_stream_uses_stdin` | Function | `tests/test_gource.py` | 43 |
| `test_generate_event_log_uses_message_sender_and_member_aliases` | Function | `tests/test_gource.py` | 72 |
| `test_generate_git_log_normalizes_duplicate_path_segments` | Function | `tests/test_gource.py` | 98 |
| `list_running` | Function | `clawteam/spawn/subprocess_backend.py` | 161 |
| `board_gource` | Function | `clawteam/cli/commands.py` | 3456 |
| `generate_event_log` | Function | `clawteam/board/gource.py` | 74 |
| `generate_git_log` | Function | `clawteam/board/gource.py` | 149 |
| `generate_combined_log` | Function | `clawteam/board/gource.py` | 195 |
| `collect_live_log_lines` | Function | `clawteam/board/gource.py` | 204 |
| `append_log_lines` | Function | `clawteam/board/gource.py` | 227 |
| `stream_gource_live` | Function | `clawteam/board/gource.py` | 235 |
| `find_gource` | Function | `clawteam/board/gource.py` | 292 |
| `launch_gource` | Function | `clawteam/board/gource.py` | 303 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Do_GET → Ensure_within_root` | cross_community | 8 |
| `Do_GET → Validate_identifier` | cross_community | 8 |
| `Do_GET → Config_path` | cross_community | 7 |
| `Do_GET → ClawTeamConfig` | cross_community | 7 |
| `Board_gource → MailboxManager` | cross_community | 5 |
| `Do_GET → Count` | cross_community | 5 |
| `Preset_set → Write` | cross_community | 5 |
| `Preset_generate_profile → Write` | cross_community | 5 |
| `Board_gource → BoardCollector` | cross_community | 4 |
| `Board_gource → _parse_iso` | intra_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 9 calls |
| Cli | 7 calls |

## How to Explore

1. `gitnexus_context({name: "poll"})` — see callers and callees
2. `gitnexus_query({query: "board"})` — find related execution flows
3. Read key files listed above for implementation details
