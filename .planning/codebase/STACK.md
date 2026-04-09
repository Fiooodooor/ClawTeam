# Technology Stack

**Analysis Date:** 2026-04-28

This stack covers the post-Plane-removal `board-enhancement` branch. The
`clawteam/plane/` subpackage has been deleted (commit `427475a`); the
directory exists in the working tree only as an empty `__pycache__` shell and
contributes nothing to the runtime, build, or test pipeline.

## Languages

**Primary:**
- Python 3.10+ (`pyproject.toml` line 6: `requires-python = ">=3.10"`) — entire
  CLI, MCP server, board HTTP server, spawn backends, transports.
- TypeScript 5.8.x (`clawteam/board/frontend/package.json` devDeps:
  `"typescript": "~5.8.0"`) — board dashboard SPA.

**Secondary:**
- TSX/JSX (`clawteam/board/frontend/src/**/*.tsx`) — React component layer.
- POSIX shell (`scripts/openclaw_worker.sh`) — non-interactive OpenClaw worker
  wrapper used by the spawn pipeline.
- TOML — built-in team templates (`clawteam/templates/*.toml`).

## Runtime

**Python interpreter:**
- CPython, supported matrix `3.10`, `3.11`, `3.12` (CI:
  `.github/workflows/ci.yml` lines 22–25; pyproject classifiers lines 16–18).

**Browser runtime (board dashboard):**
- Modern evergreen browsers (`tsconfig.app.json` targets `ES2020`, lib
  includes `DOM`, `DOM.Iterable`).
- Frontend served either by Vite dev server (`port 5173`, proxies `/api` to
  `http://localhost:8080`) or pre-built and served from
  `clawteam/board/static/` by the stdlib HTTP server.

**Package manager:**
- `uv` is the preferred resolver (lockfile `uv.lock` is committed and tracks
  every transitive dependency). The `.gitignore` ignores `uv.lock` at the
  repo root, but the file is force-tracked.
- pip/PyPA tooling supported via `pyproject.toml` (`build-system: hatchling`).
- Node tooling: npm — `package-lock.json` files committed at repo root (for
  `website/`) and at `clawteam/board/frontend/`.

## Frameworks

### Backend (Python)

**CLI framework:**
- `typer>=0.12,<1.0` (`pyproject.toml` line 22; resolved to `0.24.1` in
  `uv.lock`). Single root `Typer` app in `clawteam/cli/commands.py` (line 22)
  with twenty `add_typer` sub-apps: `config`, `preset`, `profile`, `team`,
  `inbox`, `runtime`, `task`, `cost`, `session`, `plan`, `lifecycle`,
  `identity`, `board`, `workspace`, `context`, `template`, `hook`, `plugin`,
  `harness`. There is no `plane` sub-app.

**Data validation:**
- `pydantic>=2.0,<3.0` (resolved 2.12.5). Used for every persisted model:
  `clawteam/team/models.py` (TeamConfig, TeamMember, TaskItem, TeamMessage),
  `clawteam/config.py` (ClawTeamConfig, AgentProfile, AgentPreset, HookDef).
  All models use `model_config = {"populate_by_name": True}` and `Field(...,
  alias="camelCase")` so JSON on disk is camelCase while Python attributes
  stay snake_case.

**Console rendering:**
- `rich>=13.0,<15.0` (resolved 14.3.3). `Console`/`Table` for human-friendly
  CLI output; `clawteam/board/renderer.py` builds the in-terminal kanban view.

**Interactive prompts:**
- `questionary>=2.0.1,<3.0` (resolved 2.1.1). Used by the profile wizard
  (`clawteam/cli/commands.py` `_load_questionary` at line 135 onward).

**MCP SDK:**
- `mcp>=1.0` (resolved 1.27.0). The FastMCP server is mounted via
  `from mcp.server.fastmcp import FastMCP` in `clawteam/mcp/server.py`
  (line 8) and exposes 26 tools registered through `clawteam/mcp/tools/__init__.py`.

**TOML parsing:**
- `tomli>=2.0; python_version<'3.11'` — fallback for Python 3.10 only;
  3.11+ uses stdlib `tomllib`. Used by `clawteam/templates/__init__.py`.

**Optional `p2p` extra:**
- `pyzmq>=25.0,<27.0` (resolved 26.4.0) — only loaded when
  `clawteam/transport/p2p.py` is exercised (it does an inline
  `import zmq` inside `_start_listener`).

### Backend embedded servers (no framework)

- Board HTTP server: stdlib only — `http.server.ThreadingHTTPServer` +
  `BaseHTTPRequestHandler` (`clawteam/board/server.py` line 12). No Flask,
  FastAPI, or Starlette. SSE is implemented manually by writing
  `text/event-stream` chunks (`_serve_sse`, line 324).
- MCP server: `FastMCP` stdio transport, started via `mcp.run()` in
  `clawteam/mcp/server.py:32`.

