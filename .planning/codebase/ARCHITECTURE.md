# Architecture

**Analysis Date:** 2026-04-15

## Pattern Overview

**Overall:** Single-process CLI + stdlib HTTP server + detached agent processes (tmux).
No persistent daemon. Every `clawteam` invocation is a short-lived Python process
that reads/writes a file-based state directory shared with already-running
agent tmux sessions.

**Key Characteristics:**
- Typer-based CLI (`python -m clawteam`) — one subcommand per use case.
- Agents live as independent processes in tmux windows; ClawTeam does not
  supervise them in-memory — it observes them through the filesystem and
  through `tmux list-windows`.
- File-based state. Data directory auto-discovered git-style by walking up
  from cwd looking for `.clawteam/`, fallback `~/.clawteam/`
  (`clawteam/team/models.py:15` — `get_data_dir`).
- Pluggable transport (file default, p2p optional) and pluggable spawn
  backend (tmux default, subprocess, wsh) behind small factory registries.
- In-process synchronous event bus with optional user-defined shell hooks.
- Board = stdlib `ThreadingHTTPServer` + pre-built React SPA + SSE for live
  updates.

## Layers

**CLI layer (`clawteam/cli/`):**
- Purpose: Entry point for humans and agents. Parses args, resolves data
  dir/transport from env/config, then delegates to services.
- Contains: A single file (`clawteam/cli/commands.py`, ~4800 lines)
  organised as nested `typer.Typer` apps — `team_app`, `inbox_app`,
  `runtime_app`, `task_app`, `cost_app`, `board_app`, `workspace_app`,
  `harness_app`, `plane_app`, etc.
- Depends on: Every domain module (team, spawn, board, harness, plane,
  events, transport, workspace).
- Used by: User shells, MCP tool wrappers, and agents calling the CLI
  inside their own tmux pane.

**Domain services (`clawteam/team/`, `clawteam/workspace/`):**
- Purpose: Business logic for teams, mailbox messaging, tasks, plans,
  costs, snapshots, lifecycle, inbox watching, and runtime-injection
  routing.
- Contains: Pydantic models in `clawteam/team/models.py`; stateless
  managers (`TeamManager`, `MailboxManager`, `TaskStore`, `PlanManager`,
  `LifecycleManager`, `WorkspaceManager`).
- Depends on: `clawteam.store`, `clawteam.transport`, `clawteam.events`,
  `clawteam.paths`.
- Used by: CLI commands, MCP tools, board collector, harness conductor.

**Spawn / runtime (`clawteam/spawn/`):**
- Purpose: Launch agents and inject runtime messages into their live
  terminal. Acts as the bridge between file-based coordination and
  living agent processes.
- Contains: `SpawnBackend` ABC (`clawteam/spawn/base.py`) with `TmuxBackend`,
  `SubprocessBackend`, `WshBackend`. Also `registry.py` (liveness by pid),
  `profiles.py` / `presets.py` (reusable CLI/env bundles),
  `prompt.py` (initial agent prompt builder), `adapters.py` (per-CLI
  quirks: claude, codex, gemini, qwen, kimi, pi, opencode, nanobot).
- Depends on: OS (`tmux`, subprocess), `clawteam.config`, `clawteam.team.models`.
- Used by: `clawteam spawn`, `clawteam launch`, harness `PhaseRoleSpawner`,
  runtime router (`clawteam/team/router.py`).

**Transport (`clawteam/transport/`):**
- Purpose: Abstract raw-byte delivery so the mailbox does not care whether
  it is writing files or sending ZeroMQ frames.
- Contains: `Transport` ABC (`clawteam/transport/base.py`), `FileTransport`
  (default; atomic write-then-rename into an inbox directory), optional
  `P2PTransport` (pyzmq, selected via `CLAWTEAM_TRANSPORT=p2p`),
  `ClaimedMessage` helper for ack/quarantine semantics.
- Registered via `register_transport` in `clawteam/transport/__init__.py:10`.
- Used by: `MailboxManager` in `clawteam/team/mailbox.py`.

**Store (`clawteam/store/`):**
- Purpose: Pluggable task storage with advisory file locking.
- Contains: `BaseTaskStore` ABC (`clawteam/store/base.py`), `FileTaskStore`
  (one JSON file per task under `{data_dir}/tasks/{team}/task-*.json`
  with a `.tasks.lock` sidecar).
