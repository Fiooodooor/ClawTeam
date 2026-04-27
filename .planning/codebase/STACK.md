# Technology Stack

**Analysis Date:** 2026-04-15

## Languages

**Primary:**
- Python 3.10+ (supports 3.10, 3.11, 3.12) — the entire backend, CLI, MCP server, spawn system, event bus, and HTTP dashboard. Declared in `pyproject.toml:6,15-18`.
- TypeScript ~5.8 — the board dashboard UI (React). Configured via `clawteam/board/frontend/tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json`.

**Secondary:**
- Bash — `scripts/plane-docker-setup.sh`, `scripts/openclaw_worker.sh`.
- TOML — preset/team templates in `clawteam/templates/*.toml` (e.g. `harness-default.toml`, `software-dev.toml`).

## Runtime

**Environment:**
- CPython 3.10+ for the backend process (`requires-python = ">=3.10"` in `pyproject.toml:6`).
- Node.js (via Vite dev server) for frontend development; the built bundle is static and served by the Python stdlib HTTP server at runtime.
- `tmux` — required on host for the default spawn backend. Detected with `shutil.which("tmux")` in `clawteam/spawn/tmux_backend.py:56`.

**Package Managers:**
- Python: `uv` is used locally (`uv.lock` present, ~186 KB). `pip install -e ".[dev]"` is the CI path per `.github/workflows/ci.yml:31`. Build backend is Hatchling (`pyproject.toml:51-56`).
- Frontend: `npm` for `clawteam/board/frontend/` (`package-lock.json`). A separate top-level `package.json` exists for the `website/` (not the app).

## Frameworks

**Backend core:**
- **Typer** `>=0.12,<1.0` — CLI framework. The root `app = typer.Typer(...)` lives at `clawteam/cli/commands.py:22-26`; every subcommand (`team`, `spawn`, `task`, `inbox`, `board`, `plane`, etc.) is registered on it. Entry point: `clawteam = "clawteam.cli.commands:app"` (`pyproject.toml:43`).
- **Pydantic v2** `>=2.0,<3.0` — all data models. Used for team/task models (`clawteam/team/models.py`), config (`clawteam/config.py`), Plane models (`clawteam/plane/models.py`), events, and MCP tool I/O.
- **Python stdlib `http.server`** (`ThreadingHTTPServer` + `BaseHTTPRequestHandler`) — board dashboard HTTP/SSE server. No Flask, FastAPI, or Starlette. See `clawteam/board/server.py:12,120,367`. Webhook receiver (`clawteam/plane/webhook.py:9`) uses the same stdlib primitives.
- **MCP** `>=1.0` — the official Model Context Protocol Python SDK. `FastMCP("clawteam")` registers tools in `clawteam/mcp/server.py:8-13,28-29`. Entry point: `clawteam-mcp = "clawteam.mcp.server:main"` (`pyproject.toml:44`).

**Backend UI/display:**
- **Rich** `>=13,<15` — terminal rendering (tables, colors) in `clawteam/cli/commands.py` and `clawteam/board/renderer.py`.
- **Questionary** `>=2.0.1,<3.0` — interactive CLI prompts (`clawteam/cli/commands.py`).

**Testing:**
- **pytest** `>=9.0,<10.0` (dev extra). Config in `pyproject.toml:73-74` (`testpaths = ["tests"]`). Shared fixture `isolated_data_dir` in `tests/conftest.py:10-19` redirects `CLAWTEAM_DATA_DIR` and `HOME` to `tmp_path` so tests never touch the real `~/.clawteam/`.
- 30+ test modules under `tests/` covering CLI, MCP tools, Plane, event bus, mailbox, workspace, etc.

**Linting:**
- **Ruff** `>=0.1` (dev extra). Config in `pyproject.toml:65-71`: line length 100, targets `py310`, rules `E,F,I,N,W` (E501 ignored). CI runs `ruff check clawteam/ tests/` (`.github/workflows/ci.yml:10-18`).

