<!-- refreshed: 2026-04-28 -->
# Architecture

**Analysis Date:** 2026-04-28

## System Overview

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                                Entry Surfaces                                │
├─────────────────────────┬───────────────────────────┬────────────────────────┤
│   Typer CLI             │   FastMCP server          │   Browser dashboard    │
│  `clawteam.cli`         │  `clawteam.mcp`           │  React + Vite SPA      │
│   (`clawteam` script)   │  (`clawteam-mcp` script)  │  served by board HTTP  │
└────────────┬────────────┴─────────────┬─────────────┴───────────┬────────────┘
             │                          │                         │
             │                          ▼                         ▼
             │         ┌────────────────────────────┐   ┌──────────────────────────┐
             │         │  MCP tool surface          │   │  HTTP + SSE board server │
             │         │  `clawteam/mcp/tools/`     │   │  `clawteam/board/`       │
             │         └─────────────┬──────────────┘   └────────────┬─────────────┘
             │                       │                               │
             ▼                       ▼                               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                        Coordination Core (in-process)                        │
│                                                                              │
│   Team / Mailbox     Tasks         Lifecycle / Plan       Routing            │
│  `clawteam.team.*`   `store.*`     `team.lifecycle`       `team.router`      │
│                                    `team.plan`            `team.routing_policy`│
│                                                                              │
│   Workspace (git worktrees)        Harness orchestrator                      │
│  `clawteam.workspace.*`            `clawteam.harness.*`                      │
│                                                                              │
│   Identity            Plugin manager        Event bus + hooks                │
│  `clawteam.identity`  `clawteam.plugins.*`  `clawteam.events.*`              │
└─────────┬───────────────────┬───────────────────┬────────────────────────────┘
          │                   │                   │
          ▼                   ▼                   ▼
┌────────────────────┐  ┌────────────────────┐  ┌────────────────────────────┐
│ Spawn backends     │  │ Transport backends │  │ Persistence (filesystem)   │
│ `clawteam.spawn.*` │  │ `clawteam.transport.*` │ data dir resolved by       │
│  tmux / subprocess │  │  file (default)    │  │ `team.models.get_data_dir` │
│  / wsh             │  │  / p2p (ZMQ)       │  │  ~/.clawteam or            │
│                    │  │                    │  │  walk-up `.clawteam/`      │
└─────────┬──────────┘  └─────────┬──────────┘  └────────────┬───────────────┘
          │                       │                          │
          ▼                       ▼                          ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ External processes                                                           │
