# Codebase Structure

**Analysis Date:** 2026-04-28

## Directory Layout

```text
ClawTeam/
├── clawteam/                       # Python source root (the importable package)
│   ├── __init__.py                 # exports __version__ = "0.3.0"
│   ├── __main__.py                 # `python -m clawteam` → cli.commands:app
│   ├── config.py                   # ClawTeamConfig (pydantic) + ~/.clawteam/config.json IO
│   ├── identity.py                 # AgentIdentity dataclass + CLAWTEAM_*/CLAUDE_CODE_* env reader
│   ├── paths.py                    # validate_identifier + ensure_within_root (path safety)
│   ├── fileutil.py                 # atomic_write_text + file_locked (cross-platform)
│   ├── timefmt.py                  # ISO timestamp humanisation
│   ├── cli/                        # Single-binary Typer CLI surface
│   │   ├── __init__.py
│   │   └── commands.py             # ~4800 lines; all sub-apps + commands defined here
│   ├── team/                       # Coordination layer (state + messaging + tasks)
│   │   ├── __init__.py             # re-exports + lazy TaskStore
│   │   ├── models.py               # TeamConfig, TeamMember, TaskItem, TeamMessage, get_data_dir
│   │   ├── manager.py              # TeamManager (CRUD, leader/inbox resolution, cleanup)
│   │   ├── mailbox.py              # MailboxManager (transport-backed + persistent event log)
│   │   ├── tasks.py                # Thin wrapper around store.file.FileTaskStore
│   │   ├── plan.py                 # PlanManager (markdown plan files + approval messages)
│   │   ├── lifecycle.py            # shutdown/idle protocol
│   │   ├── snapshot.py             # save/restore/list team snapshots
│   │   ├── costs.py                # CostStore (per-team token/cost ledger)
│   │   ├── router.py               # RuntimeRouter (mailbox → tmux pane injection)
│   │   ├── routing_policy.py       # DefaultRoutingPolicy (rate-limit, dedupe, defer)
│   │   ├── waiter.py               # MailboxWaiter (blocking RPC-style reply wait)
│   │   └── watcher.py              # InboxWatcher (foreground polling loop sidecar)
│   ├── store/                      # Pluggable task store backends
│   │   ├── __init__.py             # get_task_store() factory
│   │   ├── base.py                 # BaseTaskStore ABC + TaskLockError
│   │   └── file.py                 # FileTaskStore (per-team flock + atomic writes)
│   ├── transport/                  # Pluggable message transport backends
│   │   ├── __init__.py             # get_transport() / register_transport()
│   │   ├── base.py                 # Transport ABC
│   │   ├── claimed.py              # ClaimedMessage (ack/quarantine for atomic-claim transports)
│   │   ├── file.py                 # FileTransport (default; inbox files on disk)
│   │   └── p2p.py                  # P2PTransport (optional pyzmq, falls back to file)
│   ├── events/                     # Pub/sub event bus + hook system
│   │   ├── __init__.py             # re-exports event classes
│   │   ├── bus.py                  # EventBus (sync emit + 2-worker async pool)
│   │   ├── global_bus.py           # singleton get_event_bus() + lazy hook init
│   │   ├── hooks.py                # HookManager (config-defined shell/python hooks)
│   │   └── types.py                # All HarnessEvent dataclasses
│   ├── spawn/                      # Agent process launchers
│   │   ├── __init__.py             # get_backend() factory
│   │   ├── base.py                 # SpawnBackend ABC
│   │   ├── tmux_backend.py         # Default: tmux session per team, window per agent + injection
│   │   ├── subprocess_backend.py   # Headless backend for tests/CI
│   │   ├── wsh_backend.py          # Wave terminal block backend
│   │   ├── wsh_rpc.py              # wsh CLI RPC helpers
│   │   ├── adapters.py             # NativeCliAdapter + per-CLI detection (claude/codex/gemini/...)
│   │   ├── prompt.py               # build_agent_prompt() (system prompt for agents)
│   │   ├── presets.py              # AgentPreset bootstrap helpers
│   │   ├── profiles.py             # AgentProfile resolution
│   │   ├── cli_env.py              # PATH + executable discovery for spawned shells
│   │   ├── command_validation.py   # validate_spawn_command (pre-flight check)
│   │   ├── registry.py             # spawn_registry.json + is_agent_alive (process liveness)
│   │   └── sessions.py             # session metadata persistence
│   ├── workspace/                  # Per-agent git worktrees
│   │   ├── __init__.py             # get_workspace_manager() factory
│   │   ├── manager.py              # WorkspaceManager (create/checkpoint/merge/cleanup)
│   │   ├── git.py                  # Subprocess wrappers around `git worktree`/`git merge`
│   │   ├── conflicts.py            # detect_overlaps() across worktree branches
│   │   ├── context.py              # Cross-worktree status / file ownership
│   │   └── models.py               # WorkspaceInfo, WorkspaceRegistry (pydantic)
│   ├── harness/                    # Plan-then-execute orchestration
│   │   ├── __init__.py
│   │   ├── orchestrator.py         # HarnessOrchestrator (phase machine + gates)
│   │   ├── conductor.py            # HarnessConductor (foreground driver loop)
│   │   ├── phases.py               # DISCUSS/PLAN/EXECUTE/VERIFY/SHIP + Gate classes
│   │   ├── roles.py                # PLANNER/EXECUTOR/EVALUATOR/LEADER RoleConfig
│   │   ├── strategies.py           # Spawn/Respawn/Health/ExitNotifier/Assignment ABCs
│   │   ├── spawner.py              # PhaseRoleSpawner (spawn agents per phase role)
│   │   ├── contracts.py            # SprintContract + SuccessCriterion (pydantic)
│   │   ├── contract_executor.py    # ContractExecutor (materialise contracts → tasks)
│   │   ├── artifacts.py            # ArtifactStore (per-harness artifact dir)
│   │   ├── context.py              # HarnessContext (passed to plugins)
│   │   ├── context_recovery.py     # Mid-flight harness recovery
│   │   ├── exit_journal.py         # FileExitJournal (cross-process exit notifications)
│   │   └── prompts.py              # System-prompt builders per role
│   ├── plugins/                    # Plugin discovery + lifecycle
│   │   ├── __init__.py             # exports HarnessPlugin
│   │   ├── base.py                 # HarnessPlugin ABC (on_register / on_unregister)
│   │   ├── manager.py              # PluginManager (entry_points + config + local dirs)
│   │   └── ralph_loop_plugin.py    # Reference plugin (auto-respawn agents)
│   ├── templates/                  # Built-in team templates (TOML)
│   │   ├── __init__.py
│   │   ├── code-review.toml
│   │   ├── harness-default.toml
│   │   ├── hedge-fund.toml
│   │   ├── research-paper.toml
│   │   ├── software-dev.toml
│   │   └── strategy-room.toml
│   ├── mcp/                        # FastMCP server (LLM tool surface)
│   │   ├── __init__.py
│   │   ├── __main__.py             # `python -m clawteam.mcp`
│   │   ├── server.py               # FastMCP("clawteam") + tool registration
│   │   ├── helpers.py              # translate_error (typed error wrapping)
│   │   └── tools/                  # One module per tool family
│   │       ├── __init__.py         # TOOL_FUNCTIONS list (registration order)
│   │       ├── team.py
│   │       ├── task.py
│   │       ├── mailbox.py
│   │       ├── plan.py
│   │       ├── board.py
│   │       ├── cost.py
│   │       └── workspace.py
│   ├── plane/                      # Plane integration (optional extra)
│   │   ├── __init__.py             # register_sync_hooks(bus, engine, team)
│   │   ├── client.py               # PlaneClient (httpx wrapper)
│   │   ├── config.py               # PlaneConfig + plane-config.json IO
│   │   ├── models.py               # PlaneWorkspace/Project/State/WorkItem/Comment
│   │   ├── mapping.py              # Status ↔ Plane state group / preferred name
│   │   ├── sync.py                 # PlaneSyncEngine (push_task/push_all/pull_all)
│   │   └── webhook.py              # serve_webhook() + HMAC verification + HITL message generation
│   └── board/                      # Read surface (TUI + Web UI)
│       ├── __init__.py
│       ├── collector.py            # BoardCollector (aggregates everything for a team)
│       ├── liveness.py             # tmux_windows()/agents_online() (tmux liveness)
│       ├── renderer.py             # Rich kanban renderer (TUI)
│       ├── gource.py               # Gource custom-log generator + launcher
│       ├── server.py               # ThreadingHTTPServer (/api/* + SSE + GitHub proxy)
│       ├── static/                 # Vite build output (committed!)
│       │   ├── index.html
│       │   └── assets/
│       │       ├── index-G3o_UaVN.js
│       │       └── index-XwtARCXM.css
│       └── frontend/               # Vite + React 19 + Tailwind v4 + shadcn SPA
│           ├── components.json     # shadcn config (style="base-nova", aliases @/...)
│           ├── package.json
│           ├── package-lock.json
│           ├── tsconfig.json
│           ├── tsconfig.app.json
│           ├── tsconfig.node.json
│           ├── vite.config.ts      # outDir = ../static, /api proxy → :8080
│           ├── index.html          # loads Geist + Geist Mono + Instrument Serif
│           ├── .gitignore
│           ├── skills-lock.json
│           └── src/
│               ├── main.tsx        # createRoot + StrictMode
│               ├── App.tsx         # TeamContext + layout shell + dialog wiring
│               ├── index.css       # Tailwind v4 @import + theme tokens
│               ├── types.ts        # Wire types (Task, Member, TeamData, ...)
│               ├── lib/
│               │   ├── utils.ts    # cn() = twMerge(clsx())
│               │   └── api.ts      # fetch wrappers for /api/...
│               ├── hooks/
│               │   └── use-team-stream.ts   # EventSource → TeamData
│               └── components/
│                   ├── topbar.tsx          # Logo + team Select + SSE indicator
│                   ├── summary-bar.tsx     # Per-status counts
│                   ├── agent-registry.tsx  # Member list + AgentAvatar + isRunning dot
│                   ├── message-stream.tsx  # Mailbox event tail
│                   ├── peek-panel.tsx      # Right Sheet for editing tasks + related msgs
│                   ├── kanban/
│                   │   ├── board.tsx       # DragDropProvider + 6 columns
│                   │   ├── column.tsx      # useDroppable
│                   │   └── task-card.tsx   # useSortable + click-vs-drag heuristic
│                   ├── modals/
│                   │   ├── add-agent.tsx
│                   │   ├── inject-task.tsx
│                   │   ├── send-message.tsx
│                   │   └── set-context.tsx
│                   └── ui/                 # shadcn primitives
│                       ├── badge.tsx
│                       ├── button.tsx
│                       ├── card.tsx
│                       ├── dialog.tsx
│                       ├── input.tsx
│                       ├── label.tsx
│                       ├── scroll-area.tsx
│                       ├── select.tsx
│                       ├── sheet.tsx
│                       └── textarea.tsx
│
├── tests/                          # pytest suite (testpaths in pyproject)
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_*.py                   # ~40 modules: config, mailbox, manager,
│   │                               # plane_client/sync/webhook/mapping/integration,
│   │                               # snapshots, harness, spawn_backends, ...
│   └── board/
│       ├── __init__.py
│       └── test_liveness.py
│
├── scripts/                        # Operational helper shell scripts
│   ├── openclaw_worker.sh
│   └── plane-docker-setup.sh
│
├── skills/                         # Project-local skill bundle (clawteam/)
│   └── clawteam/
│       ├── SKILL.md                # Index (intentionally lightweight)
│       ├── agents/openai.yaml
│       └── references/
│           ├── cli-reference.md
│           └── workflows.md
│
├── docs/                           # Static docs site (built via /website/)
│   ├── index.html
│   ├── CNAME
│   ├── .nojekyll
│   ├── board-usage.md
│   ├── transport-architecture.md
│   ├── site-assets/                # Built CSS/JS for the marketing site
│   ├── skills/clawteam/            # Mirror of skills/ for site rendering
│   └── superpowers/                # Plan + spec markdown for board-enhancement work
│       ├── plans/
│       │   ├── 2026-04-13-board-enhancement-kanban-dnd.md
│       │   ├── 2026-04-13-board-react-shadcn-migration.md
│       │   ├── 2026-04-13-plane-hitl-robustness-fixes.md
│       │   ├── 2026-04-14-agent-liveness-detection.md
│       │   ├── 2026-04-14-board-shadcn-adoption.md
│       │   └── 2026-04-15-tmux-injection-hardening.md
│       └── specs/
│           └── 2026-04-13-board-react-shadcn-migration-design.md
│
├── website/                        # Marketing site source (separate from docs/)
│   ├── index.html
│   ├── vite.config.mjs
│   └── src/{App.jsx, main.jsx, styles.css}
│
├── .planning/codebase/             # This directory (codebase maps)
├── .clawteam/                      # Project-local data dir (committed for board demos)
│   ├── plane-config.json
│   ├── teams/{board-test,verify-test}/
│   ├── tasks/{board-test,verify-test}/
│   ├── costs/{board-test,verify-test}/
│   └── workspaces/
│
├── .agents/skills/                 # Local agent skill bundles (clawteam-dev, frontend-design)
├── .claude/                        # Per-project Claude config
├── .github/workflows/ci.yml
├── assets/                         # README artwork
├── pyproject.toml                  # Project metadata + pytest config + ruff config
├── package.json                    # Workspace-level shim (no real JS deps at root)
├── package-lock.json               # Cache for the root shim
├── uv.lock                         # uv-resolved Python lockfile
├── skills-lock.json
├── README.md / README_CN.md / README_KR.md
├── ROADMAP.md
└── LICENSE
```