**Frontend core (`clawteam/board/frontend/package.json`):**
- **React 19.1** + **React DOM 19.1** — UI runtime.
- **Vite 6.3** with `@vitejs/plugin-react` — dev server and build tool. Config: `clawteam/board/frontend/vite.config.ts`. Builds into `../static` (consumed by the Python HTTP server). Dev-mode proxy: `/api → http://localhost:8080`.
- **Tailwind CSS 4.1** via `@tailwindcss/vite` plugin — no separate `tailwind.config.*` file; Tailwind v4 is configured through `src/index.css` using `@import "tailwindcss"` and CSS variables (OKLCH-based theme tokens at `clawteam/board/frontend/src/index.css:1-30`).
- **shadcn** (style: `base-nova`, base color `neutral`, icon library `lucide`) — configured in `clawteam/board/frontend/components.json`. Generated primitives live in `src/components/ui/`: `badge`, `button`, `card`, `dialog`, `input`, `label`, `scroll-area`, `select`, `sheet`, `textarea`.
- **@base-ui/react** `^1.4.0` — unstyled headless primitives that shadcn composes over.
- **@dnd-kit/react** `^0.4.0` — drag-and-drop for kanban. `DragDropProvider` + `isSortable` at `clawteam/board/frontend/src/components/kanban/board.tsx:1-40`; used in `column.tsx` and `task-card.tsx`.
- **lucide-react**, **clsx**, **tailwind-merge**, **class-variance-authority**, **tw-animate-css** — styling/utility trio standard to shadcn.

## Key Dependencies

**Python critical (`pyproject.toml:21-40`):**
- `typer>=0.12,<1.0` — CLI surface.
- `pydantic>=2.0,<3.0` — all typed models.
- `mcp>=1.0` — MCP server runtime for `clawteam-mcp`.
- `rich>=13,<15` — terminal output (tables, panels).
- `questionary>=2.0.1,<3.0` — interactive wizards.
- `tomli>=2.0; python_version < '3.11'` — TOML reading shim for Python 3.10.

**Python optional extras:**
- `[dev]`: `pytest>=9.0,<10.0`, `ruff>=0.1`.
- `[p2p]`: `pyzmq>=25,<27` — enables the ZeroMQ transport (`clawteam/transport/p2p.py`); off by default (file transport is the built-in).
- `[plane]`: `httpx>=0.27,<1.0` — needed only when Plane integration is active (`clawteam/plane/client.py:7`).

**Frontend critical (`clawteam/board/frontend/package.json`):**
- `react@^19.1.0`, `react-dom@^19.1.0`.
- `vite@^6.3.0` + `@vitejs/plugin-react@^4.4.0`.
- `tailwindcss@^4.1.0` + `@tailwindcss/vite@^4.1.0`.
- `@base-ui/react@^1.4.0` (shadcn base layer).
- `@dnd-kit/react@^0.4.0` (kanban DnD).
- `typescript@~5.8.0`.

## Configuration

**Runtime config file:**
- `~/.clawteam/config.json` — persistent user config. Loaded and validated via `ClawTeamConfig` Pydantic model (`clawteam/config.py:51-75,83-97`). Path is fixed and independent of `data_dir` (`clawteam/config.py:78-80`).
- Contains: `data_dir`, `user`, `default_team`, `default_profile`, `transport`, `task_store`, `workspace`, `default_backend`, `skip_permissions`, `timezone`, `gource_*`, `spawn_*`, agent `profiles`, agent `presets`, `hooks`, `plugins`, and a nested `plane: PlaneConfig`.

**Data directory (`.clawteam/`):**
- Resolution order in `clawteam/team/models.py:15-36`: (1) `$CLAWTEAM_DATA_DIR`, (2) `data_dir` in user config, (3) nearest `.clawteam/` walking up from cwd (git-style project-local discovery), (4) `~/.clawteam/` fallback.
- Structure: `teams/`, `tasks/`, `workspaces/`, `costs/`, and (when enabled) `plane-config.json`. Observed live in `/home/jac/repos/ClawTeam/.clawteam/`.

