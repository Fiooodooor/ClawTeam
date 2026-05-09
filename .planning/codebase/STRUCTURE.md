# Codebase Structure

**Analysis Date:** 2026-04-28

## Directory Layout

```
ClawTeam/
├── pyproject.toml                # hatchling build, declares `clawteam` + `clawteam-mcp` console scripts
├── uv.lock                       # uv lockfile (Python deps)
├── package.json                  # Trivial root package.json (no JS deps here)
├── package-lock.json
├── README.md / README_CN.md / README_KR.md
├── ROADMAP.md / LICENSE
├── board-*.png / verify-new-ui.png  # board screenshots (kept in repo for docs)
│
├── clawteam/                     # The Python package — primary source root
│   ├── __init__.py               # `__version__ = "0.3.0"`
│   ├── __main__.py               # `python -m clawteam` → CLI app
│   ├── config.py                 # `ClawTeamConfig`, `load_config`, `save_config`, `get_effective`
│   ├── identity.py               # `AgentIdentity` env round-trip
│   ├── paths.py                  # `validate_identifier`, `ensure_within_root`
│   ├── timefmt.py                # Timestamp display helpers
│   ├── fileutil.py               # `atomic_write_text`, `file_locked`
│   │
│   ├── cli/
│   │   ├── __init__.py
│   │   └── commands.py           # ~4700-line Typer app — all `clawteam <subcommand>` commands
│   │
│   ├── mcp/                      # FastMCP server
│   │   ├── __init__.py
│   │   ├── __main__.py           # `python -m clawteam.mcp` → server.main()
│   │   ├── server.py             # FastMCP wiring; registers each callable in TOOL_FUNCTIONS
│   │   ├── helpers.py            # `MCPToolError`, `translate_error`, `to_payload`, `require_team`
│   │   └── tools/
│   │       ├── __init__.py       # TOOL_FUNCTIONS list
│   │       ├── team.py           # team_list / team_get / team_create / team_member_add / ...
│   │       ├── task.py           # task_create / task_update / task_list / task_get / task_stats
│   │       ├── mailbox.py        # mailbox_send / broadcast / receive / peek / peek_count
│   │       ├── plan.py           # plan_submit / plan_get / plan_approve / plan_reject
│   │       ├── board.py          # board_overview / board_team
│   │       ├── cost.py           # cost_summary
│   │       └── workspace.py      # workspace_agent_diff / file_owners / cross_branch_log / agent_summary
│   │
│   ├── board/                    # Dashboard backend + bundled frontend
│   │   ├── __init__.py
│   │   ├── server.py             # ThreadingHTTPServer + REST + SSE + GitHub-allowlisted proxy
│   │   ├── collector.py          # BoardCollector — aggregates JSON snapshot for SSE
│   │   ├── liveness.py           # tmux_windows / agents_online (tier-2 liveness)
│   │   ├── renderer.py           # Terminal/text renderer for `clawteam board show`
│   │   ├── gource.py             # `clawteam board gource` git visualization helper
│   │   ├── static/               # Vite-built artefacts served by server.py
│   │   │   ├── index.html
│   │   │   └── assets/
│   │   │       ├── index-*.js
│   │   │       └── index-*.css
│   │   └── frontend/             # Source for the React + Vite + Tailwind + shadcn dashboard
│   │       ├── package.json      # React 19, @base-ui/react, @dnd-kit/react, Tailwind v4, Vite 6
│   │       ├── package-lock.json
│   │       ├── vite.config.ts    # alias `@` → src; dev proxy `/api` → :8080; build outDir=../static
│   │       ├── tsconfig.json / tsconfig.app.json / tsconfig.node.json
│   │       ├── components.json   # shadcn config
│   │       ├── index.html
│   │       └── src/
│   │           ├── main.tsx
│   │           ├── App.tsx       # Top-level shell + TeamContext
│   │           ├── index.css     # Tailwind v4 + theme tokens
│   │           ├── types.ts      # TeamData / Member / Task / Message + STATUS_* maps
│   │           ├── hooks/
│   │           │   └── use-team-stream.ts   # EventSource-backed SSE hook (tier-1 liveness)
│   │           ├── lib/
│   │           │   ├── api.ts    # fetchOverview / createTask / updateTask / addMember / sendMessage
│   │           │   └── utils.ts  # `cn` className helper
│   │           └── components/
│   │               ├── topbar.tsx
│   │               ├── summary-bar.tsx
│   │               ├── agent-registry.tsx
│   │               ├── message-stream.tsx
│   │               ├── peek-panel.tsx
│   │               ├── kanban/
│   │               │   ├── board.tsx
│   │               │   ├── column.tsx
│   │               │   └── task-card.tsx
│   │               ├── modals/
│   │               │   ├── add-agent.tsx
│   │               │   ├── inject-task.tsx
│   │               │   ├── send-message.tsx
│   │               │   └── set-context.tsx
│   │               └── ui/       # shadcn primitives (badge / button / card / dialog / input /
│   │                             #   label / scroll-area / select / sheet / textarea)
│   │
│   ├── events/
│   │   ├── __init__.py           # Re-exports event types and EventBus
│   │   ├── bus.py                # EventBus (sync emit + 2-worker async pool)
│   │   ├── global_bus.py         # `get_event_bus()` singleton + auto hook loading
│   │   ├── hooks.py              # HookManager — shell + python callable hooks
│   │   └── types.py              # All HarnessEvent dataclasses
│   │
│   ├── harness/                  # Plan-then-execute orchestration
│   │   ├── __init__.py
│   │   ├── orchestrator.py       # HarnessOrchestrator (state, gates, persistence)
│   │   ├── conductor.py          # HarnessConductor polling loop
│   │   ├── phases.py             # PhaseState + PhaseRunner + ArtifactRequiredGate / AllTasksCompleteGate / HumanApprovalGate
│   │   ├── roles.py              # PLANNER / EXECUTOR / EVALUATOR / LEADER + DEFAULT_ROLES
│   │   ├── strategies.py         # SpawnStrategy / RespawnStrategy / HealthStrategy / ExitNotifier / AssignmentStrategy ABCs
│   │   ├── spawner.py            # PhaseRoleSpawner — default SpawnStrategy
│   │   ├── prompts.py            # System-prompt builder for harness agents
│   │   ├── contracts.py          # SprintContract / SuccessCriterion
│   │   ├── contract_executor.py  # Materializes tasks from sprint contracts
│   │   ├── artifacts.py          # ArtifactStore — registers + reads phase artifacts on disk
│   │   ├── exit_journal.py       # FileExitJournal — cross-process worker exit signal
│   │   ├── context.py            # HarnessContext — capability bundle for plugins
│   │   └── context_recovery.py   # Resumes harness state after a crash
│   │
│   ├── plugins/
│   │   ├── __init__.py           # Re-exports HarnessPlugin
│   │   ├── base.py               # HarnessPlugin ABC — `on_register(ctx)`, `contribute_gates`, `contribute_prompts`
│   │   ├── manager.py            # PluginManager — discover from entry_points / config / {data_dir}/plugins/
│   │   └── ralph_loop_plugin.py  # Reference plugin (auto-respawn pattern)
│   │
│   ├── spawn/                    # Process-launching backends + adapters
│   │   ├── __init__.py           # `get_backend(name)` factory + `register_backend`
│   │   ├── base.py               # SpawnBackend ABC
│   │   ├── tmux_backend.py       # TmuxBackend + hardened injection helpers (pane_safe_to_inject,
│   │   │                         #   uuid paste-buffer names, _run_tmux return-code wrapper,
│   │   │                         #   pane_id-based runtime injection)
│   │   ├── subprocess_backend.py # SubprocessBackend — fire-and-forget Popen + on-exit hook
│   │   ├── wsh_backend.py        # WshBackend — TideTerm/WaveTerm blocks
│   │   ├── wsh_rpc.py            # JSON-RPC client used by wsh_backend
│   │   ├── adapters.py           # NativeCliAdapter — claude/codex/gemini/kimi/qwen/opencode/openclaw/pi/nanobot detection + flags
│   │   ├── prompt.py             # build_agent_prompt
│   │   ├── presets.py            # AgentPreset operations (shared endpoints)
│   │   ├── profiles.py           # AgentProfile operations (per-CLI runtime)
│   │   ├── command_validation.py # validate_spawn_command + normalize_spawn_command
│   │   ├── cli_env.py            # build_spawn_path, resolve_clawteam_executable
│   │   ├── registry.py           # spawn_registry.json — register_agent / is_agent_alive / list_dead_agents / list_zombie_agents / stop_agent (tier-3 liveness)
│   │   └── sessions.py           # SessionStore — persist/resume per-agent session state
│   │
│   ├── store/
│   │   ├── __init__.py           # `get_task_store(team_name, backend)` factory
│   │   ├── base.py               # BaseTaskStore ABC + TaskLockError
│   │   └── file.py               # FileTaskStore — fcntl/msvcrt-locked JSON-per-task store
│   │
│   ├── team/                     # Domain layer — teams, mailboxes, tasks, plans, lifecycle
│   │   ├── __init__.py           # Re-exports + lazy `TaskStore`
│   │   ├── manager.py            # TeamManager — create / discover / add_member / cleanup / inbox name resolution
│   │   ├── models.py             # TeamMember / TeamConfig / TeamMessage / TaskItem + enums + get_data_dir()
│   │   ├── tasks.py              # Compatibility shim → store.file.FileTaskStore
│   │   ├── mailbox.py            # MailboxManager — send / broadcast / peek / receive + event-log mirroring
│   │   ├── plan.py               # PlanManager — submit / approve / reject
│   │   ├── lifecycle.py          # LifecycleManager — shutdown protocol + idle notification
│   │   ├── snapshot.py           # Save/restore team configuration snapshots
│   │   ├── waiter.py             # Block until task condition (used by `task wait`)
│   │   ├── watcher.py            # InboxWatcher — `inbox watch` / `runtime watch` polling loop
│   │   ├── router.py             # RuntimeRouter — message → envelope → dispatch
│   │   ├── routing_policy.py     # DefaultRoutingPolicy + RuntimeEnvelope + RouteDecision
│   │   └── costs.py              # CostStore — per-event cost ledger + budget summary
│   │
│   ├── transport/
│   │   ├── __init__.py           # `get_transport(name, team_name, **kwargs)` factory
│   │   ├── base.py               # Transport ABC
│   │   ├── claimed.py            # ClaimedMessage — at-least-once ack/quarantine wrapper
│   │   ├── file.py               # FileTransport — inbox-dir backend (default)
│   │   └── p2p.py                # P2PTransport — pyzmq PUSH/PULL with file fallback
│   │
│   ├── workspace/                # Git worktree isolation per agent
│   │   ├── __init__.py           # `get_workspace_manager(repo_path)` helper
│   │   ├── manager.py            # WorkspaceManager — create / checkpoint / merge / cleanup
│   │   ├── git.py                # Thin wrappers over `git worktree`, `git diff`, etc.
│   │   ├── models.py             # WorkspaceInfo, WorkspaceRegistry
│   │   ├── conflicts.py          # detect_overlaps — file-level conflict summary
│   │   └── context.py            # Diff/log/file-ownership helpers behind `clawteam context`
│   │
│   └── templates/                # Built-in TOML team blueprints used by `clawteam launch`
│       ├── __init__.py
│       ├── code-review.toml
│       ├── harness-default.toml
│       ├── hedge-fund.toml
│       ├── research-paper.toml
│       ├── software-dev.toml
│       └── strategy-room.toml
│
├── scripts/                      # Repo-level shell helpers
│   └── openclaw_worker.sh
│
├── tests/                        # pytest suite — one test module per source module
│   ├── conftest.py
│   ├── __init__.py
│   ├── board/
│   │   └── test_liveness.py
│   ├── test_adapters.py
│   ├── test_board.py
│   ├── test_cli_commands.py
│   ├── test_config.py
│   ├── test_context.py
│   ├── test_costs.py
│   ├── test_data_dir.py
│   ├── test_event_bus.py
│   ├── test_fileutil.py
│   ├── test_gource.py
│   ├── test_harness.py
│   ├── test_identity.py
│   ├── test_inbox_routing.py
│   ├── test_lifecycle.py
│   ├── test_mailbox.py
│   ├── test_manager.py
│   ├── test_mcp_server.py
│   ├── test_mcp_tools.py
│   ├── test_models.py
│   ├── test_plan_storage.py
│   ├── test_presets.py
│   ├── test_profiles.py
│   ├── test_prompt.py
│   ├── test_registry.py
│   ├── test_runtime_routing.py
│   ├── test_snapshots.py
│   ├── test_spawn_backends.py
│   ├── test_spawn_cli.py
│   ├── test_store.py
│   ├── test_tasks.py
│   ├── test_task_store_locking.py
│   ├── test_templates.py
│   ├── test_timefmt.py
│   ├── test_tmux_injection.py
│   ├── test_waiter.py
│   ├── test_workspace_manager.py
│   └── test_wsh_backend.py
│
├── skills/                       # Repo-tracked Claude / Agent skill bundle
│   ├── skills-lock.json
│   └── clawteam/
│       ├── SKILL.md
│       ├── agents/openai.yaml
│       └── references/
│           ├── cli-reference.md
│           └── workflows.md
│
├── .claude/skills/               # Project-local skills consumed by Claude Code
│   ├── clawteam-dev/
│   │   ├── SKILL.md              # Dev bootstrap + smoke-test recipes
│   │   └── scripts/
│   │       ├── bootstrap_clawteam_dev.sh
│   │       └── link_local_clawteam_skills.sh
│   └── frontend-design/
│       ├── SKILL.md
│       └── LICENSE.txt
│
├── .agents/skills/               # Mirror of .claude/skills/ for non-Claude agents
│   ├── clawteam-dev/...
│   └── frontend-design/...
│
├── .clawteam/                    # Project-local data dir (picked up by get_data_dir() walk-up)
│   ├── teams/
│   │   ├── board-test/{config.json, events/, inboxes/{leader,reviewer1,worker1}/}
│   │   └── verify-test/{config.json, events/, inboxes/leader/}
│   ├── tasks/{board-test/, verify-test/}
│   ├── costs/{board-test/, verify-test/}
│   └── workspaces/
│
├── docs/                         # Public docs site (GitHub Pages)
│   ├── index.html / .nojekyll / CNAME
│   ├── board-usage.md
│   ├── transport-architecture.md
│   ├── site-assets/
│   ├── skills/clawteam/{SKILL.md, references/}
│   └── superpowers/{plans/, specs/}
│
├── website/                      # Vite landing-page source (separate from board frontend)
│   ├── index.html
│   ├── vite.config.mjs
│   └── src/{App.jsx, main.jsx, styles.css}
│
├── assets/                       # Static images referenced by README / docs
│
├── .planning/codebase/           # GSD codebase mapping output (this folder)
│
├── .github/workflows/ci.yml      # CI: ruff + pytest
└── .playwright-mcp/              # Captured screenshots from Playwright MCP runs
```