│   tmux session `clawteam-{team}` with one window per agent (CLI in pane)     │
│   Native subprocesses (claude / codex / gemini / kimi / qwen / opencode /    │
│     openclaw / pi / nanobot)                                                 │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Typer CLI app | All user-facing commands grouped into sub-apps (config, profile, preset, team, inbox, runtime, task, cost, session, plan, lifecycle, identity, board, workspace, context, template, hook, plugin, harness) plus top-level `spawn`, `launch`, `run`. | `clawteam/cli/commands.py` |
| FastMCP server | Wraps a flat list of Python tool callables (`TOOL_FUNCTIONS`) as MCP tools and runs over stdio. | `clawteam/mcp/server.py` |
| MCP tool surface | Thin façade over team / task / mailbox / plan / board / cost / workspace operations; converts Python errors to `MCPToolError`. | `clawteam/mcp/tools/`, `clawteam/mcp/helpers.py` |
| Board HTTP/SSE server | stdlib `ThreadingHTTPServer` exposing `/api/overview`, `/api/team/{name}`, `/api/events/{name}` (SSE), `POST/PATCH` task & member & message endpoints, `/api/proxy` (allow-listed), and Vite-built static assets. | `clawteam/board/server.py` |
| Board collector | Aggregates `TeamConfig` + tasks + inbox counts + event log + costs + workspace overlaps into a single JSON snapshot for the dashboard. | `clawteam/board/collector.py` |
| Tmux liveness | Detects which member windows currently exist in the tmux session. | `clawteam/board/liveness.py` |
| React dashboard | SPA shell (`App.tsx`) plus topbar (team selector + SSE indicator), summary bar, kanban board, message stream, agent registry, peek panel, and modal dialogs (inject task / set context / add agent / send message). | `clawteam/board/frontend/src/` |
| Identity | Builds `AgentIdentity` from `CLAWTEAM_*` / `CLAUDE_CODE_*` env vars and round-trips them to spawned children. | `clawteam/identity.py` |
| Config | Loads `~/.clawteam/config.json` (always at the home location, ignoring `data_dir`) into the `ClawTeamConfig` Pydantic model. | `clawteam/config.py` |
| Paths | Identifier validation (`[A-Za-z0-9._-]+`) and `ensure_within_root` to prevent path escapes outside the data dir. | `clawteam/paths.py` |
| Team manager | Create / discover / inspect / cleanup teams; persists `config.json` per team and computes inbox names (`user_name` or `name`). | `clawteam/team/manager.py` |
| Mailbox | Sends, broadcasts, peeks, and receives `TeamMessage` JSON via the active `Transport`; mirrors every send into a per-team append-only `events/` log. | `clawteam/team/mailbox.py` |
| Task store (file backend) | Per-task JSON files under `tasks/{team}/`, guarded by an OS advisory lock on `.tasks.lock`; exposes `BaseTaskStore` interface. | `clawteam/store/file.py`, `clawteam/store/base.py` |
| Plan / Lifecycle / Costs | Plan submit/approve/reject flow; shutdown protocol; cost ledger. | `clawteam/team/plan.py`, `clawteam/team/lifecycle.py`, `clawteam/team/costs.py` |
| Routing policy + router | Normalizes inbox messages into `RuntimeEnvelope`s, asks the policy whether to inject, then dispatches via the tmux backend's `inject_runtime_message`. | `clawteam/team/routing_policy.py`, `clawteam/team/router.py` |
| Inbox watcher | Foreground polling loop that consumes the leader inbox and (optionally) hands messages to a `RuntimeRouter` for tmux injection. | `clawteam/team/watcher.py` |
| Spawn backends | Three concrete `SpawnBackend`s (tmux / subprocess / wsh) selected by `get_backend(name)`; record their results in the spawn registry. | `clawteam/spawn/__init__.py`, `clawteam/spawn/tmux_backend.py`, `clawteam/spawn/subprocess_backend.py`, `clawteam/spawn/wsh_backend.py` |
| Spawn registry | JSON file `teams/{team}/spawn_registry.json` mapping agent name → `{backend, tmux_target, pid, command, spawned_at}` for liveness / shutdown. | `clawteam/spawn/registry.py` |
| Native CLI adapter | Per-CLI command shaping (claude, codex, gemini, kimi, qwen, opencode, openclaw, pi, nanobot): permission flags, workspace flags, prompt placement, post-launch injection. | `clawteam/spawn/adapters.py` |
| Transport (file) | Inbox directory per recipient with msg-{ts}-{uuid}.json files; advisory locks for atomic claim. | `clawteam/transport/file.py`, `clawteam/transport/claimed.py` |
| Transport (p2p) | Optional ZeroMQ PUSH/PULL transport with file-transport fallback when peers are offline (requires `pip install clawteam[p2p]`). | `clawteam/transport/p2p.py` |
| Workspace manager | Provisions per-agent git worktrees, tracks them in a registry, supports checkpoint / merge / cleanup. | `clawteam/workspace/manager.py`, `clawteam/workspace/git.py`, `clawteam/workspace/conflicts.py`, `clawteam/workspace/context.py` |
| Harness orchestrator | Persisted phase state machine (`discuss → plan → execute → verify → ship`) with pluggable `PhaseGate`s and a default `HarnessConductor` polling loop. | `clawteam/harness/orchestrator.py`, `clawteam/harness/phases.py`, `clawteam/harness/conductor.py`, `clawteam/harness/spawner.py` |
| Event bus + hooks | In-process pub/sub (sync `emit` + `emit_async` via small thread pool) with shell- or Python-callable hooks loaded from config. | `clawteam/events/bus.py`, `clawteam/events/global_bus.py`, `clawteam/events/hooks.py`, `clawteam/events/types.py` |
| Plugin manager | Discovers / loads `HarnessPlugin` subclasses from entry points, config, or `{data_dir}/plugins/`; passes a `HarnessContext` capability bundle. | `clawteam/plugins/manager.py`, `clawteam/plugins/base.py`, `clawteam/harness/context.py`, `clawteam/plugins/ralph_loop_plugin.py` |
| Templates | Bundled team blueprints (`harness-default.toml`, `software-dev.toml`, etc.) consumed by `clawteam launch`. | `clawteam/templates/` |
| File util | Atomic writes (`atomic_write_text`) and cross-platform advisory file locks (`file_locked`) used by every persistent store. | `clawteam/fileutil.py` |

