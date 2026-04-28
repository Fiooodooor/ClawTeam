# Coding Conventions

**Analysis Date:** 2026-04-28

This codebase has two distinct convention zones:

1. **Python backend** (`clawteam/`) — Typer CLI + Pydantic v2 models, lint with ruff, line length 100, py3.10+.
2. **TypeScript frontend** (`clawteam/board/frontend/`) — React 19 + Vite 6 + Tailwind v4 + shadcn/ui (`base-nova` style) on top of `@base-ui/react` primitives, strict TypeScript.

## Naming Patterns

### Python files & modules

- Lowercase, snake_case, single-word where possible: `clawteam/plane/client.py`, `clawteam/board/liveness.py`, `clawteam/spawn/tmux_backend.py`.
- Sub-packages are flat (`plane/`, `board/`, `spawn/`, `team/`, `events/`, `store/`) and each has an `__init__.py` that re-exports the public surface (see `clawteam/plane/__init__.py`, `clawteam/spawn/__init__.py`).
- Test files mirror source: `tests/test_plane_client.py` exercises `clawteam/plane/client.py`. New focused test areas are nested (`tests/board/test_liveness.py`).
- Backend files are suffixed `_backend.py`: `subprocess_backend.py`, `tmux_backend.py`, `wsh_backend.py`.

### Python identifiers

- Functions/variables: `snake_case` (`load_plane_config`, `resolve_state_id`, `_task_to_plane_payload`).
- Classes: `PascalCase` (`PlaneClient`, `PlaneSyncEngine`, `TeamManager`, `BoardCollector`).
- Constants: `UPPER_SNAKE_CASE` module-level dicts/lookups (`_STATUS_TO_GROUP`, `DEFAULT_STATE_NAMES`, `_CLAWTEAM_TO_PLANE_PRIORITY`, `_ALLOWED_PROXY_HOSTS`).
- Private helpers: leading underscore (`_handle_work_item_event`, `_verify_signature`, `_now_iso`, `_find_project_data_dir`).
- Pydantic enum values: lowercase strings backed by `str, Enum` so they JSON-serialize naturally (see `TaskStatus`, `TaskPriority`, `MessageType` in `clawteam/team/models.py`).
- Lint rule set in `pyproject.toml` (lines 65-71): `ruff` selects `E, F, I, N, W` and ignores `E501` (line length is checked separately at 100).

### TypeScript files & identifiers

- Components and modules use **kebab-case filenames** with PascalCase exports: `peek-panel.tsx` exports `PeekPanel`, `agent-registry.tsx` exports `AgentRegistry`, `kanban/task-card.tsx` exports `TaskCard`.
- Hooks live under `src/hooks/` and use `use-` prefix: `hooks/use-team-stream.ts` exports `useTeamStream`.
- shadcn UI primitives live under `src/components/ui/` (lowercase filenames, PascalCase exports): `button.tsx`, `dialog.tsx`, `select.tsx`, `sheet.tsx`, `card.tsx`, `badge.tsx`, `input.tsx`, `label.tsx`, `scroll-area.tsx`, `textarea.tsx`.
- Modals live under `src/components/modals/`: `add-agent.tsx`, `inject-task.tsx`, `send-message.tsx`, `set-context.tsx`.
- Domain components live flat under `src/components/`: `topbar.tsx`, `summary-bar.tsx`, `peek-panel.tsx`, `message-stream.tsx`, `agent-registry.tsx`, plus the `kanban/` subdirectory.
- Types: PascalCase interfaces in `src/types.ts` (`TeamData`, `Member`, `Task`, `Message`, `TaskSummary`, `TasksByStatus`); literal-union string types (`TaskStatus = "pending" | "in_progress" | ...`).
- Constants: UPPER_SNAKE_CASE arrays/maps (`TASK_STATUSES`, `STATUS_LABELS`, `STATUS_COLORS`, `AGENT_TYPES`, `PRIORITIES`).

## Code Style

### Python

- **Formatter / linter:** `ruff` only — no Black, no isort. Configured in `pyproject.toml` `[tool.ruff]` (line-length 100, target `py310`).
- **`from __future__ import annotations`** at the top of nearly every Python file (87/99 source files). Always include it in new modules; it is what allows `dict | None`, `list[str]`, `PlaneClient | None` style hints on Python 3.10.
- Type hints use **PEP 604 unions** (`str | None`) and **PEP 585 builtin generics** (`list[str]`, `dict[str, Any]`) — never `Optional[...]`/`List[...]` from `typing` (one exception: `cli/commands.py` still imports `Optional` for Typer compatibility).
- 4-space indent, double-quoted string literals dominate, f-strings for interpolation.
- Module docstring on the first line of every file (single triple-quoted string), e.g. `"""Pydantic models for Plane REST API objects."""` at top of `clawteam/plane/models.py`.