## Directory Purposes

**`clawteam/`**
- Purpose: The single Python package shipped as the `clawteam` distribution.
- Contains: All runtime code + Vite frontend project (under `board/frontend/`).
- Key files: `__init__.py`, `__main__.py`, `config.py`, `paths.py`,
  `fileutil.py`, `identity.py`.

**`clawteam/cli/`**
- Purpose: Typer CLI entry point.
- Contains: A single 4800-line `commands.py` with one root `app` and ~22
  sub-apps (`config`, `preset`, `profile`, `team`, `inbox`, `runtime`, `task`,
  `cost`, `session`, `plan`, `lifecycle`, `identity`, `board`, `workspace`,
  `context`, `template`, `hook`, `plugin`, `harness`, `plane`).
- Key files: `clawteam/cli/commands.py`.

**`clawteam/team/`**
- Purpose: Coordination layer — teams, members, mailbox, tasks, plans,
  lifecycle, runtime routing, snapshots, costs.
- Key files: `manager.py`, `mailbox.py`, `models.py`, `router.py`,
  `routing_policy.py`, `tasks.py`, `costs.py`.

**`clawteam/store/`**
- Purpose: Pluggable task storage. Currently file-only.
- Key files: `base.py` (ABC), `file.py` (default with cross-platform flock).