## Pattern Overview

**Overall:** Local-first, filesystem-backed multi-agent control plane with pluggable spawn / transport / store backends and an in-process event bus. There is no daemon — the CLI is the orchestrator, and every command operates against shared on-disk state.

**Key Characteristics:**
- A single Python package (`clawteam`) exposes both the CLI (`clawteam` script) and the FastMCP server (`clawteam-mcp` script) defined in `pyproject.toml`.
- Every persistent operation routes through `clawteam.team.models.get_data_dir()`, which prefers `CLAWTEAM_DATA_DIR`, then `config.data_dir`, then walks up from the current working directory looking for `.clawteam/`, then falls back to `~/.clawteam/`. This is what makes data project-local.
- Strict layering: CLI / MCP / board never talk to spawn or transport directly without going through the team / store façade (see `MailboxManager.send` → `Transport.deliver`, `BoardCollector` → `TaskStore` + `MailboxManager`).
- Backend selection is by name through factory functions (`spawn.get_backend`, `transport.get_transport`, `store.get_task_store`); plugins can register additional implementations via `register_backend` / `register_transport`.
- Tmux is treated as a first-class runtime: each agent gets a window in `clawteam-{team}`, lifecycle is wired through `tmux set-hook pane-exited|pane-died` to `clawteam lifecycle on-exit|on-crash`, and runtime injection uses a hardened `load-buffer`/`paste-buffer`/`send-keys` flow with a foreground-command allowlist.
- Three-tier liveness:
  1. **SSE liveness** — `useTeamStream` toggles `isConnected` from `EventSource.onopen / onerror`; rendered as the topbar "Stream live/offline" pill (`clawteam/board/frontend/src/components/topbar.tsx`).
  2. **Tmux window liveness** — `board.liveness.agents_online` checks whether a window with the agent's name still exists in `clawteam-{team}`; rendered per-agent in `agent-registry.tsx` and aggregated as `membersOnline` in the team header.
  3. **Pane process liveness** — `spawn.registry.is_agent_alive` consults the registry, then `_tmux_pane_alive` (checks `#{pane_dead}` and rejects bare shells) with a PID fallback for subprocess agents.

## Layers

**Entry surface (CLI / MCP / Board HTTP):**
- Purpose: Translate external input into coordination-core calls.
- Location: `clawteam/cli/commands.py`, `clawteam/mcp/server.py`, `clawteam/board/server.py`, `clawteam/__main__.py`, `clawteam/mcp/__main__.py`.
- Contains: Typer apps, FastMCP wiring, HTTP request handler, SSE loop.
- Depends on: Coordination core (team / store / spawn / harness), config, identity.
- Used by: Humans (CLI / browser) and AI clients (MCP).

**Coordination core (team + store + workspace + harness):**
- Purpose: Express the domain model: teams, members, tasks, plans, mailboxes, harness phases, costs, workspaces.
- Location: `clawteam/team/`, `clawteam/store/`, `clawteam/workspace/`, `clawteam/harness/`, `clawteam/identity.py`.
- Contains: Pydantic models, managers, gates, lifecycle helpers, conductor.
- Depends on: Spawn (to run agents), transport (to deliver messages), events (to notify), file util (to persist).
- Used by: CLI, MCP, board.