### TypeScript / React

- **Strict TypeScript** with `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`, `noUncheckedIndexedAccess` all enabled (see `clawteam/board/frontend/tsconfig.app.json`).
- React 19 functional components with named `export function ComponentName(...)`.
- Props are explicit `interface ComponentNameProps { ... }` declared above the component (see `interface TopbarProps` in `topbar.tsx:12`, `interface BoardProps` in `kanban/board.tsx:8`).
- No semicolons in TS source files.
- JSX uses double quotes, `className` is the only styling primitive — Tailwind utility classes only, with `cn()` from `@/lib/utils` (twMerge + clsx) for composition.
- Variant-driven components use `class-variance-authority` (`cva`) — see `buttonVariants` in `components/ui/button.tsx`.
- Component files do NOT use `default export` for components (only the root `App.tsx` does); everything else is named-export.

## Import Organization

### Python

Three-block layout, blank line between blocks:

1. `from __future__ import annotations`
2. **stdlib** (`json`, `os`, `hashlib`, `hmac`, `pathlib`, `unittest.mock`, ...)
3. **third-party** (`httpx`, `pytest`, `typer`, `pydantic`, `rich`, `questionary`)
4. **first-party** (`from clawteam.* import ...`)

Example pattern (`tests/test_plane_webhook.py:1-18`):

```python
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from clawteam.plane.config import PlaneConfig
from clawteam.plane.webhook import (
    _verify_signature,
    _handle_work_item_event,
    _handle_comment_event,
)
from clawteam.team.manager import TeamManager
from clawteam.team.models import TaskStatus
```

**Lazy / local imports** are used heavily and intentionally to avoid circular imports and keep CLI startup fast. Examples:

- `clawteam/plane/__init__.py:17-18` imports `events.types` and `store.file` inside `register_sync_hooks` instead of at module top.
- `clawteam/plane/sync.py:57-58` imports `FileTaskStore` inside `push_task` to break the `plane <-> store` cycle.
- `clawteam/cli/commands.py` imports nearly every dependency inside the command function body (e.g. `from clawteam.config import ...` inside `config_set`).
- `clawteam/spawn/__init__.py` lazily imports each backend module inside `get_backend()` so a missing optional dep (e.g. `pyzmq`) does not break unrelated commands.

Do this when introducing a new sub-feature: pull heavy/optional dependencies in at call site, not at import time.

### TypeScript

Order, blank line between groups:

1. React core (`useState`, `useEffect`, `useRef`, `useMemo`, `createContext`, `useContext`).
2. Third-party libs (`@base-ui/react/...`, `@dnd-kit/react`, `class-variance-authority`, `lucide-react`, `clsx`, `tailwind-merge`).
3. `@/components/...` (UI first, then domain).
4. `@/lib/...`, `@/hooks/...`.
5. `import type { ... } from "@/types"` last.

**Path aliases:** `@/*` -> `clawteam/board/frontend/src/*`. Configured in three places that must stay in sync: `vite.config.ts:9`, `tsconfig.json:5`, `tsconfig.app.json:21`, plus `components.json:15-21` for shadcn.

## Pydantic Conventions

- **Pydantic v2** (`pydantic>=2.0.0,<3.0.0`). Always use `model_validate`, `model_dump_json`, `model_copy(deep=True)`, `model_fields` — never v1 `parse_obj`, `dict()`, etc.
- Models inherit from `BaseModel`. Configuration is the inline `model_config = {...}` dict, not a nested `Config` class:
  - `model_config = {"extra": "ignore"}` for all `clawteam.plane.models.*` so future Plane API fields do not crash deserialization.
  - `model_config = {"populate_by_name": True}` on team models so both `agent_id`/`agentId` are accepted.
