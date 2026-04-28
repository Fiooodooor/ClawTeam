# Technology Stack

**Analysis Date:** 2026-04-28

## Languages

**Primary:**
- Python 3.10+ (target 3.10/3.11/3.12) — entire backend, CLI, MCP server, transports, harness, board HTTP server, Plane integration
- TypeScript 5.8 — board frontend dashboard (`clawteam/board/frontend/src/`)

**Secondary:**
- Bash — operator scripts (`scripts/openclaw_worker.sh`, `scripts/plane-docker-setup.sh`)
- TOML — pyproject + team templates (`clawteam/templates/*.toml`)
- HTML/CSS — built dashboard shell (`clawteam/board/static/index.html`) and marketing site (`website/`)

## Runtime

**Environment:**
- CPython 3.10 / 3.11 / 3.12 (declared in `pyproject.toml`, verified in `.github/workflows/ci.yml` matrix)
- Node 18+ (Vite 6 + TypeScript 5.8 toolchain in `clawteam/board/frontend/package.json`; root `website/` Vite 5 build also requires Node)

**Package Manager:**
- Python: `uv` (lockfile `uv.lock` checked in, also installable via `pip install -e .`)
- Frontend (board): `npm` — `clawteam/board/frontend/package-lock.json`
- Marketing site: `npm` — `package-lock.json` at repo root

## Frameworks

**Core (Python backend):**
- `typer >=0.12,<1.0` — CLI surface (`clawteam/cli/commands.py`, ~4800 lines, ~30 sub-Typer apps)
- `pydantic >=2.0,<3.0` — every data model (`clawteam/team/models.py`, `clawteam/plane/models.py`, `clawteam/plane/config.py`)
- `rich >=13.0,<15.0` — terminal output (Console / Table imports throughout `commands.py`)
- `questionary >=2.0.1,<3.0` — interactive wizards (`profile_wizard` in `commands.py:795+`)
- `mcp >=1.0` — Model Context Protocol; ClawTeam exposes a `FastMCP` server (`clawteam/mcp/server.py`, tools in `clawteam/mcp/tools/`)
- `tomli >=2.0` — TOML parsing on Python <3.11 (templates)

**HTTP server:**
- `http.server.ThreadingHTTPServer` (stdlib only) — board dashboard at `clawteam/board/server.py:367`; Plane HITL webhook receiver at `clawteam/plane/webhook.py:215`. Intentionally framework-free to keep core install dependency-light.

**Frontend (board dashboard — `clawteam/board/frontend/`):**
- React 19.1 + ReactDOM 19.1 — root mount in `src/main.tsx:6`
- Vite 6.3 — dev server + bundler (`vite.config.ts`); proxies `/api` → `http://localhost:8080`; build output goes to `../static/` consumed by the Python server
- TypeScript 5.8 — strict, compiled via `tsc -b` before `vite build`
- Tailwind CSS 4.1 (via `@tailwindcss/vite`) — theme tokens defined as OKLCH CSS variables in `src/index.css`
- shadcn/ui — `style: "base-nova"`, alias `@/components/ui` (`components.json`); generated primitives live under `src/components/ui/` (badge, button, card, dialog, input, label, scroll-area, select, sheet, textarea)
- `@base-ui/react ^1.4` — headless primitive library backing the shadcn components (e.g. `Dialog as DialogPrimitive` from `@base-ui/react/dialog` in `src/components/ui/dialog.tsx:4`)
- `@dnd-kit/react ^0.4` + `@dnd-kit/react/sortable` — kanban drag-and-drop (`src/components/kanban/board.tsx:1`)
- `lucide-react ^1.8` — icon set (declared `iconLibrary: "lucide"` in `components.json`)
- `class-variance-authority ^0.7`, `clsx ^2.1`, `tailwind-merge ^3.5` — `cn()` utility in `src/lib/utils.ts`
- `tw-animate-css ^1.4` — Tailwind animation utilities used by dialog/sheet primitives

**Frontend (marketing — `website/`):**
- React 18.3, ReactDOM 18.3, Vite 5.4, `@vitejs/plugin-react` 4.3 (root `package.json`). Separate from the board app and pinned to React 18.

**Real-time transport (browser ↔ board):**
- Server-Sent Events (`text/event-stream`) — produced by `BoardHandler._serve_sse` (`clawteam/board/server.py:324`), consumed by `useTeamStream` via `EventSource` (`src/hooks/use-team-stream.ts:21`). 2-second poll with TTL-cached snapshots (`TeamSnapshotCache`, `server.py:96`).

**Optional Python extras (`pyproject.toml [project.optional-dependencies]`):**
- `dev` → `pytest>=9.0,<10.0`, `ruff>=0.1` (lint + test)
- `p2p` → `pyzmq>=25,<27` — ZeroMQ PUSH/PULL transport (`clawteam/transport/p2p.py`); imported lazily inside `P2PTransport`
- `plane` → `httpx>=0.27,<1.0` — sync HTTP client used only by `clawteam/plane/client.py:7`

**Testing:**
- `pytest >=9.0,<10.0` — `[tool.pytest.ini_options] testpaths = ["tests"]`. CI runs `python -m pytest tests/ -v --tb=short` across 3 Python versions × {ubuntu, macos}.

