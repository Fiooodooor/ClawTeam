# Codebase Structure

**Analysis Date:** 2026-04-15

## Directory Layout

```
ClawTeam/
├── clawteam/                  # Python package (the product)
│   ├── __main__.py            # `python -m clawteam` → CLI app
│   ├── cli/                   # Typer CLI (one mega-file, ~4800 lines)
│   ├── board/                 # Dashboard: HTTP server + collector + React SPA
│   │   ├── frontend/          # Vite + React + Tailwind + shadcn sources
│   │   └── static/            # Vite build output (served by server.py)
│   ├── team/                  # Team/mailbox/task/plan/runtime-routing logic
│   ├── spawn/                 # Spawn backends (tmux/subprocess/wsh) + profiles
│   ├── transport/             # Pluggable mailbox transport (file / p2p)
│   ├── store/                 # Pluggable task storage (file today)
│   ├── events/                # In-process event bus + user hooks
│   ├── mcp/                   # FastMCP server exposing coordination tools
│   ├── harness/               # Plan-then-execute phase orchestration
│   ├── plane/                 # (parked) Plane project-mgmt bidi sync
│   ├── workspace/             # Git worktree isolation + conflict detection
│   ├── plugins/               # Plugin ABC, discovery, built-in Ralph Loop
│   ├── templates/             # TOML team templates for `clawteam launch`
│   ├── config.py              # `ClawTeamConfig` (pydantic) + load/save
│   ├── identity.py            # AgentIdentity dataclass (env propagation)
│   ├── paths.py               # validate_identifier + ensure_within_root
│   ├── fileutil.py            # atomic_write_text + file_locked
│   └── timefmt.py             # Timezone-aware timestamp formatting
├── tests/                     # Flat pytest suite + tests/board/ subdir
├── docs/                      # Markdown docs + GitHub Pages site
├── scripts/                   # Shell helpers (openclaw_worker.sh, plane-docker-setup.sh)
├── skills/                    # Claude-ish skills bundled with the repo
├── website/                   # Marketing site content
├── assets/                    # Logos/images used by README and docs
├── .clawteam/                 # Project-local data dir (state; gitignored writes)
├── .planning/                 # GSD planning artifacts (this file lives here)
├── .agents/                   # Local agent skill metadata
├── .claude/                   # Local Claude config
├── .playwright-mcp/           # Playwright MCP scratch
├── pyproject.toml             # Package metadata, deps, scripts, ruff, pytest
├── package.json               # npm metadata for repo-level tooling
├── uv.lock                    # uv lockfile
├── README.md                  # Main docs (plus README_CN.md / README_KR.md)
├── ROADMAP.md                 # High-level roadmap
└── LICENSE                    # MIT
```

## Directory Purposes

**clawteam/cli/:**
- Purpose: CLI entry point; every user-facing command.
- Contains: `commands.py` (single ~4800-line file) plus an empty
  `__init__.py` that re-exports `app`.
- Key files: `commands.py` — nested `typer.Typer` apps (`team_app`,
  `inbox_app`, `runtime_app`, `task_app`, `cost_app`, `session_app`,
  `plan_app`, `lifecycle_app`, `identity_app`, `board_app`,
  `workspace_app`, `context_app`, `template_app`, `hook_app`,
  `plugin_app`, `harness_app`, `plane_app`) plus top-level `spawn`,
  `launch`, `run`.

**clawteam/board/:**
- Purpose: Read-mostly dashboard.
- Contains:
  - `server.py` — stdlib `ThreadingHTTPServer`, routes, SSE loop,
    `TeamSnapshotCache`, GitHub README proxy.
  - `collector.py` — `BoardCollector` turning filesystem state into the
    JSON payload the SPA consumes.
  - `liveness.py` — `agents_online` via `tmux list-windows`.
  - `renderer.py` — Rich-based CLI table rendering for `board show`.
  - `gource.py` — Gource visualization wiring.
  - `frontend/` — Vite + React 19 + Tailwind 4 + shadcn sources.
  - `static/` — Vite build output actually served in production.
- Subdirectories: `frontend/src/{App.tsx, main.tsx, index.css, types.ts,
  components/, components/ui/, components/kanban/, components/modals/,
  hooks/, lib/}`.