## Directory Purposes

**`clawteam/` (top-level Python package):**
- Purpose: Everything imported by the `clawteam` and `clawteam-mcp` console scripts.
- Contains: One subpackage per major concern (cli, mcp, board, events, harness, plugins, spawn, store, team, transport, workspace, templates).
- Key files: `clawteam/__main__.py`, `clawteam/config.py`, `clawteam/identity.py`, `clawteam/paths.py`.

**`clawteam/cli/`:**
- Purpose: All Typer-based command-line entry points.
- Contains: A single `commands.py` (large by design) that defines `app` and ~20 sub-Typer apps (`config`, `preset`, `profile`, `team`, `inbox`, `runtime`, `task`, `cost`, `session`, `plan`, `lifecycle`, `identity`, `board`, `workspace`, `context`, `template`, `hook`, `plugin`, `harness`).

**`clawteam/mcp/`:**
- Purpose: FastMCP server adapter so any MCP-compatible host can drive ClawTeam.
- Contains: `server.py` (registers each callable from `TOOL_FUNCTIONS`), `helpers.py` (error translation, payload coercion, common require_team), `tools/` (one module per domain).

**`clawteam/board/`:**
- Purpose: Read/write dashboard for the local data dir.
- Contains: `server.py` (HTTP+SSE+proxy), `collector.py` (JSON snapshot), `liveness.py` (tmux window probe), `renderer.py` (terminal renderer), `gource.py` (visualization), pre-built `static/` for serving, and `frontend/` source.