**Runtime layer (spawn + transport + events + plugins):**
- Purpose: Concrete process / message / extension mechanisms.
- Location: `clawteam/spawn/`, `clawteam/transport/`, `clawteam/events/`, `clawteam/plugins/`.
- Contains: Backend implementations, registry, `EventBus`, `HookManager`, `PluginManager`.
- Depends on: file util, paths, config; nothing from CLI/MCP/board.
- Used by: Coordination core.

**Persistence (filesystem):**
- Purpose: All durable state.
- Location: data dir resolved by `get_data_dir()`. Directory layout (relative to data dir):
  ```
  teams/{team}/config.json
  teams/{team}/inboxes/{inbox}/msg-*.json
  teams/{team}/events/evt-*.json
  teams/{team}/spawn_registry.json
  teams/{team}/runtime_state.json
  teams/{team}/peers/{agent}.json   (p2p only)
  tasks/{team}/task-{id}.json + .tasks.lock
  costs/{team}/...
  sessions/{team}/...
  workspaces/{team}/{agent}/        (git worktree path)
  workspaces/{team}/workspace-registry.json
  harness/{team}/{harness_id}/state.json
  plugins/{name}/plugin.json
  ```
- Used by: Every store-aware module.

## Data Flow

### `clawteam team start <team>` (the live coordination loop)

1. `team_start` (`clawteam/cli/commands.py:1199`) loads `TeamConfig` via `TeamManager.get_team` and resolves the spawn backend (`clawteam/spawn/__init__.py:get_backend`).
2. For each `TeamMember`, builds the prompt with `clawteam/spawn/prompt.py:build_agent_prompt` and calls `TmuxBackend.spawn` (`clawteam/spawn/tmux_backend.py:45`).
3. `TmuxBackend.spawn` sets `CLAWTEAM_*` env vars, invokes `NativeCliAdapter.prepare_command` (`clawteam/spawn/adapters.py`), exports shell-safe env into the tmux command line, creates / extends the `clawteam-{team}` session with one window per agent, attaches `pane-exited` / `pane-died` hooks, waits for the pane and TUI to be ready, and either (a) injects the prompt via the hardened `load-buffer`/`paste-buffer`/`send-keys` path or (b) uses `tmux send-keys` directly for non-claude TUIs.
4. Pane id (`#{pane_id}`) and pane PID are captured and persisted by `clawteam/spawn/registry.py:register_agent`.
5. `AfterWorkerSpawn` is emitted async on the global `EventBus` (`clawteam/events/global_bus.py`).
6. When `--watcher` is set (default), a detached `python -m clawteam runtime watch <team> --agent <leader>` process is started; it runs `InboxWatcher` (`clawteam/team/watcher.py`) bound to a `RuntimeRouter` (`clawteam/team/router.py`), which normalizes each new mailbox message into a `RuntimeEnvelope`, asks `DefaultRoutingPolicy` (`clawteam/team/routing_policy.py`) whether to dispatch, and if so calls `TmuxBackend.inject_runtime_message`.

### Runtime injection into a live pane (post-spawn)

1. `TmuxBackend.inject_runtime_message` (`clawteam/spawn/tmux_backend.py:293`) resolves the recorded `pane_id` (falling back to `clawteam-{team}:{agent}`).
2. `_pane_safe_to_inject` (`clawteam/spawn/tmux_backend.py:672`) reads `#{pane_current_command}` and refuses unless it matches the allowlist `{claude, codex, gemini, kimi, qwen, opencode, nanobot, openclaw, pi, node, python, python3}` — preventing shell or sub-TUI execution of pasted content.
3. `_inject_prompt_via_buffer` (`clawteam/spawn/tmux_backend.py:701`) writes the rendered notification to a temp file, calls `_run_tmux(["load-buffer", "-b", "prompt-{agent}-{uuid8}", tmp])`, then `paste-buffer`, then two `Enter` send-keys, then `delete-buffer`. Every call goes through `_run_tmux` (`tmux_backend.py:685`), which raises on non-zero exit so failures aren't silently masked.

### Mailbox send

