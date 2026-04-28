<!-- refreshed: 2026-04-28 -->
# Architecture

**Analysis Date:** 2026-04-28

## System Overview

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Human Operators                                 │
├──────────────────────────┬───────────────────────────┬──────────────────────┤
│  Typer CLI               │  React Board UI           │  Plane (HITL)        │
│  `clawteam ...`          │  http://127.0.0.1:8080    │  external SaaS/OSS   │
│  `clawteam/cli/          │  served by                │  reached via httpx   │
│   commands.py`           │  `clawteam/board/         │  `clawteam/plane/`   │
│                          │   server.py`              │                      │
└──────────┬───────────────┴────────────┬──────────────┴──────────┬───────────┘
           │ Typer commands             │ JSON / SSE              │ REST + webhooks
           ▼                            ▼                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Coordination Layer (`clawteam/team/`)                  │
│  TeamManager · MailboxManager · TaskStore · PlanManager · LifecycleManager  │
│  RuntimeRouter · DefaultRoutingPolicy · MailboxWaiter · InboxWatcher        │
└────┬───────────────┬──────────────┬──────────────┬─────────────────┬────────┘
     │               │              │              │                 │
     ▼               ▼              ▼              ▼                 ▼
┌──────────┐  ┌──────────────┐ ┌──────────┐ ┌────────────┐ ┌──────────────┐
│ Spawn    │  │ Transport    │ │ Store    │ │ Workspace  │ │ Events       │
│ backends │  │ (file / p2p) │ │ (file)   │ │ (worktrees)│ │ (pub/sub bus)│
│ tmux/    │  │ `clawteam/   │ │ `clawteam│ │ `clawteam/ │ │ `clawteam/   │
│ subproc/ │  │  transport/` │ │  /store/`│ │  workspace/│ │  events/`    │
│ wsh      │  │              │ │          │ │            │ │              │
└────┬─────┘  └──────┬───────┘ └────┬─────┘ └─────┬──────┘ └─────┬────────┘
     │               │              │             │              │
     ▼               ▼              ▼             ▼              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│      Project-local data dir (default `./.clawteam/`)                         │
│      teams/{team}/  inboxes/  events/  spawn_registry.json                   │
│      tasks/{team}/task-*.json  costs/{team}/  workspaces/{team}/             │
│      plans/{team}/  harness/{team}/  plane-config.json                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

Three concurrent surfaces — CLI, React board, and Plane — all read and mutate
the same on-disk state via the coordination layer. Live agents run inside tmux
windows spawned by `clawteam team start`; the coordination layer reaches them
either by writing inbox JSON files (which they poll) or by injecting prompts
directly into their tmux pane through `RuntimeRouter` → `TmuxBackend`.

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Typer app | Single binary entry point with sub-apps for team/task/inbox/board/plane/harness/workspace/etc. | `clawteam/cli/commands.py` |
| Module entry | `python -m clawteam` shim that re-exports the Typer app | `clawteam/__main__.py` |
| MCP server | FastMCP server exposing team/task/mailbox/plan/board/cost/workspace tools to LLM clients | `clawteam/mcp/server.py` |
| Config loader | Pydantic `ClawTeamConfig` + nested `PlaneConfig`, persisted at `~/.clawteam/config.json` | `clawteam/config.py` |
| Data dir resolver | Walks cwd ancestors for `.clawteam/`, then env, then config, then `~/.clawteam` | `clawteam/team/models.py` (`get_data_dir`) |
| Path safety | `validate_identifier` + `ensure_within_root` used everywhere a user string maps to a path | `clawteam/paths.py` |
| Atomic IO | mkstemp+`os.replace` + advisory `flock`/`msvcrt` locking for shared JSON files | `clawteam/fileutil.py` |
| TeamManager | Team CRUD, member CRUD, leader/inbox name resolution, project cleanup | `clawteam/team/manager.py` |
| MailboxManager | Send/broadcast/receive/peek, transport-backed inbox + persistent event log | `clawteam/team/mailbox.py` |
| FileTaskStore | Per-team file-backed task store with cross-process flock | `clawteam/store/file.py` |
| RuntimeRouter | Normalises inbox messages to `RuntimeEnvelope` and dispatches via tmux injection | `clawteam/team/router.py` |
| DefaultRoutingPolicy | Decides whether to inject, suppress, or defer (rate-limit / dedupe / quiet hours) | `clawteam/team/routing_policy.py` |
| InboxWatcher | Foreground polling loop that drains the leader's inbox and feeds RuntimeRouter | `clawteam/team/watcher.py` |
| MailboxWaiter | Blocking RPC-style wait for a specific reply key | `clawteam/team/waiter.py` |
| LifecycleManager | shutdown_request/approve/reject + idle notifications | `clawteam/team/lifecycle.py` |
| PlanManager | Persists plan markdown, sends approval/rejection messages | `clawteam/team/plan.py` |
| CostStore | Per-team `costs/<team>/` JSON ledger with `summary()` aggregation | `clawteam/team/costs.py` |
| Snapshot manager | Save/restore/list team snapshots | `clawteam/team/snapshot.py` |
| Transport (file) | Filesystem inboxes under `teams/{team}/inboxes/{agent}/msg-*.json` | `clawteam/transport/file.py` |
| Transport (p2p) | Optional pyzmq-based delivery, falls back to file when missing | `clawteam/transport/p2p.py` |
| TmuxBackend | Spawn agents in `clawteam-{team}` tmux session + buffer-based prompt injection | `clawteam/spawn/tmux_backend.py` |
| SubprocessBackend | Headless spawn for tests / non-tmux environments | `clawteam/spawn/subprocess_backend.py` |
| WshBackend | Wave-terminal `wsh` block backend | `clawteam/spawn/wsh_backend.py` |
| Spawn registry | Persists pid/tmux_target/block_id per agent for liveness checking | `clawteam/spawn/registry.py` |
| Tmux liveness | Lists tmux windows in `clawteam-{team}` session to compute online members | `clawteam/board/liveness.py` |
| WorkspaceManager | Git worktree per agent under `workspaces/{team}/{agent}` with checkpoint/merge/cleanup | `clawteam/workspace/manager.py` |
| Conflict detector | Cross-worktree file-overlap analysis for the board | `clawteam/workspace/conflicts.py` |
| EventBus | Synchronous pub/sub with thread-pool `emit_async`, hook registry | `clawteam/events/bus.py` |
| Global bus | Singleton `get_event_bus()`, lazily loads shell hooks from config | `clawteam/events/global_bus.py` |
| HookManager | Maps `HookDef` (shell/python) to `EventBus` subscriptions | `clawteam/events/hooks.py` |
| HarnessOrchestrator | DISCUSS/PLAN/EXECUTE/VERIFY/SHIP phase machine with gates | `clawteam/harness/orchestrator.py` |
| HarnessConductor | Foreground loop that drives phases + reads exit journal + spawns agents | `clawteam/harness/conductor.py` |
| ContractExecutor | Materialises sprint contracts into tasks for executors | `clawteam/harness/contract_executor.py` |
| PluginManager | Discovers plugins from entry_points / config / `data_dir/plugins/` | `clawteam/plugins/manager.py` |
| BoardCollector | Aggregates teams, members, tasks, costs, conflicts, messages into JSON | `clawteam/board/collector.py` |
| Board HTTP server | Stdlib `ThreadingHTTPServer` exposing `/api/...` JSON + SSE + GitHub README proxy | `clawteam/board/server.py` |
| TUI renderer | Rich-based kanban renderer for `clawteam board show/live` | `clawteam/board/renderer.py` |
| Gource bridge | Combines event log + git worktree history into a Gource custom log | `clawteam/board/gource.py` |
| React app | Vite + React 19 + Tailwind v4 + shadcn/ui SPA built into `clawteam/board/static/` | `clawteam/board/frontend/src/App.tsx` |
| SSE hook | `useTeamStream` opens an `EventSource` against `/api/events/{team}` | `clawteam/board/frontend/src/hooks/use-team-stream.ts` |
| API client | `fetch`-based wrapper around the board HTTP API | `clawteam/board/frontend/src/lib/api.ts` |
| PlaneClient | Synchronous httpx client over `api/v1/workspaces/{slug}/...` | `clawteam/plane/client.py` |
| PlaneSyncEngine | Bidirectional task<->work-item sync, indexed by `metadata.plane_issue_id` | `clawteam/plane/sync.py` |
| Plane webhook | Stdlib HTTP server with HMAC-SHA256 signature verification, raises HITL messages | `clawteam/plane/webhook.py` |
| Plane state mapping | ClawTeam `TaskStatus` ↔ Plane state group / preferred state name | `clawteam/plane/mapping.py` |
| Plane sync hooks | Subscribes to `AfterTaskUpdate` to push outbound changes to Plane | `clawteam/plane/__init__.py` |

## Pattern Overview

**Overall:** Filesystem-as-database, layered service modules around a Typer CLI,
with an event-driven seam (`EventBus`) that lets HTTP / Plane / plugins observe
state mutations.

**Key Characteristics:**
- Single source of truth is the data dir (`./.clawteam/` or `~/.clawteam/`); all
  three surfaces (CLI, React board, Plane sync) read/write the same files.
- Concurrency is handled per-file: `atomic_write_text` (mkstemp + replace) +
  `file_locked` advisory locks. There is no daemon, no DB, no socket — every
  process re-reads disk on demand.
- Identifiers funnelled through `validate_identifier` and `ensure_within_root`
  before any path join — so user input never escapes the data dir.
- Liveness is layered: SSE liveness (HTTP connection alive) ≠ tmux liveness
  (window exists for member name) ≠ process liveness (`is_agent_alive` checks
  pid / tmux pane / wsh block from spawn registry).

## Layers

**CLI surface (`clawteam/cli/`)**
- Purpose: User-facing entry point. One Typer `app` plus sub-apps registered
  via `app.add_typer` for `config`, `preset`, `profile`, `team`, `inbox`,
  `runtime`, `task`, `cost`, `session`, `plan`, `lifecycle`, `identity`,
  `board`, `workspace`, `context`, `template`, `hook`, `plugin`, `harness`,
  `plane`.
- Location: `clawteam/cli/commands.py` (single 4800-line file).
- Depends on: every coordination/spawn/workspace/store module via deferred
  imports inside command handlers.
- Used by: humans (`clawteam ...`) and spawned agents (re-invoke
  `python -m clawteam` for `runtime watch`, `lifecycle on-exit`, etc.).

**Coordination layer (`clawteam/team/`)**
- Purpose: Team CRUD + messaging + tasks + plans + lifecycle + routing.
- Location: `clawteam/team/`.
- Contains: managers, models, file-backed mailbox/task/snapshot/cost code,
  runtime routing.
- Depends on: `transport/`, `store/`, `events/`, `workspace/`, `paths.py`.
- Used by: CLI commands, MCP tools, the board collector, and the Plane sync
  engine and webhook receiver.

**Storage layer (`clawteam/store/`, `clawteam/transport/`)**
- Purpose: Pluggable backends behind narrow ABCs (`BaseTaskStore`, `Transport`).
- Location: `clawteam/store/`, `clawteam/transport/`.
- Contains: file-based defaults (`FileTaskStore`, `FileTransport`) plus a
  registry pattern (`get_task_store`, `get_transport`) so plugins can register
  alternatives.
- Depends on: `paths.py`, `team/models.py` for `get_data_dir`.
- Used by: `MailboxManager`, `TaskStore`, `Plane*`, board collector.

**Spawn layer (`clawteam/spawn/`)**
- Purpose: Launch agent CLIs (claude / codex / gemini / etc.) inside tmux
  windows, subprocess pipes, or wsh blocks; persist liveness info.
- Location: `clawteam/spawn/`.
- Contains: backend ABC, tmux/subprocess/wsh implementations, prompt builder,
  CLI environment helpers, spawn registry, command validation, presets and
  profiles for various coding CLIs.
- Depends on: `paths.py`, `team/models.py`, `fileutil.py`.
- Used by: CLI `team start`, `harness/spawner.py`, `harness/conductor.py`.

**Event layer (`clawteam/events/`)**
- Purpose: In-process pub/sub with shell/python hook execution.
- Location: `clawteam/events/`.
- Contains: `EventBus`, dataclass event types, `HookManager`, global singleton.
- Depends on: nothing structural; emitters import `get_event_bus()` lazily.
- Used by: mailbox send/receive, task store updates, workspace cleanup/merge,
  team launch/shutdown, conductor phase transitions, Plane sync hooks.

**Workspace layer (`clawteam/workspace/`)**
- Purpose: Per-agent git worktrees, conflict detection across agents.
- Location: `clawteam/workspace/`.
- Depends on: `git` CLI through `clawteam/workspace/git.py`.
- Used by: CLI `team start --workspace`, `clawteam workspace ...`, board
  collector for conflict overlay.

**Harness layer (`clawteam/harness/`)**
- Purpose: Plan-then-execute orchestration (DISCUSS → PLAN → EXECUTE → VERIFY →
  SHIP) with per-phase gates, role assignment, contracts, exit journal.
- Location: `clawteam/harness/`.
- Depends on: `team/`, `spawn/`, `events/`.
- Used by: `clawteam launch`, `clawteam harness ...`, `clawteam run`.

**Board surface (`clawteam/board/`)**
- Purpose: Read-mostly aggregator. Two render targets: Rich-based TUI and a
  React SPA served behind a stdlib HTTP server.
- Location: `clawteam/board/` (Python) + `clawteam/board/frontend/` (React) +
  `clawteam/board/static/` (build output).
- Depends on: `team/`, `workspace/conflicts.py`, `spawn/tmux_backend.py`.
- Used by: humans, and indirectly by MCP tools in `clawteam/mcp/tools/board.py`.

**Plane integration (`clawteam/plane/`)**
- Purpose: Treat Plane as the human-in-the-loop board: tasks sync as work
  items; comments containing "approve" / "reject" / "lgtm" become HITL inbox
  messages routed via `MailboxManager` to the team leader.
- Location: `clawteam/plane/`.
- Depends on: `httpx` (optional install: `pip install clawteam[plane]`),
  `store/file.py`, `team/manager.py`, `team/mailbox.py`, `events/`.

**MCP surface (`clawteam/mcp/`)**
- Purpose: Expose the same coordination operations to LLM clients via FastMCP.
- Location: `clawteam/mcp/`.
- Console script: `clawteam-mcp` → `clawteam.mcp.server:main`.

## Data Flow

### Primary task flow (CLI / agent → file store → board)

1. Caller invokes `clawteam task create ...` or any agent calls
   `MailboxManager.send` / `TaskStore.create` (`clawteam/store/file.py:77`).
2. `FileTaskStore.create` builds a `TaskItem` (`clawteam/team/models.py:149`),
   takes the team-wide `_write_lock` (`clawteam/store/file.py:54`), writes
   `task-{id}.json` atomically, and emits `BeforeTaskCreate` /
   `AfterTaskUpdate` events through the global bus.
2a. If a Plane sync hook is registered (via `register_sync_hooks` in
   `clawteam/plane/__init__.py`), `AfterTaskUpdate` triggers
   `PlaneSyncEngine.push_task` (`clawteam/plane/sync.py:43`) which calls the
   Plane REST API and stores `metadata.plane_issue_id` on the task.
3. `BoardCollector.collect_team` (`clawteam/board/collector.py:68`) re-reads
   all `task-*.json` and `evt-*.json` files for the team plus tmux liveness
   and merges them into a single dict.
4. `BoardHandler._serve_sse` (`clawteam/board/server.py:324`) pushes that dict
   every `interval` seconds; `useTeamStream`
   (`clawteam/board/frontend/src/hooks/use-team-stream.ts`) deduplicates via
   `lastPayload` and updates React state.

### Inbox / runtime injection flow

1. Sender calls `MailboxManager.send`
   (`clawteam/team/mailbox.py:72`); message bytes go through
   `Transport.deliver` and a copy is appended to `events/evt-*.json`.
2. `InboxWatcher` (`clawteam/team/watcher.py`) polls the leader's inbox.
3. For each new message, `RuntimeRouter.route_message`
   (`clawteam/team/router.py:69`) builds a `RuntimeEnvelope` and asks
   `DefaultRoutingPolicy` (`clawteam/team/routing_policy.py`) whether to
   inject, suppress, or defer.
4. On `inject`, `TmuxBackend.inject_runtime_message`
   (`clawteam/spawn/tmux_backend.py:272`) writes the rendered notification
   through `_inject_prompt_via_buffer` (`clawteam/spawn/tmux_backend.py:621`),
   which uses tmux `load-buffer` + `paste-buffer` to avoid shell-escaping
   pitfalls and submits with two `Enter` keystrokes.

### Plane → ClawTeam HITL flow

1. Plane fires a webhook to `serve_webhook`
   (`clawteam/plane/webhook.py:205`); `_verify_signature` rejects bad HMACs.
2. For `event=="issue_comment"`, `_handle_comment_event` checks for "approve"
   / "lgtm" / "reject" keywords (`clawteam/plane/webhook.py:97`), updates the
   matching ClawTeam task via `FileTaskStore.update`, and calls
   `_send_hitl_message` to drop a `plan_approved` or `plan_rejected` message
   into the leader's mailbox.
3. The mailbox watcher then injects that message into the leader's tmux pane
   exactly like any other team message.

### Liveness tiers (used by the board)

- **SSE liveness** (`useTeamStream`, `EventSource.onopen` / `onerror`):
  whether the SPA's connection to `/api/events/{team}` is alive. Drives the
  topbar "Stream live / offline" badge in `topbar.tsx`.
- **Tmux window liveness** (`agents_online` in `clawteam/board/liveness.py`):
  enumerates `tmux list-windows -t clawteam-{team}` once per snapshot. Drives
  per-member `isRunning` and the swarm `online/total` badge in `App.tsx`.
- **Process liveness** (`is_agent_alive` in `clawteam/spawn/registry.py`):
  pid / tmux pane / wsh block check from the spawn registry. Drives the
  conductor's `RegistryHealthCheck`, exit detection, and `team status`.

These three signals are deliberately distinct — a swarm can have a healthy SSE
stream with zero tmux liveness (no agents running), or live tmux windows with
dead agent processes (shell still attached after the agent exited; the
`_tmux_pane_alive` check explicitly looks for `pane_dead` and bare-shell
fallback).

## Key Abstractions

**`ClawTeamConfig` / `PlaneConfig`** — pydantic models in `clawteam/config.py`
and `clawteam/plane/config.py`. Persisted as JSON; loaded with
`extra="ignore"`-style tolerance. Env vars override file values via
`get_effective`.

**`TeamConfig` / `TeamMember` / `TaskItem` / `TeamMessage`** — pydantic models
in `clawteam/team/models.py`. Use `populate_by_name = True` and `alias=` to
serialize camelCase on disk/API while staying snake_case in Python.

**`MessageType` / `TaskStatus` / `TaskPriority`** — `str` Enums shared between
mailbox, store, plane mapping, and the React `TaskStatus` union.

**`RuntimeEnvelope` / `RouteDecision`** — dataclasses in
`clawteam/team/routing_policy.py` that decouple "what arrived" from "what to do
about it" so future transports / surfaces can reuse the policy.

**`HarnessEvent`** — base dataclass in `clawteam/events/types.py`. All bus
events derive from it; `register_event_type` lets plugins extend the registry.

**`SpawnBackend` / `Transport` / `BaseTaskStore`** — narrow ABCs in
`clawteam/spawn/base.py`, `clawteam/transport/base.py`,
`clawteam/store/base.py`. Each has a `register_*` + `get_*` factory pair so
plugins can swap implementations.

**`HarnessPlugin`** — base class in `clawteam/plugins/base.py`; lifecycle is
`on_register(ctx) → on_unregister()`; reference impl is
`clawteam/plugins/ralph_loop_plugin.py`.

## Entry Points

**Console scripts (declared in `pyproject.toml`):**
- `clawteam` → `clawteam.cli.commands:app`
- `clawteam-mcp` → `clawteam.mcp.server:main`

**Python module entry:**
- `python -m clawteam` → `clawteam/__main__.py` re-exports the Typer app.
- `python -m clawteam.mcp` → `clawteam/mcp/__main__.py` runs the MCP server.

**HTTP entry points:**
- `clawteam board serve` → `clawteam/board/server.py:354` (`serve()`),
  default bind `127.0.0.1:8080`, ThreadingHTTPServer, SSE via blocking write
  loop in `_serve_sse`.
- `clawteam plane webhook <team>` → `clawteam/plane/webhook.py:205`
  (`serve_webhook`), default port `9091`, binds `0.0.0.0`.

**Frontend dev server:**
- `cd clawteam/board/frontend && npm run dev` → Vite dev server with
  `/api` proxy → `http://localhost:8080` (`vite.config.ts`).