**`clawteam/board/frontend/`:**
- Purpose: React 19 + Vite 6 + Tailwind v4 + shadcn (Radix-based) SPA.
- Contains: `vite.config.ts` (build output goes to `../static`), `src/App.tsx` shell, the `useTeamStream` SSE hook, four modal dialogs, kanban subcomponents, and a `ui/` folder with shadcn primitives.

**`clawteam/events/`:**
- Purpose: Process-local pub/sub spine.
- Contains: `bus.py` (`EventBus`), `global_bus.py` (singleton + auto hook load), `hooks.py` (shell+python hook handlers), `types.py` (all event dataclasses).

**`clawteam/harness/`:**
- Purpose: Plan-then-execute orchestration around the team layer.
- Contains: `phases.py` (state machine), `orchestrator.py` (high-level control), `conductor.py` (foreground polling loop), `spawner.py` / `roles.py` / `strategies.py` / `prompts.py`, contracts + artifacts + exit-journal helpers, plugin `context.py`.

**`clawteam/plugins/`:**
- Purpose: Plugin extension surface.
- Contains: `base.py` (`HarnessPlugin` ABC), `manager.py` (`PluginManager` discovery + load), `ralph_loop_plugin.py` (reference implementation).

**`clawteam/spawn/`:**
- Purpose: Run agent processes and keep track of them.
- Contains: Three backends (`tmux_backend.py`, `subprocess_backend.py`, `wsh_backend.py`), CLI adapter logic (`adapters.py`), prompt builder, presets/profiles, command validation, environment + executable resolution helpers, spawn registry (durable JSON), session store.