1. `MailboxManager.send` (`clawteam/team/mailbox.py:72`) resolves the recipient inbox via `TeamManager.resolve_inbox` (handles `user_name` namespacing).
2. Builds a `TeamMessage`, calls `Transport.deliver` (file transport writes `{data_dir}/teams/{team}/inboxes/{inbox}/msg-*.json` atomically; p2p attempts ZMQ PUSH and falls back to file).
3. Mirrors the message into the per-team event log (`teams/{team}/events/evt-*.json`).
4. Emits `BeforeInboxSend` async on the bus.

### Board snapshot fetch (SSE)

1. Browser opens `EventSource('/api/events/{team}')` (`clawteam/board/frontend/src/hooks/use-team-stream.ts`).
2. `BoardHandler._serve_sse` (`clawteam/board/server.py:324`) loops every `interval` seconds, asks `TeamSnapshotCache.get` for a fresh snapshot (TTL = `interval`), and writes `data: {json}\n\n`.
3. The cache loader runs `BoardCollector.collect_team` (`clawteam/board/collector.py:68`), which gathers `TeamConfig`, per-member inbox counts, tasks grouped by status, last 200 event-log messages, cost summary, and workspace overlap data, plus a tmux-window-derived `isRunning` flag per member.

### Harness conductor loop

1. `HarnessConductor.run` (`clawteam/harness/conductor.py:83`) spawns the role agents for the current phase via `PhaseRoleSpawner` (`clawteam/harness/spawner.py`).
2. Each iteration: drains the `FileExitJournal`, calls `HarnessOrchestrator.advance` (which checks `PhaseGate`s and emits `PhaseTransition`), and on `execute` runs `ContractExecutor` to materialize tasks from sprint contracts.
3. Periodic `RegistryHealthCheck.check` calls `clawteam/spawn/registry.py:list_dead_agents` and prints health issues.

**State Management:**
- All durable state is JSON on disk. The only in-process state is the `EventBus` singleton (`events/global_bus.py`) and per-process spawn-backend instance dictionaries (e.g. `TmuxBackend._agents`).
- The board uses a tiny per-handler `TeamSnapshotCache` (TTL = SSE poll interval) so concurrent SSE clients share one collector pass.

## Key Abstractions

**`SpawnBackend` (`clawteam/spawn/base.py`):**
- Purpose: Polymorphic interface for "launch an agent process and report a status string."
- Implementations: `TmuxBackend`, `SubprocessBackend`, `WshBackend`. Plugins can register more via `register_backend(name, cls)`.
- Pattern: Abstract base class + `get_backend(name)` factory.

**`Transport` (`clawteam/transport/base.py`):**
- Purpose: Move opaque message bytes between agents; higher layers (`MailboxManager`) own JSON parsing and quarantine decisions.
- Implementations: `FileTransport` (default, supports claimed reads), `P2PTransport` (ZMQ PUSH/PULL with file fallback).
- Pattern: ABC + `get_transport(name, team_name, **kwargs)` factory; transports may optionally expose `claim_messages` for at-least-once semantics.

**`BaseTaskStore` (`clawteam/store/base.py`):**
- Purpose: Pluggable task persistence with concurrency guarantees owned by the implementation.
- Implementations: `FileTaskStore` (one JSON per task, fcntl/msvcrt locks). `clawteam/team/tasks.py` re-exports it as `TaskStore` for back-compat.
- Pattern: ABC + `get_task_store(team_name, backend)` factory keyed by `CLAWTEAM_TASK_STORE` / config.

**`PhaseGate` (`clawteam/harness/phases.py`):**
- Purpose: Open extension point for "is this phase allowed to advance?"
- Implementations: `ArtifactRequiredGate`, `AllTasksCompleteGate`, `HumanApprovalGate`. Plugins contribute extra gates via `HarnessPlugin.contribute_gates`.
- Pattern: ABC; gates are appended per phase on a `PhaseRunner`.

**`HarnessPlugin` + `HarnessContext` (`clawteam/plugins/base.py`, `clawteam/harness/context.py`):**
- Purpose: Capability-bundle for extensions — plugins receive an `EventBus`, `team_name`, lazy `TaskStore` / `SessionStore` / `ArtifactStore`, and `ClawTeamConfig` instead of being limited to event listening.
- Examples: `clawteam/plugins/ralph_loop_plugin.py`.