**clawteam/board/frontend/src/:**
- `App.tsx` — top-level shell with `TeamContext`, hooks up SSE stream,
  mounts topbar/summary/registry/message-stream/kanban/peek/modals.
- `main.tsx` — React 19 `createRoot` bootstrap.
- `types.ts` — TS shapes (`TeamData`, `Task`, `Message`, status enums).
- `index.css` — Tailwind entry + theme tokens.
- `components/` — `topbar.tsx`, `summary-bar.tsx`, `agent-registry.tsx`,
  `message-stream.tsx`, `peek-panel.tsx`.
- `components/ui/` — shadcn primitives (`badge`, `button`, `card`,
  `dialog`, `input`, `label`, `scroll-area`, `select`, `sheet`,
  `textarea`).
- `components/kanban/` — `board.tsx`, `column.tsx`, `task-card.tsx`.
- `components/modals/` — `add-agent.tsx`, `inject-task.tsx`,
  `send-message.tsx`, `set-context.tsx`.
- `hooks/` — `use-team-stream.ts` (EventSource wrapper).
- `lib/` — `api.ts` (fetch helpers), `utils.ts` (shadcn `cn`).

**clawteam/team/:**
- Purpose: Coordination domain — teams, members, tasks, plans, mailbox,
  costs, lifecycle, snapshots, runtime routing.
- Key files:
  - `models.py` — pydantic `TeamConfig`, `TeamMember`, `TeamMessage`,
    `TaskItem`, enums, plus `get_data_dir()` (git-style discovery).
  - `manager.py` — `TeamManager` CRUD.
  - `mailbox.py` — `MailboxManager` over `Transport`; event log.
  - `tasks.py` — imports `TaskStore` from `clawteam.store`.
  - `plan.py` — `PlanManager` + legacy plan paths.
  - `lifecycle.py` — shutdown protocol.
  - `costs.py` — `CostStore` + budget tracking.
  - `snapshot.py` — team/data snapshots for resume.
  - `watcher.py` — `InboxWatcher` polling loop (`receive` every tick).
  - `router.py` — `RuntimeRouter` bridging inbox → tmux pane.
  - `routing_policy.py` — `DefaultRoutingPolicy`, `RuntimeEnvelope`,
    deduping/backoff state (persisted to `runtime_state.json`).
  - `waiter.py` — blocking wait-for-reply helper.

**clawteam/spawn/:**
- Purpose: Launch agents and inject runtime messages.
- Key files:
  - `base.py` — `SpawnBackend` ABC.
  - `tmux_backend.py` — `TmuxBackend.spawn`, `inject_runtime_message`,
    `_inject_prompt_via_buffer`.
  - `subprocess_backend.py`, `wsh_backend.py`, `wsh_rpc.py` — alt
    backends.
  - `adapters.py` — per-CLI integration (claude/codex/gemini/qwen/kimi/
    pi/opencode/nanobot).
  - `profiles.py` / `presets.py` — reusable runtime bundles.
  - `prompt.py` — `build_agent_prompt` (identity + task + workspace
    context + optional skill content).
  - `registry.py` — pid-based spawn registry and liveness checks.
  - `sessions.py` — per-team session files for resume.
  - `command_validation.py` — guardrails for spawn command args.
  - `cli_env.py` — `build_spawn_path`, `resolve_clawteam_executable`.

**clawteam/transport/:**
- Purpose: Raw-byte mailbox delivery abstraction.
- Key files: `base.py` (`Transport` ABC), `__init__.py` (factory +
  registry), `file.py` (atomic writes into inbox dirs), `p2p.py`
  (ZeroMQ), `claimed.py` (`ClaimedMessage` ack/quarantine).

**clawteam/store/:**
- Purpose: Task storage behind `BaseTaskStore`.
- Key files: `base.py`, `file.py` (`FileTaskStore` — one JSON per task +
  `.tasks.lock`). `__init__.py` exposes `get_task_store`.

**clawteam/events/:**
- Purpose: Event bus + user-configurable hooks.
- Key files: `bus.py` (`EventBus`, handler registry, priority ordering,
  async emit), `types.py` (dataclass event types), `hooks.py`
  (`HookManager` turning `HookDef` → shell/python handlers),
  `global_bus.py` (singleton accessor that lazy-loads hooks from config).