**`clawteam/store/`:**
- Purpose: Pluggable task storage.
- Contains: `base.py` (interface + `TaskLockError`) and `file.py` (default JSON-per-task implementation).

**`clawteam/team/`:**
- Purpose: Domain layer (the things humans say "teams" and "tasks" about).
- Contains: Pydantic models, manager (CRUD + cleanup), mailbox (send/broadcast/receive + event log), plan / lifecycle / costs / waiter / snapshot, runtime router + policy, inbox watcher.

**`clawteam/transport/`:**
- Purpose: Pluggable message-bytes movement.
- Contains: ABC + `claimed.py` (ack/quarantine), `file.py` default, `p2p.py` (pyzmq, optional extra).

**`clawteam/workspace/`:**
- Purpose: Per-agent git worktree management for isolated parallel edits.
- Contains: `manager.py` (worktree lifecycle), `git.py` (subprocess wrappers), `models.py`, `conflicts.py` (cross-agent file overlap detection), `context.py` (diff / log / blame helpers exposed under `clawteam context`).

**`clawteam/templates/`:**
- Purpose: TOML team blueprints used by `clawteam launch`.
- Contains: One `*.toml` per archetype (software-dev, code-review, hedge-fund, research-paper, strategy-room, harness-default).

**`tests/`:**
- Purpose: pytest suite. Naming convention: `test_<module>.py` mirrors `clawteam/<module>.py`.
- Contains: Unit tests for every subsystem; `tests/board/` mirrors `clawteam/board/`. Includes `test_tmux_injection.py` covering the hardened injection paths and `test_data_dir.py` covering the project-local walk-up.