- `npm run build` writes the SPA to `clawteam/board/static/` (consumed by the
  Python board server).

## Architectural Constraints

- **Threading:** Mostly single-threaded. The board uses
  `ThreadingHTTPServer` so each SSE/JSON request gets its own thread. The
  `EventBus` has a 2-worker `ThreadPoolExecutor` for `emit_async`. Tests
  reset the bus via `reset_event_bus()`.
- **Global state:** `EventBus` singleton (`clawteam/events/global_bus.py`)
  with one-shot lazy hook loading; `BoardHandler.collector` /
  `default_team` / `interval` / `team_cache` are class attributes set by
  `serve()` before binding (`clawteam/board/server.py:354`). Tests must
  not start two board servers in the same process.
- **No process-wide DB connection.** Every coordination call re-opens the
  relevant JSON file under an advisory lock. Concurrency is correct because
  every read-modify-write goes through `_write_lock` /
  `file_locked` / `os.replace`.
- **Path safety contract:** Any string that becomes part of a path MUST go
  through `validate_identifier` (regex `[A-Za-z0-9._-]+`) and any join MUST
  go through `ensure_within_root`. Violations are bugs — these are the only
  defenses against `team_name="../etc"` style escapes.
- **Plane sync is opt-in.** It only runs when `PlaneConfig.sync_enabled`
  AND `httpx` is importable AND `register_sync_hooks` was called (currently
  on demand, not from `__init__`). Push-side reads `task.metadata` for
  idempotency; pull-side scans by `metadata.plane_issue_id`.