**clawteam/mcp/:**
- Purpose: MCP server exposing coordination tools to agents.
- Key files: `server.py` (FastMCP wiring), `helpers.py`
  (`translate_error`), `__main__.py` (`python -m clawteam.mcp`),
  `tools/__init__.py` (registry), and tool modules: `team.py`,
  `task.py`, `mailbox.py`, `plan.py`, `board.py`, `cost.py`,
  `workspace.py`.

**clawteam/harness/:**
- Purpose: Plan-then-execute phase orchestration.
- Key files: `phases.py` (state machine + gates), `roles.py`,
  `contracts.py`, `contract_executor.py`, `orchestrator.py`,
  `conductor.py` (polling driver, Ctrl+C stop), `spawner.py`
  (`PhaseRoleSpawner`), `strategies.py` (respawn / health / notifier
  ABCs), `context.py` (plugin context), `context_recovery.py`,
  `artifacts.py`, `exit_journal.py`, `prompts.py`.

**clawteam/plane/:**
- Purpose: Parked bidirectional sync with self-hosted Plane.
- Key files: `config.py` (`PlaneConfig`), `client.py` (httpx),
  `models.py` (Plane work items), `mapping.py` (status mapping),
  `sync.py` (`PlaneSyncEngine.push_all/pull_all`), `webhook.py` (inbound
  Plane webhook handler), `__init__.py:register_sync_hooks` (event-bus
  subscription).

**clawteam/workspace/:**
- Purpose: Git worktree workspaces + cross-agent conflict detection.
- Key files: `manager.py` (`WorkspaceManager` create/checkpoint/merge/
  cleanup), `git.py` (git shell helpers), `models.py` (pydantic
  registry), `context.py` (`inject_context` for prompts),
  `conflicts.py` (`detect_overlaps`), `__init__.py:get_workspace_manager`.

**clawteam/plugins/:**
- Purpose: Plugin ABC + discovery.
- Key files: `base.py` (`HarnessPlugin` ABC), `manager.py`
  (`PluginManager.discover` via entry points / config / local dirs),
  `ralph_loop_plugin.py` (built-in respawn strategy).

**clawteam/templates/:**
- Purpose: TOML team templates for `clawteam launch`.
- Key files: `__init__.py` (loader + pydantic `TemplateDef`, `AgentDef`,
  `TaskDef`), and six built-in templates: `software-dev.toml`,
  `hedge-fund.toml`, `research-paper.toml`, `strategy-room.toml`,
  `code-review.toml`, `harness-default.toml`.

**tests/:**
- Purpose: Pytest suite.
- Layout: Flat `test_*.py` at the top level, plus a `board/` subdirectory
  for board-specific tests.
- Key file: `conftest.py` — autouse fixture sets `CLAWTEAM_DATA_DIR` to
  `tmp_path/.clawteam` and redirects `HOME`/`USERPROFILE` so no test
  touches the real `~/.clawteam`.
- Coverage includes: `test_cli_commands`, `test_spawn_backends`,
  `test_spawn_cli`, `test_mailbox`, `test_tasks`, `test_board`,
  `test_board/test_liveness.py`, `test_harness`, `test_runtime_routing`,
  `test_waiter`, `test_workspace_manager`, `test_plane_*` (6 files),
  `test_store`, `test_presets`, `test_profiles`, `test_registry`,
  `test_snapshots`, `test_templates`, `test_gource`, etc.

**scripts/:**
- Purpose: Developer / deployment shell helpers.
- Key files: `openclaw_worker.sh`, `plane-docker-setup.sh`.

**docs/:**
- Purpose: User documentation + GitHub Pages site.
- Key files: `board-usage.md`, `transport-architecture.md`, `index.html`,
  `CNAME`, `site-assets/`, `skills/`, `superpowers/`.

## Key File Locations

**Entry Points:**
- `clawteam/__main__.py` — `python -m clawteam` → `cli.commands:app`.
- `clawteam/cli/commands.py:22` — root `typer.Typer` app.
- `clawteam/mcp/server.py:33` — `clawteam-mcp` entry.
- `clawteam/board/server.py:354` — `serve(host, port, ...)` invoked by
  `clawteam board serve`.

**Configuration:**
- `pyproject.toml` — package deps, `[project.scripts]` defining the
  `clawteam` and `clawteam-mcp` entry points, ruff + pytest config.