**`scripts/`:**
- Purpose: Repo-level shell utilities outside the Python package.
- Contains: `openclaw_worker.sh`.

**`skills/clawteam/` and `.claude/skills/`, `.agents/skills/`:**
- Purpose: Skill bundles consumed by Claude Code / generic agents working inside this repo.
- Contains: `SKILL.md` plus references and bootstrap scripts (`bootstrap_clawteam_dev.sh`, `link_local_clawteam_skills.sh`).

**`docs/` and `website/`:**
- Purpose: Public-facing GitHub Pages site (`docs/`) and a separate Vite landing page source (`website/`). Distinct from the board UI under `clawteam/board/frontend/`.

**`.clawteam/`:**
- Purpose: Project-local data dir captured by `get_data_dir()`'s walk-up. Generated by running `clawteam` commands inside this repo.
- Generated: Yes (by CLI usage).
- Committed: Currently tracked, contains transient test team state. Treat as scratch.

**`.planning/codebase/`:**
- Purpose: GSD-generated codebase analysis documents (this directory).
- Contains: ARCHITECTURE.md, STRUCTURE.md (and any future maps). Do not place runtime code here.

## Key File Locations

**Entry points:**
- `clawteam/cli/commands.py` — `app = typer.Typer(...)` plus every subcommand. `pyproject.toml` registers it as the `clawteam` console script.
- `clawteam/__main__.py` — `python -m clawteam` shim that re-exports `app`.
- `clawteam/mcp/server.py` — `main()` registered as the `clawteam-mcp` console script; also `python -m clawteam.mcp` via `clawteam/mcp/__main__.py`.
- `clawteam/board/server.py` — `serve(host, port, default_team, interval)` invoked by `clawteam board serve`.