- Defaults: `Field(default_factory=list)` / `Field(default_factory=dict)` for mutable defaults; `Field(default_factory=lambda: uuid.uuid4().hex[:12], alias="agentId")` for generated IDs.
- Aliases bridge Python `snake_case` <-> JSON `camelCase`. Always serialize with `model_dump_json(by_alias=True)` for any payload crossing the wire (see `clawteam/team/manager.py:_save_config`, `clawteam/cli/commands.py:_dump`).
- All persisted JSON files go through `clawteam.fileutil.atomic_write_text` (mkstemp + `os.replace`) — never `path.write_text` for state. See `clawteam/config.py:save_config`, `clawteam/plane/config.py:save_plane_config`.
- Provide non-strict `__init__` defaults (e.g. `id: str = ""`, `priority: str = "none"` in `PlaneWorkItem`) so partial API responses still construct successfully.

## Typer CLI Conventions

- Single root app in `clawteam/cli/commands.py`: `app = typer.Typer(name="clawteam", help=..., no_args_is_help=True)`.
- Sub-apps wired with `app.add_typer(config_app, name="config")`, `app.add_typer(profile_app, name="profile")`, `app.add_typer(preset_app, name="preset")`, etc. Add new domains the same way.
- Global options live on `@app.callback()` (`--version`, `--json`, `--data-dir`, `--transport`); they mutate module-level globals (`_json_output`, `_data_dir`) and forward into env vars (`os.environ["CLAWTEAM_DATA_DIR"] = ...`).
- Every command supports both human and JSON output through `_output(data, _human)`. Always provide both a JSON-serializable dict and a `_human(d)` callable that pretty-prints with `rich.Table` / `console.print`.
- Errors: `console.print(f"[red]...[/red]")` then `raise typer.Exit(1)` — never `sys.exit`. Successful side effects: `console.print(f"[green]OK[/green] ...")`.
- Argument/option help strings are mandatory (`typer.Argument(..., help="...")`, `typer.Option(None, "--name", help="...")`).
- Validation uses `_parse_key_value_items(items, label="env")` for repeatable `KEY=VALUE` options (`--env`, `--env-map`).
- Lazy imports inside the command body keep `clawteam --help` snappy (see "Import Organization" above).

## React / shadcn Conventions

- **shadcn config** (`clawteam/board/frontend/components.json`): style `base-nova`, RSC off, TSX on, base color `neutral`, icon library `lucide`, CSS variables on. Import primitives via the `@/components/ui/*` aliases.
- **Underlying primitives are `@base-ui/react`**, NOT `@radix-ui`. The shadcn registry has been re-skinned on Base UI. When you regenerate a component, target `base-nova`, not `default`.
- Tailwind v4 with `@import "tailwindcss"` — config is CSS-first inside `src/index.css` using `@theme inline { ... }`. Color tokens are `oklch()` CSS variables exposed as `--color-*`. Status colors live as semantic tokens: `--color-status-pending`, `--color-status-progress`, `--color-status-approval`, `--color-status-completed`, `--color-status-verified`, `--color-status-blocked`. Reference them via `var(--color-status-*)` (see `STATUS_COLORS` in `src/types.ts:67-74`).
- All class composition goes through `cn()` from `@/lib/utils` (clsx + tailwind-merge).
- Variant components use `cva()` and accept `VariantProps<typeof variants>` plus the underlying primitive's props (see `Button` props are `ButtonPrimitive.Props & VariantProps<typeof buttonVariants>` in `components/ui/button.tsx:48`).
- Data-slot attribute pattern: every UI primitive sets `data-slot="button"` (or similar) on the rendered element so styling and tests can hook in.
- API access goes through `@/lib/api.ts` only — never inline `fetch()` in components. The client uses a `BASE = "/api"` constant proxied to `http://localhost:8080` in dev (`vite.config.ts:18-21`).
- SSE consumption is centralized in `@/hooks/use-team-stream.ts`; new realtime data should extend `TeamData` in `@/types.ts` and flow through the same hook.
- Dialog/Sheet: opening state lives in the parent (`useState` in `App.tsx`), child receives `open: boolean` + `onClose: () => void` props (see `InjectTaskDialog`, `PeekPanel`, `AddAgentDialog` usages in `App.tsx:170-193`).

## Error Handling

### Python

- **CLI surface:** print red message, exit non-zero. Pattern from `cli/commands.py`:
  ```python
  console.print(f"[red]Invalid key '{key}'. Valid: {', '.join(sorted(valid_keys))}[/red]")
  raise typer.Exit(1)
  ```