**Build / dev tooling:**
- `ruff >=0.1` — lint + import-sort. Config in `pyproject.toml`: `line-length = 100`, `target-version = "py310"`, lint rules `E, F, I, N, W` (E501 ignored).
- `hatchling` — Python build backend (`[build-system]` in `pyproject.toml`); wheels package the `clawteam` directory.

## Key Dependencies

**Critical (always installed):**
- `typer` — defines the entire `clawteam` command tree, including the `clawteam plane` sub-app added on this branch (`commands.py:4684`)
- `pydantic` — boundary of every cross-process payload (tasks, messages, Plane work items, configs)
- `rich` — sole terminal-rendering library (no fallback)
- `mcp` — required to ship the `clawteam-mcp` console script (`pyproject.toml [project.scripts]`)

**Critical (extras-gated):**
- `httpx` — required for `clawteam plane *` commands; absent in the default install. The Plane modules `import httpx` at module top so calling Plane CLI without the extra raises `ImportError` at first use.
- `pyzmq` — required only when `CLAWTEAM_TRANSPORT=p2p`; falls back to file transport otherwise.

**Infrastructure:**
- Native `tmux` binary — required by the default spawn backend (`clawteam/spawn/tmux_backend.py`) and by agent-liveness detection (`clawteam/board/liveness.py:17` shells out to `tmux list-windows`). The board explicitly distinguishes SSE liveness from agent liveness using this signal.
- Native `wsh` binary — optional Wave Terminal backend (`clawteam/spawn/wsh_backend.py`)
- Native `gource` binary — optional, used by `clawteam/board/gource.py` for activity visualization
- Docker + Docker Compose — required to host the bundled Plane stack via `scripts/plane-docker-setup.sh` (downloads Plane's official `setup.sh` and runs `docker compose up -d`)

## Configuration

**Environment variables (read directly from source):**
- `CLAWTEAM_DATA_DIR` — overrides the data directory; set by `--data-dir` CLI flag (`commands.py:64-66`). Resolution order in `clawteam/team/models.py:15-46`: env var → user-config `data_dir` → nearest `.clawteam/` walking up from cwd (project-local, git-style) → `~/.clawteam/` global fallback.
- `CLAWTEAM_TRANSPORT` — selects `file` (default) vs `p2p` ZeroMQ transport; set by global `--transport` flag (`commands.py:67-69`).

**Project-local data directory (this branch's addition):**
- `.clawteam/` — discovered by walking up from cwd. Contains `teams/`, `tasks/`, `costs/`, `workspaces/`, and the new `plane-config.json` (`clawteam/plane/config.py:27`).

**Per-team / per-tool config files:**
- `.clawteam/plane-config.json` — Plane integration settings (URL, API key, workspace slug, project ID, sync flag, webhook secret/port, state mapping). Schema: `PlaneConfig` in `clawteam/plane/config.py:13`.
- `.clawteam/teams/<team>/config.json` — team + member definitions
- `.clawteam/teams/<team>/inboxes/` — per-agent mailboxes
- `.clawteam/teams/<team>/peers/<agent>.json` — P2P peer discovery (`clawteam/transport/p2p.py:22`)
- User config (CLI/profile/preset) — managed via `clawteam config` / `clawteam profile` / `clawteam preset` sub-apps

**Build configuration:**
- `pyproject.toml` — packaging, deps, ruff, pytest
- `clawteam/board/frontend/vite.config.ts` — React + Tailwind plugins, `@/` alias to `src/`, build outDir set to `../static`, dev proxy `/api → localhost:8080`
- `clawteam/board/frontend/components.json` — shadcn config (style `base-nova`, baseColor `neutral`, CSS variables enabled, lucide icons)
- `clawteam/board/frontend/tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json` — split TS configs for app vs Node (Vite) code

**Secrets handling:**
- `.env` is in `.gitignore` (no `.env*` files committed in repo root).
- Plane API keys are persisted to `.clawteam/plane-config.json` via `save_plane_config` (atomic write); the project gitignore excludes only `.env`, not this file — operators must keep `.clawteam/` out of shared workspaces or use a non-project data dir.
- Webhook signatures verified via HMAC-SHA256 (`clawteam/plane/webhook.py:19-21`).

## Platform Requirements

**Development:**
- Linux or macOS (CI matrix: `ubuntu-latest`, `macos-latest`)
- Python 3.10–3.12
- Node 18+ for board frontend builds
- `tmux` on PATH for the default spawn / liveness pipeline
- `git` (workspace context tracking in `clawteam/workspace/git.py`)
- One or more agent CLIs on PATH (the spawner detects `claude`, `claude-code`, `codex`, `codex-cli`, `gemini`, `kimi`, `qwen`, `qwen-code`, `opencode`, `nanobot`, `openclaw`, `pi` — see `clawteam/spawn/adapters.py:106-172`)
- Optional: Docker for self-hosted Plane (`scripts/plane-docker-setup.sh`)
- Optional: `wsh` for Wave Terminal backend
- Optional: `gource` for activity visualization

**Production / runtime targets:**
- Same as development. ClawTeam ships as a developer-side coordination CLI; there is no managed-service deployment target. The board server binds `127.0.0.1:8080` by default (`clawteam/board/server.py:354`); the Plane webhook receiver binds `0.0.0.0:9091` by default (`clawteam/plane/webhook.py:209,215`).
- Distribution: PyPI-compatible wheel built by hatchling (`clawteam-0.3.0`); console scripts `clawteam` and `clawteam-mcp`.

---

*Stack analysis: 2026-04-28*