**Configuration:**
- `pyproject.toml` — package metadata, dependencies, console scripts, ruff and pytest settings.
- `clawteam/config.py` — `ClawTeamConfig` Pydantic model + `~/.clawteam/config.json` reader/writer.
- `~/.clawteam/config.json` — user-level config (NOT affected by `data_dir` overrides).
- `clawteam/board/frontend/vite.config.ts` — frontend build/dev config (build outDir = `../static`, dev `/api` proxy → `:8080`).
- `clawteam/board/frontend/components.json` — shadcn component config.
- `.github/workflows/ci.yml` — ruff + pytest CI pipeline.

**Core logic:**
- `clawteam/team/models.py` — `TeamConfig`, `TeamMember`, `TeamMessage`, `TaskItem`, all enums, `get_data_dir()` (project-local walk-up).
- `clawteam/team/manager.py` — TeamManager CRUD façade.
- `clawteam/team/mailbox.py` — `MailboxManager.send / broadcast / receive`.
- `clawteam/store/file.py` — locked, atomic per-task JSON store.
- `clawteam/spawn/tmux_backend.py` — primary spawn backend; contains the hardened tmux injection helpers (`_pane_safe_to_inject`, `_inject_prompt_via_buffer`, `_run_tmux`, `inject_runtime_message`).
- `clawteam/spawn/registry.py` — durable per-team `spawn_registry.json` (tier-3 liveness).
- `clawteam/board/collector.py` — produces the JSON consumed by the dashboard SSE stream.
- `clawteam/board/liveness.py` — tier-2 liveness (`agents_online`).
- `clawteam/board/frontend/src/hooks/use-team-stream.ts` — tier-1 liveness via `EventSource`.
- `clawteam/team/router.py` + `clawteam/team/routing_policy.py` — runtime injection routing.
- `clawteam/harness/orchestrator.py` + `clawteam/harness/phases.py` — phase state machine and gates.
- `clawteam/events/bus.py` + `clawteam/events/global_bus.py` — event spine.
- `clawteam/workspace/manager.py` — git worktree manager.