**Plane integration config:**
- `<data_dir>/plane-config.json` — loaded via `PlaneConfig` model (`clawteam/plane/config.py:13-48`). Separate file so secrets stay out of the global config.

**Environment variables** (full map in `clawteam/config.py:100-136`):
- `CLAWTEAM_DATA_DIR`, `CLAWTEAM_USER`, `CLAWTEAM_TEAM_NAME`, `CLAWTEAM_DEFAULT_PROFILE`, `CLAWTEAM_TRANSPORT`, `CLAWTEAM_TASK_STORE`, `CLAWTEAM_WORKSPACE`, `CLAWTEAM_DEFAULT_BACKEND`, `CLAWTEAM_SKIP_PERMISSIONS`, `CLAWTEAM_TIMEZONE`, `CLAWTEAM_GOURCE_*`, `CLAWTEAM_SPAWN_*`.
- Agent-scoped (injected by spawn backends into every spawned window, `clawteam/spawn/tmux_backend.py:67-77`): `CLAWTEAM_AGENT_ID`, `CLAWTEAM_AGENT_NAME`, `CLAWTEAM_AGENT_TYPE`, `CLAWTEAM_TEAM_NAME`, `CLAWTEAM_AGENT_LEADER`, `CLAWTEAM_WORKSPACE_DIR`, `CLAWTEAM_CONTEXT_ENABLED`, `CLAWTEAM_BIN`.

**Build config:**
- `pyproject.toml` — project metadata, deps, ruff, pytest, hatchling build.
- `clawteam/board/frontend/vite.config.ts` — Vite + React + Tailwind plugins, `@/` alias, output to `../static`, dev proxy.
- `clawteam/board/frontend/components.json` — shadcn registry config.
- `clawteam/board/frontend/tsconfig*.json` — TS project references.

**File-based stores** (all JSON on disk, atomic writes via `fileutil.atomic_write_text`, `fcntl`/`msvcrt` cross-platform locking):
- Tasks: `<data_dir>/tasks/<team>/task-<id>.json` (`clawteam/store/file.py:24-38`).
- Teams: `<data_dir>/teams/<team>/` with `config.json`, `spawn_registry.json`, `inboxes/<agent>/`.
- Mailbox: `<data_dir>/teams/<team>/inboxes/<agent>/msg-<ts>-<uuid>.json` (`clawteam/team/mailbox.py:1-40`).
- Costs: `<data_dir>/costs/`.
- Events: in-process pub/sub only (see `INTEGRATIONS.md` → Event bus).

## Platform Requirements

**Development:**
- Linux or macOS (CI matrix: `ubuntu-latest`, `macos-latest` × Python 3.10/3.11/3.12 per `.github/workflows/ci.yml:22-25`).
- Windows is partially supported in transports (`msvcrt` locking at `clawteam/store/file.py:14-17`, `clawteam/transport/file.py:7-16`) but `tmux` is POSIX-only, so the default spawn backend won't work on native Windows.
- Required tooling: `tmux` (agent spawning), Python 3.10+, optionally Node 20+ for frontend dev, optionally `gource` binary for visualization (`clawteam/board/gource.py`), optionally Docker (only for Plane self-hosted — see `INTEGRATIONS.md`).

**Production:**
- Distributed as a Python package (`hatchling` wheels and sdists, `pyproject.toml:55-63`) installed with `pip install clawteam` or `uv pip install`.
- Two console entry points: `clawteam` (the CLI) and `clawteam-mcp` (the MCP server over stdio).
- Runs entirely on the user's workstation; there is no hosted service. The board HTTP server binds to `127.0.0.1:8080` by default (`clawteam/board/server.py:354-359`).

---

*Stack analysis: 2026-04-15*
*Update after major dependency changes*