- **Tmux injection is best-effort.** `RuntimeRouter.dispatch` returns
  `False` and records the failure on the policy when the backend lacks
  `inject_runtime_message` or the tmux target is missing — the message
  still lives in the on-disk inbox and event log.
- **Frontend output dir is checked in.** `vite.config.ts` writes to
  `../static`, so `clawteam/board/static/index.html` and
  `clawteam/board/static/assets/` are committed and shipped in the wheel.
  Editing `frontend/src/...` without rebuilding will not reach end users.

## Anti-Patterns

### Bypassing `ensure_within_root` / `validate_identifier`
**What happens:** Code occasionally calls `get_data_dir() / team_name` directly
(see `_plans_root_path()` style helpers).
**Why it's wrong:** Any unchecked `team_name` allows path traversal — e.g.
`team_name="../../../etc"` resolves outside the data dir.
**Do this instead:** Always pass through
`ensure_within_root(get_data_dir() / "<bucket>", validate_identifier(name, "team name"))`
as `clawteam/team/manager.py:_team_dir` does.

### Hand-writing JSON instead of pydantic dump
**What happens:** A handler builds a dict manually and `json.dumps` it.
**Why it's wrong:** The on-disk format is the API contract for the React app
(camelCase via `by_alias=True`) and Plane sync. Drift between writers and
readers is silent.
**Do this instead:** Use `model.model_dump_json(by_alias=True, exclude_none=True)`
+ `atomic_write_text`, mirroring `MailboxManager._log_event`
(`clawteam/team/mailbox.py:48`).

