---
name: transport
description: "Skill for the Transport area of clawteam. 45 symbols across 10 files."
---

# Transport

45 symbols | 10 files | Cohesion: 64%

## When to Use

- Working with code in `clawteam/`
- Understanding how test_peek_and_count_skip_locked_preclaimed_consumed_message, test_fetch_consume_skips_message_if_claim_fails, read work
- Modifying transport-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `clawteam/transport/file.py` | unlock, try_lock, _inbox_dir, _claimable_paths, _is_locked (+11) |
| `clawteam/transport/p2p.py` | claim_messages, fetch, _peers_dir, _now_ms, _peer_info (+11) |
| `tests/test_mailbox.py` | test_peek_and_count_skip_locked_preclaimed_consumed_message, test_fetch_consume_skips_message_if_claim_fails, fake_claim |
| `tests/test_board.py` | FakeResponse, read, open |
| `clawteam/transport/base.py` | close, count |
| `clawteam/team/snapshot.py` | _read_inbox_messages |
| `clawteam/transport/claimed.py` | ClaimedMessage |
| `clawteam/team/mailbox.py` | peek_count |
| `clawteam/harness/context_recovery.py` | _teammate_summary |
| `clawteam/board/collector.py` | collect_team_summary |

## Entry Points

Start here when exploring this area:

- **`test_peek_and_count_skip_locked_preclaimed_consumed_message`** (Function) — `tests/test_mailbox.py:346`
- **`test_fetch_consume_skips_message_if_claim_fails`** (Function) — `tests/test_mailbox.py:370`
- **`read`** (Function) — `tests/test_board.py:317`
- **`open`** (Function) — `tests/test_board.py:327`
- **`unlock`** (Function) — `clawteam/transport/file.py:23`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `FakeResponse` | Class | `tests/test_board.py` | 309 |
| `ClaimedMessage` | Class | `clawteam/transport/claimed.py` | 9 |
| `test_peek_and_count_skip_locked_preclaimed_consumed_message` | Function | `tests/test_mailbox.py` | 346 |
| `test_fetch_consume_skips_message_if_claim_fails` | Function | `tests/test_mailbox.py` | 370 |
| `read` | Function | `tests/test_board.py` | 317 |
| `open` | Function | `tests/test_board.py` | 327 |
| `unlock` | Function | `clawteam/transport/file.py` | 23 |
| `try_lock` | Function | `clawteam/transport/file.py` | 34 |
| `deliver` | Function | `clawteam/transport/file.py` | 137 |
| `claim_messages` | Function | `clawteam/transport/file.py` | 152 |
| `fetch` | Function | `clawteam/transport/file.py` | 225 |
| `count` | Function | `clawteam/transport/file.py` | 245 |
| `close` | Function | `clawteam/transport/base.py` | 32 |
| `fake_claim` | Function | `tests/test_mailbox.py` | 399 |
| `claim_messages` | Function | `clawteam/transport/p2p.py` | 220 |
| `fetch` | Function | `clawteam/transport/p2p.py` | 264 |
| `list_recipients` | Function | `clawteam/transport/file.py` | 253 |
| `list_recipients` | Function | `clawteam/transport/p2p.py` | 295 |
| `deliver` | Function | `clawteam/transport/p2p.py` | 206 |
| `count` | Function | `clawteam/transport/base.py` | 25 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Board_overview → Load_config` | cross_community | 10 |
| `Do_GET → Ensure_within_root` | cross_community | 8 |
| `Do_GET → Validate_identifier` | cross_community | 8 |
| `Board_overview → Ensure_within_root` | cross_community | 8 |
| `Board_overview → Validate_identifier` | cross_community | 8 |
| `Cost_report → FakeResponse` | cross_community | 6 |
| `Cost_show → FakeResponse` | cross_community | 6 |
| `Launch_team → FakeResponse` | cross_community | 5 |
| `Do_GET → Count` | cross_community | 5 |
| `Board_overview → Count` | cross_community | 5 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 17 calls |
| Cli | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_peek_and_count_skip_locked_preclaimed_consumed_message"})` — see callers and callees
2. `gitnexus_query({query: "transport"})` — find related execution flows
3. Read key files listed above for implementation details