**`AgentIdentity` (`clawteam/identity.py`):**
- Purpose: Single source of truth for "who am I" inside a spawned agent. Reads `CLAWTEAM_*` then falls back to `CLAUDE_CODE_*` for compatibility, and round-trips itself into child env via `to_env()`.

**`RuntimeEnvelope` / `RouteDecision` (`clawteam/team/routing_policy.py`):**
- Purpose: Decouple "what arrived in an inbox" from "should we paste it into someone's tmux pane and how." Carries source / target / channel / priority / summary / evidence and a dedupe key.

## Entry Points

**`clawteam` console script (`pyproject.toml` → `clawteam.cli.commands:app`):**
- Location: `clawteam/cli/commands.py`.
- Triggers: `clawteam ...` shell invocation, also `python -m clawteam` (`clawteam/__main__.py`).
- Responsibilities: Parses CLI options, normalizes `--data-dir` into `CLAWTEAM_DATA_DIR`, dispatches to ~20 Typer sub-apps and a handful of top-level commands (`spawn`, `launch`, `run`).

**`clawteam-mcp` console script (`pyproject.toml` → `clawteam.mcp.server:main`):**
- Location: `clawteam/mcp/server.py`, also `python -m clawteam.mcp` (`clawteam/mcp/__main__.py`).
- Triggers: An MCP host launches the server over stdio.
- Responsibilities: Wraps each `TOOL_FUNCTIONS` callable with `translate_error` and registers it through `FastMCP("clawteam").tool()`.

**`clawteam board serve` (`clawteam/cli/commands.py:3510` → `clawteam/board/server.py:serve`):**
- Triggers: User runs `clawteam board serve [--host ... --port ... --interval ...]`.
- Responsibilities: Starts a stdlib `ThreadingHTTPServer` on `127.0.0.1:8080` by default, serves the React build from `clawteam/board/static/`, plus REST + SSE APIs.

**Tmux pane hooks (`clawteam/spawn/tmux_backend.py:158`–`167`):**
- Triggers: tmux fires `pane-exited` / `pane-died` for each spawned pane.
- Responsibilities: Invoke `clawteam lifecycle on-exit|on-crash --team --agent`, which in turn updates the spawn registry, releases task locks, and notifies the leader.

**Inbox watcher (`clawteam runtime watch`, `clawteam/cli/commands.py:2084` → `clawteam/team/watcher.py`):**
- Triggers: Detached child started by `team start --watcher` (default), or run manually.
- Responsibilities: Polls leader inbox, prints / forwards messages, optionally injects them into the tmux leader pane via `RuntimeRouter`.

## Architectural Constraints

- **Threading:** Predominantly single-threaded. The board uses `ThreadingHTTPServer` (one thread per HTTP request, including long-lived SSE connections). The event bus owns a 2-worker `ThreadPoolExecutor` for `emit_async` only (`clawteam/events/bus.py:106`). Spawn backends, store, and transport are synchronous.
- **Global state:** Only one durable singleton: the `EventBus` from `clawteam/events/global_bus.py`. Spawn backends keep per-instance dictionaries (`TmuxBackend._agents`) but the CLI creates one per command invocation, so cross-command state always goes through the on-disk spawn registry. `BoardHandler` carries class-level `collector` / `team_cache` set at server startup.
- **Concurrency model:** Coordination across processes happens through the filesystem. `clawteam/store/file.py` and `clawteam/transport/file.py` use OS advisory locks (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows) and `clawteam/fileutil.py:atomic_write_text` for tmp+rename writes.
- **Path safety:** Every directory derived from user input must go through `paths.ensure_within_root(root, *parts)` — refusing to escape the data dir — and through `paths.validate_identifier(value, kind)` with the regex `[A-Za-z0-9._-]+`.
- **Data-dir resolution:** All on-disk reads/writes go through `clawteam/team/models.py:get_data_dir`. Anything that hardcodes `~/.clawteam` or builds a path without it breaks the project-local walk-up.
- **Config location:** `clawteam/config.py:config_path` is hardwired to `~/.clawteam/config.json` and is intentionally NOT affected by `data_dir` overrides — config is global, data is per-project.
- **Backend availability:** `TmuxBackend` returns `"Error: tmux not installed"` instead of raising when `tmux` is missing. `WshBackend` requires `wsh` to be on PATH or in known TideTerm/WaveTerm locations. `P2PTransport` needs the `[p2p]` extra (`pyzmq`).
- **MCP errors:** All MCP tool exceptions must surface as `MCPToolError`; that's enforced by the `_tool` decorator wrapping every callable in `clawteam/mcp/server.py:16` with `translate_error`.