### Forgetting `start_new_session=True` when fork-spawning helpers
**What happens:** `clawteam team start --watcher` spawns a sidecar
`python -m clawteam runtime watch` (`clawteam/cli/commands.py:1306`).
Without `start_new_session=True`, Ctrl-C in the parent kills the watcher.
**Do this instead:** Always pass `start_new_session=True` and redirect
`stdout`/`stderr` to `DEVNULL` for fire-and-forget sidecars.

### Conflating SSE liveness with agent liveness
**What happens:** UI badges showing the SSE stream as "online" while no
tmux windows exist for any member, leading users to believe agents are
running.
**Why it's wrong:** SSE only proves the HTTP connection is alive; it says
nothing about tmux or process state.
**Do this instead:** Surface both signals separately. The current `App.tsx`
shows the SSE indicator in the topbar (`topbar.tsx`) and a separate
`X/Y online` badge derived from `data.team.membersOnline`
(`clawteam/board/frontend/src/App.tsx:94`).

### Reading the post-build static dir from frontend dev mode
**What happens:** Editing a component and refreshing the Python-served
`http://localhost:8080` instead of the Vite dev server.
**Why it's wrong:** The Python server reads `clawteam/board/static/` (the
built bundle), not `frontend/src/`.
**Do this instead:** Use `npm run dev` and the Vite proxy during iteration;
run `npm run build` before committing.