**`clawteam/transport/`**
- Purpose: Pluggable message delivery. Default is filesystem inboxes.
- Key files: `base.py`, `file.py`, `p2p.py` (requires pyzmq extra),
  `claimed.py`.

**`clawteam/events/`**
- Purpose: In-process event bus + hook execution.
- Key files: `bus.py`, `global_bus.py`, `types.py`, `hooks.py`.

**`clawteam/spawn/`**
- Purpose: Process launchers for the actual agent CLIs.
- Key files: `tmux_backend.py` (default), `subprocess_backend.py`,
  `wsh_backend.py`, `registry.py`, `prompt.py`, `adapters.py`.

**`clawteam/workspace/`**
- Purpose: Git worktree isolation per agent + cross-worktree conflict
  detection.
- Key files: `manager.py`, `git.py`, `conflicts.py`.

**`clawteam/harness/`**
- Purpose: Higher-level "plan-then-execute" orchestration on top of teams.
- Key files: `orchestrator.py`, `conductor.py`, `phases.py`, `contracts.py`,
  `spawner.py`.

**`clawteam/plugins/`**
- Purpose: Plugin loader + reference Ralph-loop plugin.
- Key files: `manager.py`, `base.py`, `ralph_loop_plugin.py`.

**`clawteam/templates/`**
- Purpose: TOML team templates loaded by `clawteam launch <template>`.
- Generated: No.
- Committed: Yes.

