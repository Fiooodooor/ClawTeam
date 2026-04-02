# ClawTeam Roadmap

## Current State (v0.2)

Single user -> single machine -> filesystem -> CLI-driven workflow.

- All state is stored under `~/.clawteam/` (team config, tasks, messages)
- All agents run on the same host
- Pure file I/O with zero external service dependencies

## Phase 1: Transport Abstraction Layer (v0.3)

**Goal**: Make message transport pluggable without changing upper-layer APIs.

**Architecture change**:

Before:

```
MailboxManager -> direct file read/write
```

After:

```
MailboxManager -> Transport (interface)
                  |- FileTransport (default, current behavior)
                  |- (future: RedisTransport, ...)
```

**Work items**:

| Task | Description | Owner Suggestion |
| --- | --- | --- |
| Define Transport interface | `send()`, `receive()`, `peek()`, `peek_count()`, `broadcast()` | Person A |
| Refactor FileTransport | Extract current file mailbox logic into `FileTransport` | Person A |
| Refactor MailboxManager | Select backend via `CLAWTEAM_TRANSPORT=file` | Person A |
| TaskStore abstraction | Extract `FileTaskStore` and reserve extension points | Person B |
| Testing | Ensure behavior remains unchanged after refactor | Person B |

**Deliverables**:

```
clawteam/transport/
|- base.py   # Transport abstract base class
|- file.py   # FileTransport (current behavior)

clawteam/store/
|- base.py   # TaskStore abstract base class
|- file.py   # FileTaskStore (current behavior)
```

**Acceptance**: Existing command behavior remains unchanged; `CLAWTEAM_TRANSPORT=file` stays the default.

## Phase 2: Redis Message Transport (v0.4)

**Goal**: Support cross-machine message delivery.

**Architecture**:

```
Machine A (leader) -- RedisTransport --+
                                        |
Machine B (worker) -- RedisTransport --+

Team config and tasks -> still file-based (or shared filesystem)
Message transport      -> Redis (high-frequency, real-time)
```

**Work items**:

| Task | Description | Owner Suggestion |
| --- | --- | --- |
| RedisTransport implementation | Use `LPUSH`/`RPOP` for send/receive | Person A |
| Connection management | URL config, pool, reconnect logic | Person A |
| Configuration | `CLAWTEAM_TRANSPORT=redis` + `CLAWTEAM_REDIS_URL=redis://...` | Person B |
| Broadcast implementation | Requires team member listing via TeamManager | Person B |
| Hybrid mode | Messages via Redis, config/tasks via files | Person B |
| Integration tests | Verify on 2 machines (or 2 containers) | Shared |

**New dependency**: `redis` (PyPI), optional via `pip install clawteam[redis]`

**Acceptance**:

- On machine A:

```bash
CLAWTEAM_TRANSPORT=redis CLAWTEAM_REDIS_URL=redis://127.0.0.1:6379 clawteam inbox send demo worker-a "hello"
```

- On machine B:

```bash
CLAWTEAM_TRANSPORT=redis CLAWTEAM_REDIS_URL=redis://127.0.0.1:6379 clawteam inbox receive demo --agent worker-a
```

Expected: message is received.

## Phase 3: Shared State Layer (v0.5)

**Goal**: Share team config and tasks across machines, not only messages.

Phase 2 only solves cross-machine messaging. Team config (`config.json`) and tasks (`task-*.json`) remain local file data.

**Two approaches (choose one):**

### Option A: NFS / Shared filesystem

```bash
# All machines mount the same NFS path
# Works with no code changes
```

Simplest rollout path, but requires network filesystem infrastructure.

### Option B: Redis as unified store

```
messages -> Redis (done in Phase 2)
config   -> Redis Hash
tasks    -> Redis Hash

All state in Redis; filesystem is local cache only
```

**Work items (Option B):**

| Task | Description | Owner Suggestion |
| --- | --- | --- |
| RedisTeamStore | Store team config in Redis Hash | Person A |
| RedisTaskStore | Store tasks in Redis Hash | Person B |
| Migration tool | `clawteam migrate file-to-redis` | Shared |
| Unified config | One switch: `CLAWTEAM_BACKEND=redis` | Shared |

**Acceptance**: Two machines share one team config, one task board, and one message queue.

## Phase 4: Multi-user Collaboration (v0.6)

**Goal**: Let agents owned by different users collaborate in one team.

**New capabilities**:

| Capability | Description |
| --- | --- |
| User identity | Distinguish "whose agent" beyond agent name |
| Permission model | Who can create/join/view teams/tasks |
| Namespace | `user1/worker1` vs `user2/worker1` |
| Token auth | Validate identity when connecting to Redis |

```
User A's Claude Code --+
                        +-- shared team collaboration
User B's Claude Code --+
```

## Future UI and Operations

**Goal**: Browser-first dashboard as a richer alternative to terminal rendering.

- Real-time board updates (WebSocket/SSE)
- Multi-team overview
- Drag-and-drop task operations
- Message history timeline

## Summary

- v0.2: single-machine filesystem baseline, usable today
- v0.3: config + multi-user + Web UI baseline complete (cross-machine via shared FS)
- v0.4+: optional transport abstraction / Redis path for larger distributed usage

### v0.3 Completed

- Config system: `clawteam config show/set/get/health`
- Multi-user support: `CLAWTEAM_USER` / `clawteam config set user`, composite uniqueness via `(user, name)`
- Web UI: `clawteam board serve` with live updates and dark dashboard
- Cross-machine pattern: shared FS + `CLAWTEAM_DATA_DIR`, no code changes required

## Collaboration Suggestion

Recommended parallel split for two contributors:

- Phase 1:
  - Person A: Transport abstraction + FileTransport
  - Person B: Store abstraction + FileTaskStore + tests
- Phase 2:
  - Person A: RedisTransport core
  - Person B: config wiring + broadcast + integration tests
- Phase 3:
  - Person A: RedisTeamStore
  - Person B: RedisTaskStore + migration tooling

Align interface contracts early in Phase 1, then implement in parallel.