## Error Handling

**Strategy:** Defensive — never crash a user-facing operation because a
secondary feature failed.

**Patterns:**
- Storage operations raise normal Python exceptions; CLI handlers translate
  to `console.print("[red]...[/red]"); raise typer.Exit(1)`.
- Event handlers are wrapped in `try/except: pass` inside `EventBus.emit`
  (`clawteam/events/bus.py:96`) so a buggy hook cannot break the bus.
- Plane push from the `AfterTaskUpdate` hook catches `Exception` and logs
  with `log.warning(...)` (`clawteam/plane/__init__.py:28`).
- Board collector wraps cost / conflict / message-history augmentation in
  `try/except: pass` blocks so a partially-installed environment still
  returns the core team payload (`clawteam/board/collector.py:128-183`).
- Webhook handler emits 401 on bad HMAC, 400 on bad JSON, 200 with a JSON
  result body otherwise (`clawteam/plane/webhook.py:170`).
- File store concurrency uses a typed `TaskLockError` raised when the caller
  doesn't own the lock and `force=False`.

## Cross-Cutting Concerns

**Logging:** Stdlib `logging` (e.g. `log = logging.getLogger(__name__)` in
`clawteam/plane/*`). User-facing CLI uses `rich.console.Console` for stylised
output. Board HTTP handler suppresses `/api/events/` access logs explicitly
(`clawteam/board/server.py:347`).

**Validation:** Pydantic v2 models everywhere persistent state lives.
`validate_identifier` for any string that becomes a path component.
`ensure_within_root` immediately after.

**Authentication:**
- ClawTeam itself has no auth; the board server binds to `127.0.0.1` by
  default. Treat the data dir as the trust boundary.
- Plane uses `X-API-Key` header (`PlaneClient._headers` in
  `clawteam/plane/client.py:50`).
- Plane webhooks verify HMAC-SHA256 against `PlaneConfig.webhook_secret`
  (`clawteam/plane/webhook.py:19`).
- The board server's `/api/proxy` endpoint is hard-allow-listed to
  `api.github.com`, `github.com`, `raw.githubusercontent.com`, rejects
  redirects, and refuses non-https or private/loopback hosts
  (`clawteam/board/server.py:33-93`).

**Identity:** `AgentIdentity.from_env` (`clawteam/identity.py:37`) builds an
identity from `CLAWTEAM_*` env vars, falling back to legacy `CLAUDE_CODE_*`
ones, so older agents keep working.

**Timezone:** Timestamps are ISO-8601 UTC at write time; display is humanised
through `clawteam/timefmt.py` using the configured `timezone`.

---

*Architecture analysis: 2026-04-28*