### Frontend (TypeScript / React)

**Core:**
- `react@^19.1.0` + `react-dom@^19.1.0` (`clawteam/board/frontend/package.json`).
  Strict mode enabled (`clawteam/board/frontend/src/main.tsx:6`).
- `@base-ui/react@^1.4.0` — headless primitive layer (Dialog, Select, Button,
  merge-props, useRender). Drives all shadcn-style UI primitives in
  `clawteam/board/frontend/src/components/ui/*.tsx`.
- shadcn CLI configuration (`clawteam/board/frontend/components.json`),
  style `base-nova`, base color `neutral`, icon library `lucide`. shadcn is a
  generator, not a runtime dep.

**Styling:**
- `tailwindcss@^4.1.0` + `@tailwindcss/vite@^4.1.0` (Tailwind v4, CSS-first
  configuration in `clawteam/board/frontend/src/index.css` via
  `@import "tailwindcss"` and `@theme inline { ... }`). No `tailwind.config.*`
  file — theme tokens are CSS variables.
- `tw-animate-css@^1.4.0` — extra animation utilities.
- `class-variance-authority@^0.7.1` + `clsx@^2.1.1` + `tailwind-merge@^3.5.0`
  — composing variant classes (see `clawteam/board/frontend/src/lib/utils.ts`
  for the `cn(...)` helper).
- `lucide-react@^1.8.0` — icon set.
- Google Fonts loaded inline in `clawteam/board/frontend/index.html` and the
  built `clawteam/board/static/index.html`: Geist, Geist Mono, Instrument
  Serif.

**Drag-and-drop:**
- `@dnd-kit/react@^0.4.0` (the new dnd-kit v0.4 React entry) — drives the
  kanban board in `clawteam/board/frontend/src/components/kanban/board.tsx`
  via `DragDropProvider` + `isSortable`.

**Build / Dev:**
- `vite@^6.3.0` with `@vitejs/plugin-react@^4.4.0` — frontend bundler.
  Output written to `../static` (`clawteam/board/frontend/vite.config.ts`
  line 14: `outDir: "../static", emptyOutDir: true`) so Python ships the
  built assets without separate packaging.
- `typescript@~5.8.0` — `tsc -b` runs as part of `npm run build`.
- Type packages: `@types/node@^22`, `@types/react@^19.1`, `@types/react-dom@^19.1`.

**Marketing site (separate, unrelated to the dashboard):**
- `clawteam-website` at repo root (`package.json`) — `react@^18.3.1`,
  `react-dom@^18.3.1`, `vite@^5.4.11`, `@vitejs/plugin-react@^4.3.4`. Built
  from `website/` with its own `vite.config.mjs`. Note the React 18 / Vite 5
  pinning differs from the React 19 / Vite 6 dashboard.

### Testing

- `pytest>=9.0,<10.0` (resolved 9.0.3). Configured in `pyproject.toml`
  `[tool.pytest.ini_options]` with `testpaths = ["tests"]`. 41 test files in
  `tests/`, none of them target Plane (no `tests/test_plane_*.py` exists).
- Optional dev extra includes `ruff>=0.1.0` (resolved 0.15.9).

### Linting

- `ruff` configured in `pyproject.toml` (`[tool.ruff]` line 62 onward):
  `line-length = 100`, `target-version = "py310"`, lint selects
  `E,F,I,N,W` and ignores `E501`. CI runs `ruff check clawteam/ tests/`
  (`.github/workflows/ci.yml:18`).

## Key Dependencies

**Critical (Python):**
- `typer` (`0.24.1`) — entry point `clawteam = clawteam.cli.commands:app`.
- `pydantic` (`2.12.5`) — every on-disk model.
- `mcp` (`1.27.0`) — FastMCP server entry point
  `clawteam-mcp = clawteam.mcp.server:main`.
- `rich` (`14.3.3`) — TTY rendering.

**Critical (Frontend):**
- `react` / `react-dom` 19 — runtime.
- `@base-ui/react` 1.4 — primitive components.
- `@dnd-kit/react` 0.4 — kanban drag-and-drop.
- `tailwindcss` 4 (+ Vite plugin) — styling.

**Infrastructure:**
- `hatchling` — build backend (`pyproject.toml` lines 48–53). Wheel includes
  the `clawteam` package only.
- `vite` — frontend build, with Python serving the resulting static files.

## Configuration

**User config file:**
- Fixed location `~/.clawteam/config.json`, never moved by `data_dir`
  overrides (`clawteam/config.py:76` `config_path()`).
- Schema = `ClawTeamConfig` Pydantic model
  (`clawteam/config.py:50`), atomically written via `atomic_write_text`.
- Effective-value resolver `get_effective(key)` (`clawteam/config.py:98`)
  consults env var → file → default in that order.