- `~/.clawteam/config.json` — user config (`ClawTeamConfig` fields:
  `data_dir`, `user`, `default_team`, `default_profile`, `transport`,
  `task_store`, `workspace`, `default_backend`, `skip_permissions`,
  `timezone`, `gource_*`, `profiles`, `presets`, `hooks`, `plugins`,
  `plane`). Fixed path via `clawteam/config.py:78`.
- `clawteam/board/frontend/components.json` — shadcn config.
- `clawteam/board/frontend/vite.config.ts` — Vite build (outputs to
  `../static`).
- `clawteam/board/frontend/tsconfig*.json` — TS config.

**Core logic:**
- `clawteam/team/models.py:15` — `get_data_dir` (env → config → project
  walk-up → `~/.clawteam/`).
- `clawteam/team/manager.py` — team CRUD.
- `clawteam/team/mailbox.py` — mailbox on top of Transport.
- `clawteam/team/watcher.py` + `router.py` + `routing_policy.py` —
  runtime injection pipeline.
- `clawteam/spawn/tmux_backend.py:272` — `inject_runtime_message` via
  `tmux paste-buffer`.
- `clawteam/board/server.py` + `collector.py` + `liveness.py` —
  dashboard backend.
- `clawteam/harness/conductor.py` — phase polling loop.
- `clawteam/events/bus.py` + `global_bus.py` — event system.

**Testing:**
- `tests/conftest.py` — autouse isolation fixture.
- `tests/test_*.py` — per-module tests.
- `tests/board/test_liveness.py` — tmux liveness tests.

**Documentation:**
- `README.md` + `README_CN.md` + `README_KR.md` — user docs.
- `ROADMAP.md` — high-level roadmap.
- `docs/board-usage.md`, `docs/transport-architecture.md` — feature
  deep-dives.

## Naming Conventions

**Files:**
- `snake_case.py` — all Python modules.
- `PascalCase` for classes; `snake_case` for functions and variables.
- Typer subcommand functions: `<verb>_<noun>` (e.g. `spawn_agent`,
  `launch_team`); decorated with `@<group>_app.command("<kebab-name>")`
  so the CLI shows kebab-case while Python stays snake_case.
- TS/TSX in the frontend: `kebab-case.tsx` for components
  (`task-card.tsx`, `peek-panel.tsx`) and `kebab-case.ts` for hooks and
  libs (`use-team-stream.ts`).
- React top-level export: `App.tsx` (PascalCase) — the rest is
  kebab-case, matching shadcn conventions.
- Templates: `<purpose>.toml` under `clawteam/templates/`.
- Tests: `test_<module>.py` at the top of `tests/`.

**Directories:**
- `snake_case` lowercase for Python packages (`team`, `spawn`,
  `harness`).
- Singular nouns for cohesive subsystems (`board`, `harness`,
  `workspace`); plural when the dir contains a collection (`templates/`,
  `tools/`, `plugins/`).
- Frontend dirs: `kebab-case` (`components/`, `hooks/`, `lib/`,
  `components/ui/`, `components/kanban/`, `components/modals/`).

**Special patterns:**
- `__init__.py` re-exports public API and sometimes does lazy imports to
  break cycles (e.g. `clawteam/team/__init__.py:10` lazily loads
  `TaskStore`).
- Data files on disk use camelCase keys (`agentId`, `leadAgentId`,
  `lockedBy`) while Python keeps snake_case. Pydantic models opt in via
  `model_config = {"populate_by_name": True}` and `Field(alias="…")`.
- Environment variables are prefixed `CLAWTEAM_*`; legacy
  `CLAUDE_CODE_*` are accepted as fallbacks (`clawteam/identity.py`).
- Tmux session naming: `clawteam-{team}` (`TmuxBackend.session_name`).
  Windows are named after the agent logical name.
- Inbox directory naming: `{user}_{name}` when user is set, else
  `{name}` (`TeamManager.inbox_name_for`).

## Where to Add New Code

**New CLI command:**
- Add function in `clawteam/cli/commands.py` under the appropriate
  `*_app` (e.g. `@team_app.command("foo")`).
- If it gates new state, create a service module under the relevant
  package (`clawteam/team/`, `clawteam/workspace/`, …) and import lazily
  inside the command.