**Testing:**
- `tests/conftest.py` — shared pytest fixtures.
- `tests/test_tmux_injection.py` — covers `_pane_safe_to_inject`, paste-buffer uniqueness, return-code wrapper.
- `tests/test_data_dir.py` — covers project-local walk-up.
- `tests/test_runtime_routing.py` — covers `RuntimeRouter` + `DefaultRoutingPolicy`.
- `tests/test_mcp_server.py`, `tests/test_mcp_tools.py` — FastMCP wiring.

## Naming Conventions

**Files:**
- Python: `snake_case.py` (one module per concern). The only deliberately giant file is `clawteam/cli/commands.py` (Typer subcommand registry).
- TypeScript / React: `kebab-case.tsx` for components and hooks (`use-team-stream.ts`, `agent-registry.tsx`, `task-card.tsx`).
- shadcn UI primitives: lowercase singular (`button.tsx`, `dialog.tsx`).
- Tests mirror source: `clawteam/team/manager.py` → `tests/test_manager.py`, `clawteam/board/liveness.py` → `tests/board/test_liveness.py`.

**Directories:**
- Python subpackages: `snake_case`. Names are concise nouns (`spawn`, `store`, `team`, `transport`, `workspace`, `harness`).
- Frontend: `kebab-case` and topical (`kanban/`, `modals/`, `ui/`, `hooks/`, `lib/`).

**Identifiers used as filesystem path segments (team names, agent names, user names):**
- Must match `^[A-Za-z0-9._-]+$` (`clawteam/paths.py:_IDENTIFIER_RE`). Anything else raises `ValueError` from `validate_identifier`.

**Tmux session naming:**
- `clawteam-{team}` (`TmuxBackend.session_name`). Each agent gets a window named after the member.

**Branch naming for workspaces:**
- `clawteam/{team_name}/{agent_name}` (`clawteam/workspace/manager.py:73`).

**Inbox naming:**
- `{user}_{name}` when `user` is set on the member, else `{name}` (`TeamManager.inbox_name_for`).

## Where to Add New Code