**Environment variables (publicly named, no secrets quoted):**
- `CLAWTEAM_DATA_DIR`, `CLAWTEAM_USER`, `CLAWTEAM_TEAM_NAME`,
  `CLAWTEAM_DEFAULT_PROFILE`, `CLAWTEAM_TRANSPORT`, `CLAWTEAM_TASK_STORE`,
  `CLAWTEAM_WORKSPACE`, `CLAWTEAM_DEFAULT_BACKEND`,
  `CLAWTEAM_SKIP_PERMISSIONS`, `CLAWTEAM_TIMEZONE`, `CLAWTEAM_GOURCE_PATH`,
  `CLAWTEAM_GOURCE_RESOLUTION`, `CLAWTEAM_GOURCE_SECONDS_PER_DAY`,
  `CLAWTEAM_SPAWN_PROMPT_DELAY`, `CLAWTEAM_SPAWN_READY_TIMEOUT`
  (mapping in `clawteam/config.py:103`).
- Spawn-time agent context (set by `TmuxBackend.spawn`,
  `clawteam/spawn/tmux_backend.py:69`): `CLAWTEAM_AGENT_ID`,
  `CLAWTEAM_AGENT_NAME`, `CLAWTEAM_AGENT_TYPE`, `CLAWTEAM_TEAM_NAME`,
  `CLAWTEAM_AGENT_LEADER`, `CLAWTEAM_WORKSPACE_DIR`,
  `CLAWTEAM_CONTEXT_ENABLED`, `CLAWTEAM_BIN`.

**Project-local data directory (post-`2f13883`):**
- `clawteam/team/models.py:15` `get_data_dir()` resolves in this order:
  1. `CLAWTEAM_DATA_DIR` env var.
  2. `data_dir` field in `~/.clawteam/config.json`.
  3. Nearest `.clawteam/` walking up from `cwd` (git-style discovery via
     `_find_project_data_dir()`).
  4. `~/.clawteam/`.
- The current repo already contains a project-local store at
  `.clawteam/{costs,tasks,teams,workspaces}/`.

**Frontend build:**
- `clawteam/board/frontend/vite.config.ts` — alias `@` → `./src`, dev
  proxies `/api` to `localhost:8080`, build output to `../static`.
- `clawteam/board/frontend/tsconfig.json` and `tsconfig.app.json` —
  strict, `noUncheckedIndexedAccess`, `noUnusedLocals`, `noUnusedParameters`,
  `jsx: "react-jsx"`, path alias `@/* → ./src/*`.
- `clawteam/board/frontend/components.json` — shadcn generator config.

**Project metadata:**
- `pyproject.toml` — version `0.3.0`, MIT license, alpha development
  status, two console scripts (`clawteam`, `clawteam-mcp`).

**Build configs:**
- `pyproject.toml` `[build-system]` uses Hatchling, wheel target packages
  `["clawteam"]` (line 53).
- No build script for the frontend ships with the wheel; the assumption is
  that whoever ships a binary distribution runs `npm run build` first to
  populate `clawteam/board/static/`.

## Platform Requirements

**Development:**
- Python 3.10+ with `pip` or `uv`.
- Node 20+ (Vite 6 + React 19 require modern Node) and npm if rebuilding
  the dashboard.
- External binaries (looked up via `shutil.which`, all optional but
  feature-gated):
  - `tmux` — required for the default spawn backend (`clawteam/spawn/tmux_backend.py:58`,
    `clawteam/board/liveness.py:17`).
  - `git` — required for workspace isolation (`clawteam/workspace/git.py`).
  - `gource` — optional, gates `clawteam board gource`
    (`clawteam/board/gource.py:301`).
  - `ffmpeg` — optional, only when `clawteam board gource --export` is used
    (`clawteam/board/gource.py:363`).
  - `wsh` — optional, only when the `wsh` spawn backend is selected
    (`clawteam/spawn/wsh_backend.py:193`).
  - Per-agent CLIs (`claude`, `codex`, `gemini`, `kimi`, `qwen`, `opencode`,
    `nanobot`, `openclaw`, `pi`) — required at runtime for whichever agent
    profile is being launched (detected in
    `clawteam/spawn/adapters.py:106`–`172`).
- Tested OSes per CI matrix: `ubuntu-latest` and `macos-latest`
  (`.github/workflows/ci.yml:24`). Windows has partial support: subprocess
  backend has a Win32 PID-alive branch (`clawteam/spawn/registry.py:200`)
  but tmux/wsh backends are POSIX-only.

**Production:**
- ClawTeam ships as a CLI tool, not a service — there is no production
  deploy target. Users install the wheel locally and run agents on their
  own machine.
- The board dashboard is intended to bind to `127.0.0.1` by default
  (`clawteam/cli/commands.py:3514`); it is not hardened for public exposure.

---

*Stack analysis: 2026-04-28*