## Anti-Patterns

### Bypassing `get_data_dir()` for filesystem paths

**What happens:** Code constructs `Path.home() / ".clawteam"` directly instead of calling `get_data_dir()`.
**Why it's wrong:** Breaks the project-local data dir feature — the user runs `clawteam team start ...` inside a repo that has `.clawteam/`, but the new code reads/writes `~/.clawteam/` instead. Also breaks every test that overrides `CLAWTEAM_DATA_DIR`.
**Do this instead:** `from clawteam.team.models import get_data_dir; data = get_data_dir() / "teams" / team_name` — and route through `paths.ensure_within_root` if any segment came from user input. Reference: `clawteam/team/manager.py:_team_dir` and `clawteam/store/file.py:_tasks_root`.

### Calling `subprocess.run(["tmux", ...])` without checking the return code

**What happens:** Code pastes prompt content via tmux but ignores `result.returncode` (or never reads `stderr`), so a failed `load-buffer` looks like success and the pane silently never gets the message.
**Why it's wrong:** Silently masks paste-buffer / load-buffer / send-keys failures and leaves orphan paste buffers behind. This is the bug class fixed by commits `efc5f9c` (unique paste buffers + return-code checks) and `1c9a422` (pane_id targeting).
**Do this instead:** Use `_run_tmux` from `clawteam/spawn/tmux_backend.py:685` for any tmux mutation. For injection, go through `_inject_prompt_via_buffer` (`tmux_backend.py:701`) which uses a unique `prompt-{agent}-{uuid8}` buffer name and cleans up.

### Injecting into a tmux pane without checking the foreground command

**What happens:** Code pastes a prompt directly into a pane that is currently running `bash` / `vim` / `less` / `fzf` / a sub-TUI.
**Why it's wrong:** Shells will execute the pasted content (including `$()` and backticks) and TUIs will misinterpret it. This is exactly the bug class fixed by commit `00a094d`.
**Do this instead:** Always gate injection on `_pane_safe_to_inject(target)` (`clawteam/spawn/tmux_backend.py:672`), which reads `#{pane_current_command}` and only allows the agent-CLI allowlist `_INJECT_SAFE_COMMANDS`.

### Targeting a tmux pane by `session:window_name` instead of `pane_id`

**What happens:** Code re-resolves the target as `clawteam-{team}:{agent_name}` every time it wants to inject.
**Why it's wrong:** Window names can be renamed by the user or shifted by `tile_panes` operations; pane ids (`%42`) are stable for the life of the pane. Fixed in commit `1c9a422`.
**Do this instead:** `TmuxBackend.spawn` captures `#{pane_id}` after the pane appears (`tmux_backend.py:230`) and `inject_runtime_message` reads it back from `self._agents` first, only falling back to the window-name target if no pane id is recorded.

### Letting an MCP tool raise a non-`MCPToolError`

**What happens:** A new MCP tool raises `RuntimeError` / a domain exception directly.
**Why it's wrong:** MCP clients see an opaque "Unexpected error" instead of the structured message; the error envelope contract breaks.
**Do this instead:** Either raise `MCPToolError("...")` (or call `mcp.helpers.fail(...)`), or rely on the `_tool` wrapper plus `translate_error` in `clawteam/mcp/server.py:16` and `clawteam/mcp/helpers.py:25` — but only if the underlying exception is `ValueError` / `RuntimeError` / `TaskLockError`.

### Reading inbox JSON and silently dropping malformed messages without acking