**`clawteam/mcp/`**
- Purpose: FastMCP server exposing coordination operations as MCP tools.
- Key files: `server.py`, `tools/__init__.py` (TOOL_FUNCTIONS list).

**`clawteam/plane/`**
- Purpose: Plane (project management) integration for HITL.
- Key files: `client.py`, `sync.py`, `webhook.py`, `mapping.py`, `config.py`.
- Optional extra: `pip install clawteam[plane]` (adds `httpx`).

**`clawteam/board/`**
- Purpose: Read-mostly aggregator surface. Hosts both the Rich TUI and the
  React Web UI.
- Key files: `collector.py`, `liveness.py`, `renderer.py`, `server.py`,
  `gource.py`.

**`clawteam/board/frontend/`**
- Purpose: Vite-based React 19 + Tailwind v4 + shadcn/ui SPA project.
- Generated: No (the `src/` tree is hand-written).
- Committed: Yes (whole tree, including `package-lock.json` and
  `components.json`).
- Build command: `npm run build` (writes to `../static/`).

**`clawteam/board/static/`**
- Purpose: Build output of the Vite project, served by the Python HTTP
  handler at `/` and `/assets/...`.
- Generated: Yes (by `vite build`).
- Committed: Yes — this is intentional so end users get the SPA without
  needing Node installed.