**A new CLI command:**
- Decide which sub-app it belongs to. Existing sub-apps live in `clawteam/cli/commands.py` and are declared with `app.add_typer(<name>_app, name="...")` blocks.
- Add an `@<subapp>.command("...")` function near sibling commands (search for the existing sub-app's first command).
- Update `tests/test_cli_commands.py`. Use the Typer `CliRunner` pattern already established there.
- If the command needs domain logic, put the logic on the relevant manager (`TeamManager`, `MailboxManager`, `WorkspaceManager`, etc.) and keep the CLI handler thin.

**A new MCP tool:**
- Implement the callable in the appropriate `clawteam/mcp/tools/<domain>.py` (or create a new module if the domain is new). Use `helpers.require_team`, `helpers.task_store`, `helpers.team_mailbox`, and `helpers.to_payload` for boilerplate.
- Add the function to `TOOL_FUNCTIONS` in `clawteam/mcp/tools/__init__.py`.
- Add a test in `tests/test_mcp_tools.py` (and `tests/test_mcp_server.py` if you want to verify the FastMCP registration).

**A new spawn backend:**
- Add `clawteam/spawn/<name>_backend.py` implementing `SpawnBackend`.
- Wire it into `clawteam/spawn/__init__.py:get_backend`.
- If it should support runtime injection, add `inject_runtime_message(self, team, agent_name, envelope) -> tuple[bool, str]` (see `TmuxBackend.inject_runtime_message`).
- Always call `clawteam.spawn.registry.register_agent` after a successful spawn; emit `AfterWorkerSpawn` on the global bus.
- Add a test in `tests/test_spawn_backends.py` (or a sibling file mirroring the existing `test_wsh_backend.py`).

**A new transport:**
- Add `clawteam/transport/<name>.py` implementing `Transport`.
- Wire it in `clawteam/transport/__init__.py:get_transport`.
- If you need at-least-once delivery, expose a `claim_messages(agent_name, limit) -> list[ClaimedMessage]` method (see `clawteam/transport/file.py`).

**A new task store backend:**
- Add `clawteam/store/<backend>.py` implementing `BaseTaskStore`. Own your concurrency (locks, transactions).
- Wire it through `clawteam/store/__init__.py:get_task_store`.
- Re-export under `clawteam/team/tasks.py` if you need backwards-compat.

**A new harness phase or gate:**
- Add a `Phase` constant (`clawteam/harness/phases.py`) and (if relevant) a `PhaseGate` subclass.
- Register the gate in `HarnessOrchestrator.__init__` (`clawteam/harness/orchestrator.py`) or via a plugin's `contribute_gates()`.

**A new event type:**
- Add a `@dataclass` in `clawteam/events/types.py` inheriting `HarnessEvent`.
- Re-export from `clawteam/events/__init__.py` if it should be discoverable.
- Plugin-provided event types must call `clawteam.events.bus.register_event_type(cls)` so shell hooks can reference them by name.

**A new plugin:**
- Create a module that defines a `HarnessPlugin` subclass (see `clawteam/plugins/ralph_loop_plugin.py`).
- Distribute via a `clawteam.plugins` entry point, or list its dotted module path in `ClawTeamConfig.plugins`, or drop it under `{data_dir}/plugins/<name>/` with a `plugin.json`.

**A new dashboard panel / dialog:**
- Frontend source: add components under `clawteam/board/frontend/src/components/` (use `kebab-case.tsx`). Reuse primitives from `components/ui/`.
- Hooks live under `src/hooks/`; API calls live in `src/lib/api.ts`.
- Backend support: extend `BoardCollector.collect_team` if you need new fields in the SSE payload, or add a new endpoint in `BoardHandler.do_GET / do_POST / do_PATCH`.
- After changes: rebuild the frontend (`npm run build` from `clawteam/board/frontend/`) so `clawteam/board/static/` reflects the new bundle.

**A new built-in team template:**
- Drop a `<archetype>.toml` under `clawteam/templates/` (mirror `software-dev.toml`'s shape). Add a fixture-based test in `tests/test_templates.py`.

**Tests:**
- One `tests/test_<module>.py` per source module — mirror the package layout. Place board-frontend-specific Python tests under `tests/board/`.

## Special Directories

**`clawteam/board/static/`:**
- Purpose: Pre-built Vite output (HTML + hashed assets) bundled into the wheel and served at runtime.
- Generated: Yes — output of `npm run build` from `clawteam/board/frontend/`.
- Committed: Yes — keeps the package self-contained so end users do not need Node to run `clawteam board serve`.

**`.clawteam/`:**
- Purpose: Project-local data dir (target of the `get_data_dir()` walk-up when running CLI commands inside this repo).
- Generated: Yes — by CLI runs inside the repo.
- Committed: Currently tracked (smoke-test residue); treat its contents as ephemeral.

**`.playwright-mcp/`:**
- Purpose: Screenshots captured by Playwright MCP runs while exercising the dashboard.
- Generated: Yes.
- Committed: Yes (visual regression record).

**`.venv/`:**
- Purpose: Local uv-managed virtualenv.
- Generated: Yes.
- Committed: No (in `.gitignore`).

**`.planning/codebase/`:**
- Purpose: GSD codebase mapping output (the documents you are reading).
- Generated: Yes — by `/gsd-map-codebase` runs.
- Committed: Yes.

---

*Structure analysis: 2026-04-28*