**What happens:** A new transport's `fetch` returns parsed dicts (or skips bytes that don't validate) and never tells the mailbox.
**Why it's wrong:** `MailboxManager` owns parsing and quarantine policy; transports should only return raw bytes (or `ClaimedMessage`s). Without that split, malformed messages either get silently lost or stay in the inbox forever.
**Do this instead:** Implement `Transport.fetch` to return `list[bytes]` (and optionally `claim_messages` for at-least-once). `MailboxManager._parse_claimed_messages` (`clawteam/team/mailbox.py:174`) handles `ack()` vs `quarantine(reason)`.

## Error Handling

**Strategy:** Domain-specific exceptions raised low and translated at the boundary.

**Patterns:**
- `paths.validate_identifier` raises `ValueError` for any unsafe identifier; `paths.ensure_within_root` raises `ValueError("Resolved path escapes the configured data directory")`.
- `store.base.TaskLockError` is raised when an update would conflict with another agent's lock; CLI surfaces it as a non-zero exit, MCP surfaces it through `MCPToolError`.
- Spawn backends return `"Error: ..."` strings from `spawn(...)` instead of raising, so the CLI can pipe them straight to the user without a stack trace.
- The board server returns proper HTTP status codes (`400` for malformed requests, `403` for denied proxy targets, `404` for unknown teams, `500` only for unexpected proxy failures).
- `EventBus.emit` swallows handler exceptions (`events/bus.py:99`) so a buggy hook can't crash the orchestrator; failures are silent — instrument the hook itself if you need observability.
- `_load_hooks_from_config` and most plugin discovery sites wrap import / parse failures in bare `except Exception: pass` — the system stays usable when config is missing or malformed.

## Cross-Cutting Concerns

**Logging:** Almost all user-facing output goes through `rich.console.Console` in the CLI; the board server uses stdlib `BaseHTTPRequestHandler.log_message` (suppressed for SSE). The harness conductor prints to `sys.stderr`. Only `clawteam/workspace/manager.py` uses `logging.getLogger`. There is no structured/JSON logging framework.

**Validation:** Pydantic v2 models (`TeamConfig`, `TeamMember`, `TeamMessage`, `TaskItem`, `WorkspaceInfo`, `PhaseState`, `ClawTeamConfig`, `AgentProfile`, `AgentPreset`, `HookDef`) own field validation. Identifier validation uses the `_IDENTIFIER_RE` from `paths.py`.

**Authentication / authorization:** None internally — this is a local developer tool. The board server only binds `127.0.0.1` by default and the `/api/proxy` endpoint enforces an HTTPS-only allowlist (`api.github.com`, `github.com`, `raw.githubusercontent.com`) plus rejection of loopback / private / link-local hostnames (`board/server.py:33`).

**Concurrency / atomicity:** `clawteam/fileutil.py:atomic_write_text` (mkstemp + replace) for every persisted JSON; `file_locked` advisory locks for spawn registry and task store; per-team `.tasks.lock` guards multi-task batch operations.

**Eventing:** The bus is the single observable spine. Events emitted today: `BeforeWorkerSpawn`, `AfterWorkerSpawn`, `WorkerExit`, `WorkerCrash`, `BeforeTaskCreate`, `AfterTaskUpdate`, `TaskCompleted`, `BeforeInboxSend`, `AfterInboxReceive`, `BeforeWorkspaceMerge`, `AfterWorkspaceCleanup`, `TeamLaunch`, `TeamShutdown`, `AgentIdle`, `HeartbeatTimeout`, `PhaseTransition`, `TransportFallback`, `BoardAttach` (`clawteam/events/types.py`).

**Identity propagation:** Spawn backends export `CLAWTEAM_AGENT_ID` / `CLAWTEAM_AGENT_NAME` / `CLAWTEAM_AGENT_TYPE` / `CLAWTEAM_TEAM_NAME` / `CLAWTEAM_AGENT_LEADER` (and `CLAWTEAM_USER` / `CLAWTEAM_WORKSPACE_DIR` when set) into every child process so the spawned agent can rebuild its identity via `AgentIdentity.from_env`.

---

*Architecture analysis: 2026-04-28*
