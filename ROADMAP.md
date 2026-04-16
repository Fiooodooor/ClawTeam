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

| 任务 | 描述 | 建议 |
|------|------|------|
| 定义 Transport 接口 | `send()`, `receive()`, `peek()`, `peek_count()`, `broadcast()` | 人员 A |
| 重构 FileTransport | 把 `mailbox.py` 当前的文件操作抽成 `FileTransport` 类 | 人员 A |
| 重构 MailboxManager | 通过 `CLAWTEAM_TRANSPORT=file` 选择 backend | 人员 A |
| TaskStore 抽象 | 同样抽出 `FileTaskStore`，预留接口 | 人员 B |
| 测试 | 确保重构后行为不变 | 人员 B |

```
clawteam/transport/
|- base.py   # Transport abstract base class
|- file.py   # FileTransport (current behavior)

clawteam/store/
|- base.py   # TaskStore abstract base class
|- file.py   # FileTaskStore (current behavior)
```

**验收**: 所有现有命令行为不变，`CLAWTEAM_TRANSPORT=file` 为默认值。

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

| 任务 | 描述 | 建议 |
|------|------|------|
| RedisTransport 实现 | `LPUSH`/`RPOP` 实现 send/receive | 人员 A |
| 连接管理 | URL 配置、连接池、断线重连 | 人员 A |
| 配置方式 | `CLAWTEAM_TRANSPORT=redis` + `CLAWTEAM_REDIS_URL=redis://...` | 人员 B |
| broadcast 实现 | 需要知道团队成员列表 → 依赖 TeamManager | 人员 B |
| 混合模式 | 消息走 Redis，配置/任务走文件 | 人员 B |
| 集成测试 | 两台机器（或两个 container）实际跑通 | 一起 |

**New dependency**: `redis` (PyPI), optional via `pip install clawteam[redis]`

**验收**:
```bash
# 机器 A
export CLAWTEAM_TRANSPORT=redis
export CLAWTEAM_REDIS_URL=redis://192.168.1.100:6379
clawteam team spawn-team dev-team -n leader
clawteam spawn tmux claude --team dev-team -n worker1 --task "..."

# 机器 B
export CLAWTEAM_TRANSPORT=redis
export CLAWTEAM_REDIS_URL=redis://192.168.1.100:6379
clawteam inbox receive dev-team --agent worker1
# => 收到消息 ✅
```

---

## Phase 3: 共享状态层 (v0.5)

**目标**: 团队配置和任务也能跨机器共享。

Phase 2 只解决了消息跨机器，但团队配置（`config.json`）和任务（`task-*.json`）还在本地文件。

**两种路线（选一个）**:

### 路线 A: NFS / 共享文件系统

```bash
CLAWTEAM_TRANSPORT=redis CLAWTEAM_REDIS_URL=redis://127.0.0.1:6379 clawteam inbox send demo worker-a "hello"
```

- On machine B:

```bash
CLAWTEAM_TRANSPORT=redis CLAWTEAM_REDIS_URL=redis://127.0.0.1:6379 clawteam inbox receive demo --agent worker-a
```

Expected: message is received.

| 任务 | 描述 | 建议 |
|------|------|------|
| RedisTeamStore | 团队配置存 Redis Hash | 人员 A |
| RedisTaskStore | 任务存 Redis Hash | 人员 B |
| 数据迁移工具 | `clawteam migrate file-to-redis` | 一起 |
| 统一配置 | `CLAWTEAM_BACKEND=redis` 一个变量搞定所有 | 一起 |

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
clawteam board serve --port 8080
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

### v0.3 已完成内容
- Config 系统：`clawteam config show/set/get/health`
- 多用户协作：`CLAWTEAM_USER` / `clawteam config set user`，(user, name) 复合唯一性
- Web UI：`clawteam board serve`，SSE 实时推送，深色主题看板
- 跨机器方案：SSHFS/云盘 + `CLAWTEAM_DATA_DIR`，零代码改动

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