**`tests/`**
- Purpose: pytest suite. Configured via `[tool.pytest.ini_options]
  testpaths = ["tests"]` in `pyproject.toml`.
- Layout: Mostly flat, with one nested package `tests/board/`.

**`scripts/`**
- Purpose: Shell helpers (Plane Docker setup, OpenClaw worker shim).

**`skills/clawteam/`**
- Purpose: Project-local "skill" bundle (the lightweight `SKILL.md` + a few
  reference docs and an agent YAML).
- Mirror copy: `docs/skills/clawteam/` (used by the marketing site).

**`docs/`**
- Purpose: Built static documentation/marketing site (`index.html` +
  `site-assets/`) plus markdown specs and plans under `superpowers/`.
- Generated: Partially — `site-assets/` are built by `website/`.

**`docs/superpowers/plans/` and `docs/superpowers/specs/`**
- Purpose: Architectural plan + spec markdown, mostly produced for the
  board-enhancement workstream (board React migration, agent liveness, tmux
  injection hardening, Plane HITL robustness).

**`website/`**
- Purpose: Source for the marketing/landing site. Builds into `docs/site-assets/`.

**`.planning/codebase/`**
- Purpose: Codebase analysis docs (this directory). Also contains
  `*.stale` snapshots from a previous branch — do not consume those.

**`.clawteam/`**
- Purpose: Project-local data directory (per the new project-local data dir
  feature). Contains demo `teams/`, `tasks/`, `costs/`, `workspaces/` for
  `board-test` and `verify-test` plus a `plane-config.json`. Used to pre-seed
  the board UI during development.

**`.agents/skills/`**
- Purpose: Per-project skill bundles loaded by Claude Code agents
  (`clawteam-dev`, `frontend-design`).

**`assets/`** — README artwork (icon, scene illustrations).

**Repo-root images** (`board-*.png`, `verify-new-ui.png`) — Playwright/manual
screenshots from the board enhancement work.

## Key File Locations

**Entry Points:**
- `clawteam/__main__.py`: `python -m clawteam` shim.
- `clawteam/cli/commands.py`: Typer console-script `clawteam`.
- `clawteam/mcp/__main__.py` and `clawteam/mcp/server.py`: MCP server
  (`clawteam-mcp`).
- `clawteam/board/server.py`: HTTP server for the Web UI (`clawteam board serve`).
- `clawteam/board/frontend/src/main.tsx`: React app bootstrap.
- `clawteam/plane/webhook.py`: Plane webhook receiver
  (`clawteam plane webhook`).

**Configuration:**
- `pyproject.toml`: project metadata, dependencies (typer/pydantic/rich/
  questionary/mcp/httpx-as-extra/pyzmq-as-extra), scripts, ruff, pytest.
- `~/.clawteam/config.json`: user `ClawTeamConfig` (loaded by
  `clawteam/config.py`).
- `<data_dir>/plane-config.json`: `PlaneConfig` (loaded by
  `clawteam/plane/config.py`).
- `clawteam/board/frontend/package.json`: React/Vite/Tailwind/shadcn deps.
- `clawteam/board/frontend/components.json`: shadcn aliases (`@/components`,
  `@/lib`, `@/hooks`, etc.).
- `clawteam/board/frontend/vite.config.ts`: Vite plugins, alias `@`,
  `outDir: "../static"`, `/api` proxy.