- **Library surface:** raise specific exceptions (`ValueError`, `TaskLockError`, `httpx.HTTPStatusError`). Don't catch unless you have something meaningful to do.
- **Background hooks / sync:** broad `except Exception as exc: log.warning(...)` so a failing webhook or Plane API never tears down the whole agent (see `clawteam/plane/__init__.py:28-29`, `clawteam/plane/sync.py:75-76`, `clawteam/plane/webhook.py:133-134`).
- **Persistence:** `load_*` functions return defaults on `json.JSONDecodeError` / generic `Exception` so a corrupt file does not brick the CLI (`clawteam/config.py:88-92`, `clawteam/plane/config.py:35-39`, `clawteam/team/manager.py:35-36`).
- HTTP: `resp.raise_for_status()` immediately after every request (see `PlaneClient._get/_post/_patch` in `clawteam/plane/client.py:62, 67, 72`).

### TypeScript

- `fetch` wrappers throw on non-2xx: `if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`)` (`src/lib/api.ts:9, 19`).
- Components catch with `.catch(console.error)` for fire-and-forget mutations (`updateTask(...).catch(console.error)` in `kanban/board.tsx:35`, `peek-panel.tsx:78`).
- For interactive flows, set a local `submitting` flag and try/catch/finally (see `add-agent.tsx:43-56`).
- SSE: silent `.onerror = () => setIsConnected(false)` with parse failures going to `console.error` (`hooks/use-team-stream.ts:35, 39`).

## Logging

- **Module-level logger:** `log = logging.getLogger(__name__)` at top of every module that logs (consistent variable name `log`, not `logger`, except in `clawteam/workspace/manager.py` which still uses `logger`). Used in `clawteam/plane/__init__.py:12`, `clawteam/plane/sync.py:20`, `clawteam/plane/webhook.py:16`.
- Log calls use `%`-style placeholders, never f-strings: `log.info("Created Plane work item %s for task %s", item.id, task.id)`. This defers formatting until the handler decides to emit.
- User-facing CLI messages go through `rich.Console.print(...)` with `[color]...[/color]` markup, NOT through `logging`.
- Frontend uses `console.error` for unexpected conditions only.

## Function Design

- **Module-level helpers** for pure transforms (no class wrapper). Examples: `_task_to_plane_payload(task, state_id)` in `clawteam/plane/client.py:30`, `clawteam_status_to_plane_group(status)` and `resolve_state_id(states, status)` in `clawteam/plane/mapping.py`. Prefer this over methods when there is no state to carry.
- Classes are reserved for things that genuinely own state or a connection: `PlaneClient` (httpx session), `PlaneSyncEngine` (config + cached states), `TeamManager` (uses `@staticmethod` for everything because all state lives on disk).
- Keep functions short — most CLI commands and webhook handlers are 20-50 lines. When a webhook handler needs sub-steps (`_send_approval_request`, `_send_hitl_message`), extract them as private module-level helpers next to the caller (see `clawteam/plane/webhook.py:118-162`).
- Constructor signatures pass plain values, not big config blobs, when feasible: `PlaneClient(base_url, api_key, workspace_slug)` rather than `PlaneClient(config)`. The orchestrating layer (`PlaneSyncEngine`) takes the full `PlaneConfig` and unpacks.

## Module Design

- Each subpackage `__init__.py` exposes a small surface via `__all__` (e.g. `clawteam/plane/__init__.py: __all__ = ["register_sync_hooks"]`, `clawteam/spawn/__init__.py: __all__ = ["SpawnBackend", "get_backend", "register_backend"]`).
- No barrel files in the frontend — every component is imported by its full path (`@/components/kanban/board`, `@/components/modals/add-agent`).
- Cross-cutting Plane <-> store integration is wired through the **event bus** (`clawteam/events/bus.py`) using `register_sync_hooks(bus, engine, team_name)` rather than direct calls — keeps the store layer ignorant of Plane.

## Documentation

- Module docstring on every Python file (one-liner is fine).
- Docstrings on public functions/classes; private helpers usually skip docstrings unless behavior is non-obvious.
- Use numbered lists in docstrings for resolution / fallback order (see `get_data_dir()` in `clawteam/team/models.py:15-24`, `resolve_state_id()` in `clawteam/plane/mapping.py:50-56`).
- Inline `# pragma: no cover` on import-error guards that are intentionally untested (e.g. `cli/commands.py:139`).

---

*Convention analysis: 2026-04-28*