- Only `file` backend exists today — the ABC is the extension point for
  redis/sql later.

**Events (`clawteam/events/`):**
- Purpose: Synchronous in-process publish/subscribe so internal components
  and user hooks can react to worker lifecycle, task updates, inbox
  send/receive, phase transitions, etc.
- Contains: `EventBus` (`clawteam/events/bus.py`), typed events
  (`clawteam/events/types.py`: `BeforeWorkerSpawn`, `AfterTaskUpdate`,
  `BeforeInboxSend`, `PhaseTransition`, …), `HookManager`
  (`clawteam/events/hooks.py`) which turns `HookDef` entries in the user
  config into shell-command or dotted-path Python handlers. Handlers run
  synchronously in priority order; `emit_async` uses a 2-thread pool.
- Singleton lives in `clawteam/events/global_bus.py:11`; the first call
  loads hooks from `~/.clawteam/config.json`.

**Harness (`clawteam/harness/`):**
- Purpose: Plan-then-execute orchestration for structured multi-agent work.
  Drives a phase state machine (DISCUSS → PLAN → EXECUTE → VERIFY → SHIP
  by default; phases are open strings so plugins can extend them).
- Contains: `PhaseState` / `PhaseRunner` / `PhaseGate`
  (`clawteam/harness/phases.py`), `HarnessOrchestrator`, `HarnessConductor`
  (polling loop, Ctrl+C to stop), `PhaseRoleSpawner`, `ContractExecutor`
  (`contract_executor.py`), `ArtifactStore`, `ExitJournal`.
- Depends on: spawn registry (health), team mailbox/task store (state),
  event bus (phase transitions).

**MCP server (`clawteam/mcp/`):**
- Purpose: Expose mailbox/task/board/plan/workspace operations to running
  agents via the Model Context Protocol so agents do not shell out for
  every coordination action.
- Contains: FastMCP wrapper in `clawteam/mcp/server.py`; tool functions in
  `clawteam/mcp/tools/` (`team.py`, `task.py`, `mailbox.py`, `plan.py`,
  `board.py`, `cost.py`, `workspace.py`), all registered in
  `clawteam/mcp/tools/__init__.py:TOOL_FUNCTIONS`. Errors are translated
  via `clawteam/mcp/helpers.py:translate_error`.
- Entry point `clawteam-mcp` → `clawteam.mcp.server:main`.

**Plane (`clawteam/plane/`) — parked feature:**
- Purpose: Bidirectional sync with a self-hosted Plane instance (tasks
  ↔ work items). Wires `AfterTaskUpdate` to push-on-change via an event
  subscription (`clawteam/plane/__init__.py:15`). Not active today.
- Contains: `PlaneClient` (httpx), `PlaneSyncEngine`, `PlaneConfig`,
  TOML/JSON models, webhook adapter.

**Board (`clawteam/board/`):**
- Purpose: Read-mostly dashboard over team state — discover teams,
  show task kanban, stream message history, see agent liveness.
- Contains:
  - `clawteam/board/server.py` — stdlib `ThreadingHTTPServer` with JSON
    REST endpoints (`/api/overview`, `/api/team/<name>`), SSE endpoint
    (`/api/events/<name>`), POST `/task`, POST `/member`, POST `/message`,
    PATCH `/task/<id>`, `/api/proxy` for a narrowly-allowlisted GitHub
    README fetcher. A `TeamSnapshotCache` with TTL=`interval` shares one
    collector run across concurrent SSE clients.
  - `clawteam/board/collector.py` — builds the team payload by combining
    `TeamManager`, `MailboxManager` (event log), `TaskStore`, `CostStore`,
    `workspace.conflicts`.
  - `clawteam/board/liveness.py` — detects which members have live tmux
    windows (SSE liveness is independent from agent liveness).
  - `clawteam/board/renderer.py`, `clawteam/board/gource.py` — CLI
    renderers (rich tables; Gource visualization of workspaces).
  - `clawteam/board/static/` — Vite build output of the React SPA.
  - `clawteam/board/frontend/` — React + Vite + Tailwind + shadcn sources.

**Workspace (`clawteam/workspace/`):**
- Purpose: Git worktree isolation per agent with an overlap/conflict
  detector so the board can show cross-agent file collisions.