- `clawteam/board/frontend/tsconfig*.json`: strict TS config split into
  `tsconfig.app.json` + `tsconfig.node.json`.

**Core Logic:**
- `clawteam/team/manager.py`: TeamManager (CRUD).
- `clawteam/team/mailbox.py`: MailboxManager (send/receive/event log).
- `clawteam/store/file.py`: FileTaskStore (concurrency-correct task IO).
- `clawteam/team/router.py` + `clawteam/team/routing_policy.py`: runtime
  injection policy.
- `clawteam/spawn/tmux_backend.py`: tmux session/window/pane management +
  buffer-based prompt injection.
- `clawteam/board/collector.py`: aggregator that both the TUI and React app
  read from.
- `clawteam/plane/sync.py`: bidirectional sync engine.

**Testing:**
- `tests/conftest.py`: shared fixtures.
- `tests/test_plane_*.py`: Plane integration coverage (client, sync,
  webhook, mapping, models, integration).
- `tests/board/test_liveness.py`: tmux liveness detection coverage.
- `tests/test_cli_commands.py`: CLI surface smoke tests.

## Naming Conventions

**Python files:**
- snake_case modules.
- Manager classes live in `*_manager.py` *or* simply named after the domain
  (`manager.py` inside a domain package — e.g. `team/manager.py`,
  `workspace/manager.py`).
- Pydantic models live in `models.py` per package.

**TypeScript/React files:**
- kebab-case file names: `task-card.tsx`, `inject-task.tsx`,
  `use-team-stream.ts`.
- Components are PascalCase exports (`TaskCard`, `InjectTaskDialog`).
- Hooks start with `use-` and live in `src/hooks/`.
- shadcn primitives live in `src/components/ui/` and are re-exported as
  PascalCase.

**Directories:**
- Lowercase, snake_case for Python packages (`team/`, `harness/`,
  `plane/`).
- Lowercase, kebab-style is avoided in Python; used freely in the React tree
  (`kanban/`, `modals/`, `ui/`).

**Data dir layout (`<data_dir>/...`):**
- `teams/{team}/config.json` + `teams/{team}/inboxes/{inbox}/msg-*.json` +
  `teams/{team}/events/evt-*.json` + `teams/{team}/spawn_registry.json`.
- `tasks/{team}/task-{id}.json` + `tasks/{team}/.tasks.lock`.
- `costs/{team}/cost-*.json`.
- `workspaces/{team}/{agent}/` (worktrees) +
  `workspaces/{team}/workspace-registry.json`.
- `plans/{team}/{agent}-{plan_id}.md`.
- `harness/{team}/{harness_id}/state.json`.
- `plane-config.json` at the data-dir root.

**Identifiers:** ASCII letters/digits/`._-` only — enforced by
`validate_identifier` (`clawteam/paths.py`).

## Where to Add New Code

**New CLI command:**
- Decide which sub-app it belongs to (e.g. `team_app`, `task_app`, `plane_app`).
- Add a function decorated with `@<sub_app>.command("name")` inside
  `clawteam/cli/commands.py`. Keep heavy imports inside the function body
  (matches the existing deferred-import pattern that keeps CLI startup fast).
- If you need a brand-new sub-app: declare it near the related ones with
  `<name>_app = typer.Typer(help="...")` and `app.add_typer(<name>_app, name="...")`.

**New coordination feature (e.g. new message type, new task field):**
- Extend the pydantic model in `clawteam/team/models.py` (use camelCase
  alias if the React app needs to read it).
- Update `clawteam/store/file.py` or `clawteam/team/mailbox.py` as needed.
- Mirror types in `clawteam/board/frontend/src/types.ts` and adjust
  `clawteam/board/collector.py` so the new field flows to the SPA.

**New event type:**
- Add the dataclass to `clawteam/events/types.py`, deriving from
  `HarnessEvent`.
- Re-export from `clawteam/events/__init__.py`.
- Producers: `from clawteam.events.global_bus import get_event_bus` then
  `get_event_bus().emit_async(MyEvent(...))`.
- Consumers: `bus.subscribe(MyEvent, handler)` (priority lower = earlier).