- Add a pytest in `tests/test_cli_commands.py` (or a dedicated
  `test_<area>.py`).

**New domain logic:**
- Place alongside related services under `clawteam/team/` or its sibling
  packages. Add pydantic models to the existing `models.py` rather than
  creating new scattered model files.
- Tests go in `tests/test_<area>.py`.

**New spawn backend:**
- Implement `SpawnBackend` in `clawteam/spawn/<backend>_backend.py`.
- Wire it up in `clawteam/spawn/__init__.py:get_backend`, or register it
  from a plugin with `register_backend`.
- Tests in `tests/test_spawn_backends.py`.

**New transport:**
- Implement `Transport` in `clawteam/transport/<name>.py`.
- Register in `clawteam/transport/__init__.py:get_transport` or via
  `register_transport` from a plugin.
- Tests in `tests/test_adapters.py` (or a new file).

**New task store backend:**
- Implement `BaseTaskStore` in `clawteam/store/<name>.py`.
- Branch in `clawteam/store/__init__.py:get_task_store`.
- Tests in `tests/test_store.py` / `tests/test_task_store_locking.py`.

**New event type + hook:**
- Add dataclass to `clawteam/events/types.py`, re-export from
  `clawteam/events/__init__.py`.
- Emit with `get_event_bus().emit` / `emit_async`.
- No handler change needed — user hooks can reference it by class name
  in `config.hooks`.

**New board endpoint:**
- Extend `BoardHandler.do_GET` / `do_POST` / `do_PATCH` in
  `clawteam/board/server.py`; add a loader in `BoardCollector`.
- Update `frontend/src/lib/api.ts` + the appropriate React component
  under `frontend/src/components/`.
- Rebuild the SPA (`npm run build` in `clawteam/board/frontend/`) to
  refresh `clawteam/board/static/`.

**New frontend component:**
- Add kebab-case `.tsx` under `clawteam/board/frontend/src/components/`
  (or `components/ui/` for shadcn primitives, `components/kanban/` for
  kanban pieces, `components/modals/` for dialogs).
- Hooks go in `frontend/src/hooks/`; utilities in `frontend/src/lib/`;
  shared types in `frontend/src/types.ts`.

**New MCP tool:**
- Add function in `clawteam/mcp/tools/<area>.py`.
- Register it in `clawteam/mcp/tools/__init__.py:TOOL_FUNCTIONS`.
- Tests in `tests/test_mcp_tools.py` / `tests/test_mcp_server.py`.

**New template:**
- Drop TOML file in `clawteam/templates/` matching `TemplateDef` schema
  (see existing examples).
- Tests in `tests/test_templates.py`.

**New plugin:**
- Subclass `HarnessPlugin` in `clawteam/plugins/<name>_plugin.py`.
- Register via entry point or list the dotted path under `config.plugins`.

## Special Directories

**clawteam/board/static/:**
- Purpose: Pre-built SPA artifacts served by the HTTP server in
  production.
- Source: `npm run build` inside `clawteam/board/frontend/` (outputs via
  `vite.config.ts`). Committed so end-users do not need Node.

**clawteam/board/frontend/node_modules/:**
- Purpose: Local npm dependencies for frontend development.
- Committed: No (gitignored).

**.clawteam/:**
- Purpose: Project-local data directory — what `get_data_dir` finds when
  walking up from the repo. Holds `teams/<team>/{config.json, inboxes/,
  events/, spawn_registry.json, runtime_state.json}`, `tasks/<team>/*`,
  `costs/<team>/*`, `workspaces/<team>/*`, `snapshots/<team>/*`,
  `sessions/<team>/*`, `harness/<team>/*`, `plane-config.json`.
- Committed: Developer-local state; not a tracked artifact.

**.planning/:**
- Purpose: GSD planning documents (including this file).
- Committed: Yes.

**.agents/, .claude/, .playwright-mcp/:**
- Purpose: Local tool/agent metadata. Repo-local, not runtime state.

**.venv/:**
- Purpose: Python virtualenv created during development.
- Committed: No.

**website/:**
- Purpose: Marketing/landing site content (separate from the `docs/`
  GitHub Pages site).

---

*Structure analysis: 2026-04-15*
*Update when directory layout or naming conventions change.*