- Contains: `WorkspaceManager` (create/checkpoint/merge/cleanup),
  `conflicts.py` (`detect_overlaps`), `context.py` (builds injected
  context blocks for agent prompts), `git.py` (shell out helpers),
  `models.py` (pydantic registry), a JSON registry under
  `{data_dir}/workspaces/{team}/workspace-registry.json`.

## Data Flow

**CLI command:**
1. User (or agent) runs `clawteam <cmd>`.
2. Entry `clawteam.cli.commands:app` — Typer parses args; the `main()`
   callback optionally exports `CLAWTEAM_DATA_DIR` and `CLAWTEAM_TRANSPORT`.
3. Command handler imports the relevant service lazily, constructs
   pydantic inputs, and calls it.
4. Result is either printed by a rich renderer or JSON-dumped when
   `--json` is set.
5. Process exits; all changes are durable on disk.

**Sending a message (inbox send):**
1. `clawteam inbox send` calls `MailboxManager.send`.
2. `TeamManager.resolve_inbox` turns a logical recipient into its
   on-disk inbox name (`{user}_{name}` or `{name}`).
3. `Transport.deliver` writes bytes atomically (file backend: mkstemp +
   rename into `{data_dir}/teams/{team}/inboxes/{recipient}/msg-*.json`;
   p2p: zmq frame).