**New spawn backend:**
- Subclass `clawteam/spawn/base.py:SpawnBackend`.
- Either register at runtime via `register_backend("name", cls)` or extend
  `get_backend()` in `clawteam/spawn/__init__.py`.
- Persist liveness info via `clawteam/spawn/registry.py:register_agent`.

**New transport / new task store backend:**
- Implement the relevant ABC (`Transport`, `BaseTaskStore`).
- Register via `register_transport(...)` / extend `get_task_store(...)`.

**New MCP tool:**
- Add a function in `clawteam/mcp/tools/<family>.py`.
- Append to `TOOL_FUNCTIONS` in `clawteam/mcp/tools/__init__.py`. The
  decorator wrap is automatic in `clawteam/mcp/server.py`.

**New plugin:**
- Create a module exposing a class that subclasses
  `clawteam/plugins/base.py:HarnessPlugin`.
- Either ship as an entry point under `clawteam.plugins`, list its dotted
  path in `ClawTeamConfig.plugins`, or drop a plugin dir under
  `<data_dir>/plugins/<name>/` with a `plugin.json` manifest.

**New React component:**
- Domain-specific containers go directly under
  `clawteam/board/frontend/src/components/`.
- Kanban-related visuals go under `src/components/kanban/`.
- Modals go under `src/components/modals/`.
- shadcn primitives go under `src/components/ui/` (use `npx shadcn@latest add ...`
  with the alias config from `components.json`).
- Hooks: `src/hooks/use-*.ts`.
- API helpers: extend `src/lib/api.ts` (do not call `fetch` from components).
- Wire types: extend `src/types.ts`; keep them in sync with whatever
  `BoardCollector` emits.

**New API endpoint on the board server:**
- Add a branch in `BoardHandler.do_GET/do_POST/do_PATCH` in
  `clawteam/board/server.py`.
- For mutations, use `_serve_json` and surface CORS via `do_OPTIONS`.
- For SSE-style streams, follow `_serve_sse` with `text/event-stream` and
  poll the relevant collector method, snapshotting via `TeamSnapshotCache`.
- Add a matching wrapper in `clawteam/board/frontend/src/lib/api.ts`.

**New Plane behaviour:**
- REST calls: `clawteam/plane/client.py`. Add a method on `PlaneClient`.
- Status mapping: `clawteam/plane/mapping.py`.
- Sync direction: `clawteam/plane/sync.py` (`push_task` / `pull_all`).
- Webhook event: extend `_handle_*` in `clawteam/plane/webhook.py` and
  re-route via `MailboxManager` for HITL injection.

**New harness phase / gate:**
- Phase constants and base `PhaseGate` live in `clawteam/harness/phases.py`.
- Default registration is in `clawteam/harness/orchestrator.py`.
- Conductor wiring (when to spawn, when to materialise tasks) is in
  `clawteam/harness/conductor.py:_prepare_execute`.

**New tests:**
- Drop a `tests/test_<area>.py` file. Use existing fixtures from
  `tests/conftest.py`. Board-specific tests go under `tests/board/`.

## Special Directories

**`clawteam/board/static/`**
- Purpose: Pre-built Vite output served by the Python HTTP handler.
- Generated: Yes (`vite build`).
- Committed: Yes — required so `pip install clawteam` users get a working
  Web UI without Node.

**`clawteam/board/frontend/node_modules/`**
- Purpose: npm install output for the SPA project.
- Generated: Yes.
- Committed: No (per `clawteam/board/frontend/.gitignore`).

**`.clawteam/`** (project-local data dir)
- Purpose: Pre-seeded teams used for local board demos.
- Generated: Manually populated.
- Committed: Yes (the demo state is intentionally checked in).

**`docs/site-assets/`**
- Purpose: Marketing-site bundle built from `website/`.
- Generated: Yes.
- Committed: Yes (so the static site can be served from the repo without a
  build step).

**`.venv/`, `.pytest_cache/`, `.playwright-mcp/`, `__pycache__/`,
`uv.lock`** — local development byproducts. `.venv/` and the cache dirs are
git-ignored; `uv.lock` is intentionally committed for reproducible installs.

**`.planning/codebase/*.stale`** — Snapshots of an earlier branch's analysis;
**do not** consume them. The non-`*.stale` files are the live maps.

---

*Structure analysis: 2026-04-28*