4. `MailboxManager._log_event` writes the same payload into the team
   event log (`teams/{team}/events/evt-*.json`, never consumed, used by
   the board's message history).
5. `BeforeInboxSend` fires on the global event bus (`emit_async`), which
   runs any user shell hooks.

**Runtime injection (file state → live tmux pane):**
1. Agent process A writes a message into agent B's inbox (step above).
2. Somewhere a `clawteam runtime watch` loop is running for B. Each tick
   the `InboxWatcher` (`clawteam/team/watcher.py:40`) polls the inbox,
   reads any new `TeamMessage`s, and hands them to a `RuntimeRouter`.
3. `RuntimeRouter.route_message` (`clawteam/team/router.py:69`) normalises
   the message into a `RuntimeEnvelope`, then asks the
   `DefaultRoutingPolicy` (`clawteam/team/routing_policy.py`) whether to
   inject, drop, or defer. Policy state is persisted to
   `{data_dir}/teams/{team}/runtime_state.json` so deduping and backoff
   survive process restarts.
4. On an `inject` decision,
   `TmuxBackend.inject_runtime_message`
   (`clawteam/spawn/tmux_backend.py:272`) uses
   `_inject_prompt_via_buffer` — `tmux load-buffer` + `tmux paste-buffer`
   + submit — to shove a notification into pane `clawteam-{team}:{agent}`.
5. The router records success/failure back into the policy state.

**Board SSE:**
1. `clawteam board serve` boots `clawteam.board.server.serve` — a
   `ThreadingHTTPServer` with `BoardHandler`.
2. Browser loads the Vite-built SPA from `clawteam/board/static/`.
3. React mounts `App.tsx` → `useTeamStream(teamName)`
   (`frontend/src/hooks/use-team-stream.ts`) opens
   `EventSource('/api/events/{team}')`.
4. The server's SSE loop pulls a cached snapshot via
   `TeamSnapshotCache.get(team, loader)` (TTL = `interval`, default 2 s).
   On miss the loader calls `BoardCollector.collect_team` which fans out
   to managers, the event log, cost store, and conflict detector.
5. Frames are serialised as `data: {...}\n\n` until the client closes.
6. SPA mutations (new task, status patch, add agent, send message)
   POST/PATCH through `frontend/src/lib/api.ts`; handlers call into the
   same `TeamManager` / `TaskStore` / `MailboxManager` used by the CLI.

**Harness phase advance:**
1. `clawteam harness ...` constructs `HarnessOrchestrator` + `HarnessConductor`.
2. Conductor loop: check exit journal, call `orchestrator.advance()`
   (runs `PhaseGate.check` per phase), spawn the next role via
   `PhaseRoleSpawner`, poll health through the spawn registry.
3. On `execute`, `ContractExecutor` materialises `SprintContract`
   success criteria as `TaskItem`s for the executor agents.
4. Each transition fires `PhaseTransition` on the event bus.

**State management:**
- All durable state is file-based under `{data_dir}/`:
  - `teams/{team}/config.json`, `teams/{team}/inboxes/<agent>/msg-*.json`,
    `teams/{team}/events/evt-*.json`, `teams/{team}/spawn_registry.json`,
    `teams/{team}/runtime_state.json`.
  - `tasks/{team}/task-*.json` with a `.tasks.lock`.
  - `costs/{team}/...`, `workspaces/{team}/workspace-registry.json`,
    `snapshots/{team}/...`, `sessions/{team}/...`,
    `harness/{team}/{harness_id}/...`, `plane-config.json`.
- User config is `~/.clawteam/config.json` — never affected by
  `--data-dir` (`clawteam/config.py:78` `config_path`).
- Writes use `atomic_write_text` (mkstemp + `os.replace`) plus advisory
  `file_locked` context managers (`clawteam/fileutil.py`) for
  read-modify-write sequences.
- Tests isolate everything via `tests/conftest.py` which sets
  `CLAWTEAM_DATA_DIR=tmp_path/.clawteam` plus `HOME=tmp_path`.

## Key Abstractions

**TeamConfig / TeamMember / TeamMessage / TaskItem:**
- Purpose: Canonical wire/storage schema for coordination state.
- Location: `clawteam/team/models.py`. Pydantic models with
  `populate_by_name=True` and camelCase aliases (`agentId`, `leadAgentId`,
  `lockedBy`, `createdAt`, …) so JSON on disk matches the teammate-tool
  spec while Python keeps snake_case.

**Transport:**
- Purpose: Hide delivery mechanics behind `deliver / fetch / count /
  list_recipients`. Optional `claim_messages` for ack/quarantine.
- Examples: `FileTransport`, `P2PTransport`.
- Pattern: Name-keyed factory registry (`get_transport`,
  `register_transport` in `clawteam/transport/__init__.py`).

**SpawnBackend:**
- Purpose: Hide how a process is launched and how runtime messages reach
  it. Backends can optionally implement `inject_runtime_message`.
- Examples: `TmuxBackend`, `SubprocessBackend`, `WshBackend`.
- Pattern: Factory registry (`clawteam/spawn/__init__.py:15`).

**BaseTaskStore:**
- Purpose: Pluggable tasks with concurrency responsibility delegated to
  the implementation.
- Examples: `FileTaskStore`.
- Pattern: Factory in `clawteam/store/__init__.py:8`.

**EventBus + HarnessEvent hierarchy:**
- Purpose: Decouple lifecycle notifications from consumers (internal code,
  plugins, user hooks).
- Pattern: Synchronous pub/sub with priority-ordered subscribers;
  `emit_async` uses a small thread pool. `resolve_event_type` lets shell
  hooks name events by class name.

**RuntimeEnvelope + RoutingPolicy:**
- Purpose: Convert inbox `TeamMessage`s into decisions on whether to
  interrupt a running agent via tmux paste-buffer, with dedupe and
  backoff.
- Location: `clawteam/team/routing_policy.py`, `clawteam/team/router.py`.

**HarnessPlugin:**
- Purpose: Third-party extension point — subscribe to the event bus,
  contribute phase gates, contribute prompt text.
- Pattern: ABC + entry-point/config discovery in `clawteam/plugins/`.
  Example: `clawteam/plugins/ralph_loop_plugin.py`.

**Profiles / Presets:**
- Purpose: Reusable bundles of CLI + env + model for spawning (e.g. a
  "claude sonnet with bedrock" profile).
- Location: `clawteam/spawn/profiles.py`, `clawteam/spawn/presets.py`.

**Templates:**
- Purpose: One-command team launch (`clawteam launch <template>`) from
  TOML files describing leader, members, initial tasks.
- Location: `clawteam/templates/` (built-ins: `software-dev.toml`,
  `hedge-fund.toml`, `research-paper.toml`, `strategy-room.toml`,
  `code-review.toml`, `harness-default.toml`).

## Entry Points

**CLI:**
- Location: `clawteam/__main__.py` → `clawteam.cli.commands:app`.
- Installed as `clawteam` (pyproject `[project.scripts]`).
- Triggers: User shell, agents calling the CLI, hooks.
- Responsibilities: Parse args, set env overrides, delegate to services.

**Key commands:**
- `clawteam team start <team>` — start the inbox watcher / runtime router
  for an agent (the loop that turns file-delivered messages into tmux
  injections).
- `clawteam launch <template>` — one-shot: create team + spawn agents +
  seed tasks from a TOML template.
- `clawteam spawn [tmux|subprocess] [cmd…] --team <t> --agent-name <n>` —
  low-level single-agent spawn.
- `clawteam board serve` — start the dashboard HTTP server.
- `clawteam runtime watch/inject/state` — interact with the runtime
  routing policy directly.
- `clawteam harness run` — drive the phase state machine.

**MCP server:**
- Location: `clawteam/mcp/server.py:main`, installed as `clawteam-mcp`.
- Triggers: MCP clients (running agents).
- Responsibilities: Expose team/task/mailbox/plan/board/cost/workspace
  tools over stdio.

**Board HTTP server:**
- Location: `clawteam/board/server.py:serve` (invoked by
  `clawteam board serve`).
- Triggers: Browser / SSE clients.
- Responsibilities: Serve static SPA, stream snapshots, accept task and
  message mutations.

**Agents:**
- Not entry points of ClawTeam's own Python code — they are external CLIs
  (claude, codex, gemini, etc.) launched by `TmuxBackend.spawn`. They
  call back into ClawTeam via the CLI or the MCP server.

## Error Handling

**Strategy:**
- CLI commands: raise `typer.Exit(1)` with a red rich message on user
  errors; let unexpected exceptions propagate (Typer prints a traceback).
- Services: raise `ValueError` for invalid identifiers / not-found
  errors (via `clawteam/paths.py:validate_identifier` and
  `ensure_within_root`). `TaskLockError` for contended tasks.
- MCP tools: wrapped in `mcp/server.py:_tool` which calls
  `helpers.translate_error` so client-visible errors are typed MCP errors.
- Event bus: handler exceptions are swallowed to prevent bus corruption
  (`clawteam/events/bus.py:99`).
- Inbox mailbox: malformed message bytes go through `ClaimedMessage.quarantine`
  (for claim-supporting transports) or are silently dropped by
  `_parse_messages` (`clawteam/team/mailbox.py:164`).
- Board SSE: `BrokenPipeError` / `ConnectionResetError` are caught so
  disconnects do not crash the handler thread
  (`clawteam/board/server.py:344`).
- Transport fallback emits a `TransportFallback` event so hooks can log
  or alert.

## Cross-Cutting Concerns

**Identifier safety & path containment:**
- `validate_identifier` rejects anything outside `[A-Za-z0-9._-]`.
- `ensure_within_root` resolves paths and raises if they escape the data
  directory — used everywhere a team name or agent name becomes a path.

**Atomicity:**
- `atomic_write_text` (mkstemp + rename) for JSON files.
- `file_locked` context manager for read-modify-write sequences on
  shared state (registries, task lock file, config).

**Time:**
- All timestamps produced via `_now_iso()` as UTC ISO8601 strings.
- `clawteam/timefmt.py:format_timestamp` formats for display in the
  user's configured timezone (`ClawTeamConfig.timezone`).

**Configuration resolution order:**
- Data dir: `CLAWTEAM_DATA_DIR` → config `data_dir` → nearest
  `.clawteam/` ancestor → `~/.clawteam/`.
- Transport: `CLAWTEAM_TRANSPORT` → config `transport` → `file`.
- Backend: CLI arg → config `default_backend` → `tmux`.
- Skill-like settings (see `get_effective` in `clawteam/config.py:100`)
  report their source (`env` / `file` / `default`) for the `config
  health` command.

**Identity propagation:**
- `AgentIdentity` (`clawteam/identity.py`) reads either `CLAWTEAM_*` or
  legacy `CLAUDE_CODE_*` env vars, and `to_env()` exports the same keys
  into spawned children so agents know their team/role.

**Logging / UI:**
- CLI uses `rich` for tables and coloured errors; `--json` switches to
  machine-readable output.
- SSE handler mutes its own per-request access log lines.

**Validation:**
- Pydantic models across domain types (teams, tasks, messages, plane
  config, harness phases).
- Typer handles CLI-level validation.

---

*Architecture analysis: 2026-04-15*
*Update when the transport/spawn/harness abstractions change.*
