# Coding Conventions

**Analysis Date:** 2026-04-15

ClawTeam is a Python 3.10+ CLI (Typer + Pydantic + Rich) with a TypeScript/React
dashboard under `clawteam/board/frontend/`. Conventions below are derived from
the actual source, not ideals.

## Naming Patterns

**Python files:**
- `snake_case.py` under `clawteam/<area>/` (e.g. `clawteam/team/mailbox.py`,
  `clawteam/spawn/subprocess_backend.py`).
- Area packages: `team/`, `spawn/`, `board/`, `plane/`, `harness/`, `events/`,
  `transport/`, `store/`, `mcp/`, `cli/`, `workspace/`.
- Tests live flat under `tests/test_<area>.py` (e.g. `tests/test_mailbox.py`),
  with one nested `tests/board/` subpackage.

**Python functions and variables:**
- `snake_case` for functions and locals.
- `_leading_underscore` for module-private helpers (e.g. `_teams_root()`,
  `_save_config()`, `_load_config()` in `clawteam/team/manager.py:14-39`).
- `UPPER_SNAKE_CASE` for module constants (e.g. `_STATIC_DIR`,
  `_ALLOWED_PROXY_HOSTS` in `clawteam/board/server.py:18-23`;
  `_IDENTIFIER_RE` in `clawteam/paths.py:8`).

**Python types:**
- `PascalCase` for classes, Pydantic models, and Enums
  (`TaskItem`, `TeamConfig`, `TeamMessage`, `MessageType`).
- Enum values are `snake_case` strings backed by `str, Enum`:
  `TaskStatus.in_progress = "in_progress"` (`clawteam/team/models.py:59-66`).
- Pydantic models subclass `BaseModel` and use `model_config = {"populate_by_name": True}`
  or `{"extra": "ignore"}` (see `clawteam/team/models.py:93` and
  `clawteam/plane/models.py:13`).

**TypeScript / React:**
- `kebab-case.tsx` for component files (`topbar.tsx`, `summary-bar.tsx`,
  `peek-panel.tsx`, `kanban/board.tsx`).
- `use-<thing>.ts` for hooks (`src/hooks/use-team-stream.ts`).
- `PascalCase` for exported components (`export function Topbar(...)`,
  `export function Board(...)`).
- `PascalCase` for interfaces/types, `SCREAMING_SNAKE_CASE` for constants
  (`TASK_STATUSES`, `STATUS_LABELS` in `src/types.ts:49-65`).

## Code Style

**Python formatting:**
- Ruff configured in `pyproject.toml`:
  ```toml
  [tool.ruff]
  line-length = 100
  target-version = "py310"
  [tool.ruff.lint]
  select = ["E", "F", "I", "N", "W"]
  ignore = ["E501"]
  ```
- 4-space indentation, double-quoted strings throughout.
- No Black/isort — Ruff handles import sort (`I`) and lint (`E`, `F`, `N`, `W`).

**Python typing:**
- Every `.py` file under `clawteam/` begins with
  `from __future__ import annotations` (87 of 99 files — effectively all
  non-trivial modules).
- PEP 604 unions: `str | None`, `list[str]`, `dict[str, Any]`. No
  `Optional[...]` / `Union[...]` in new code; CLI layer in
  `clawteam/cli/commands.py` still imports `Optional` for a few Typer
  options but stores use `str | None`.
- `typing.Any` is used sparingly and only where genuinely unstructured
  (e.g. `metadata: dict[str, Any]` in `TaskItem`, Plane API payloads).
- `TYPE_CHECKING` for heavy imports that would create cycles
  (`clawteam/plane/sync.py:6-18`, `clawteam/harness/context_recovery.py:5`).

**TypeScript:**
- `tsconfig.app.json` runs `"strict": true` plus `noUnusedLocals`,
  `noUnusedParameters`, `noFallthroughCasesInSwitch`,
  `noUncheckedIndexedAccess` (`clawteam/board/frontend/tsconfig.app.json:14-18`).
- Path alias `@/*` → `./src/*` wired in both tsconfig and `components.json`.
  Every internal import uses `@/components/...`, `@/lib/api`, `@/hooks/...`,
  `@/types`.
- 2-space indent, double quotes, no trailing semicolons (matches Vite/shadcn
  defaults used across `App.tsx`, `topbar.tsx`, `summary-bar.tsx`).

## Import Organization

**Python order** (enforced by Ruff `I`):
1. `from __future__ import annotations` (always first, on its own).
2. stdlib (`json`, `os`, `subprocess`, `pathlib.Path`, ...).
3. Third-party (`typer`, `pydantic`, `rich`, `httpx`).
4. First-party `clawteam.*` imports.

Example — `clawteam/cli/commands.py:1-21`:
```python
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from clawteam import __version__
from clawteam.timefmt import format_timestamp
```

**Lazy/local imports** are used deliberately to avoid optional-dep import
cost or circular deps — inside functions, not at top of file:
```python
def send(...):
    from clawteam.team.manager import TeamManager   # avoid cycle
    ...
```
(See `clawteam/team/mailbox.py:93`, and many `config_*` CLI commands that
import `from clawteam.config import ...` inside the function body.)

**TypeScript order:**
1. External packages (`react`, `@base-ui/react`, `@dnd-kit/react`, `clsx`,
   `class-variance-authority`).
2. Internal `@/` aliases (`@/components/...`, `@/lib/utils`, `@/lib/api`,
   `@/hooks/...`).
3. Type-only imports use `import type { ... }` (see
   `src/App.tsx:15`, `src/components/kanban/board.tsx:5`).

## Data Shapes: Pydantic Everywhere

**All persisted data and wire payloads are Pydantic `BaseModel`s** — there
are no dataclasses for domain models, and `dict` is avoided except for
free-form `metadata` / API payloads.

- `clawteam/team/models.py` — `TeamConfig`, `TeamMember`, `TeamMessage`,
  `TaskItem`, plus `MemberStatus`, `TaskStatus`, `TaskPriority`,
  `MessageType` enums.
- `clawteam/plane/models.py` — `PlaneWorkspace`, `PlaneProject`,
  `PlaneState`, `PlaneWorkItem`, `PlaneComment` (all `extra="ignore"` for
  forward-compat with Plane API changes).
- `clawteam/config.py` — `ClawTeamConfig`, `AgentProfile`, `AgentPreset`,
  `HookDef`.
- `clawteam/team/costs.py`, `clawteam/team/snapshot.py`,
  `clawteam/spawn/sessions.py` — all use `BaseModel` with
  `model_config = {"populate_by_name": True}`.

**JSON aliasing pattern:** fields use snake_case in Python but camelCase on
disk/wire, via `Field(alias=..., serialization_alias=...)`:
```python
# clawteam/team/models.py:127
class TeamMessage(BaseModel):
    model_config = {"populate_by_name": True}
    from_agent: str = Field(alias="from", serialization_alias="from")
    request_id: str | None = Field(default=None, alias="requestId")
    ...
```
Serialization helper in CLI dumps `by_alias=True, exclude_none=True`
(`clawteam/cli/commands.py:72-74`).

## CLI Pattern (Typer + Rich)

All command handlers live in `clawteam/cli/commands.py` (~3k+ lines). The
house style is:

- One module-level `app = typer.Typer(...)` plus sub-apps
  (`config_app`, `profile_app`, `preset_app`, `team_app`, etc.) mounted via
  `app.add_typer(...)`.
- A single `console = Console()` for all human output (no direct `print()`
  outside `_output()` helper).
- `--json` is a global flag set in `@app.callback()`; handlers call
  `_output(data, human_fn)` to dual-emit JSON or human text
  (`clawteam/cli/commands.py:77-84`).
- Pydantic → dict via `_dump(model)`:
  ```python
  def _dump(model) -> dict:
      return json.loads(model.model_dump_json(by_alias=True, exclude_none=True))
  ```
- Error exit is always: red rich tag, then `raise typer.Exit(1)`. This
  pattern appears 95 times in `clawteam/cli/commands.py` alone:
  ```python
  console.print(f"[red]Invalid {label} '{item}'. Expected KEY=VALUE.[/red]")
  raise typer.Exit(1)
  ```
- Human output tables use `rich.table.Table` with `style="cyan"` for keys
  and `style="dim"` for metadata columns (see `config_show()` at
  `commands.py:189-197`).

## Error Handling

**CLI layer** — loud and exit:
- `console.print("[red]...[/red]")` then `raise typer.Exit(1)`.
- Never silent, never bare `return` on failure.

**Library layer** — raise typed `ValueError`/custom exceptions, let the CLI
translate:
- `clawteam/paths.py:11` — `validate_identifier()` raises `ValueError` with
  a descriptive `kind` prefix.
- `clawteam/team/manager.py:90` — `raise ValueError(f"Team '{name}' already
  exists")`.

**Best-effort try/except** is reserved for optional features that must not
crash the main flow. The pattern is always specific:
- Event bus emits are wrapped in `try/except Exception: pass` because
  hooks are optional:
  ```python
  # clawteam/workspace/manager.py:229-236
  try:
      from clawteam.events.global_bus import get_event_bus
      from clawteam.events.types import AfterWorkspaceCleanup
      get_event_bus().emit_async(AfterWorkspaceCleanup(...))
  except Exception:
      pass
  ```
- Config load failures fall back to defaults instead of crashing:
  ```python
  # clawteam/config.py:88-92
  try:
      data = json.loads(p.read_text(encoding="utf-8"))
      return ClawTeamConfig.model_validate(data)
  except Exception:
      return ClawTeamConfig()
  ```

**Subprocess calls** catch the specific pair `(TimeoutExpired, OSError)`:
```python
# clawteam/board/liveness.py:22-32
try:
    result = subprocess.run(
        ["tmux", "list-windows", "-t", session, "-F", "#{window_name}"],
        capture_output=True, text=True, timeout=2,
    )
except (subprocess.TimeoutExpired, OSError):
    return set()
if result.returncode != 0:
    return set()
```

## Subprocess Usage

Every `subprocess.run` call in the repo follows the same shape:
- `capture_output=True, text=True` for stdout as `str`.
- Explicit `timeout=<seconds>` (never unbounded).
- Wrapping `try` catches `subprocess.TimeoutExpired` plus `OSError`.
- Check `result.returncode` before using `result.stdout`.

See `clawteam/board/liveness.py:22`, `clawteam/spawn/tmux_backend.py:122`,
`clawteam/team/watcher.py:107`, `clawteam/harness/context_recovery.py:84`.

`subprocess.Popen` is used only when the process must outlive the caller
(subprocess spawn backend). It pipes `stdout=subprocess.DEVNULL,
stderr=subprocess.DEVNULL` since unread pipes block long-lived runs
(`clawteam/spawn/subprocess_backend.py:97-105`).

## Filesystem and Data Directory

- Paths use `pathlib.Path`. String concatenation of paths does not appear.
- The canonical root is `get_data_dir()` in
  `clawteam/team/models.py:15-36`, which checks `CLAWTEAM_DATA_DIR`, then
  `config.data_dir`, then walks up for a project-local `.clawteam/`, then
  falls back to `~/.clawteam/`.
- Every write inside `data_dir` goes through `ensure_within_root()` in
  `clawteam/paths.py:24-33`, which rejects paths that resolve outside the
  configured root.
- Logical identifiers (team name, member name, user name) run through
  `validate_identifier()` (regex `[A-Za-z0-9._-]+`) before they touch
  disk — both to sanitise and to reject traversal.
- Persistent writes always use the atomic-rename helpers in
  `clawteam/fileutil.py`:
  - `atomic_write_text(path, content)` — `mkstemp` + `os.replace`.
  - `file_locked(path)` — exclusive advisory lock via `fcntl.flock`
    (or `msvcrt.locking` on Windows).

## Logging

- **Library code**: stdlib `logging`, module-level
  `log = logging.getLogger(__name__)`. See `clawteam/plane/sync.py:20`,
  `clawteam/plane/webhook.py:16`, `clawteam/plane/__init__.py:12`,
  `clawteam/workspace/manager.py:16` (the latter names it `logger`).
- **CLI code**: `console.print(...)` only; no `logging` calls in
  `clawteam/cli/commands.py`.
- No structured logging framework (no `structlog`, `pino`, etc.); messages
  are plain `%s`-style:
  ```python
  log.info("Updated Plane work item %s for task %s", plane_id, task.id)
  ```

## Frontend Conventions (React + Tailwind + shadcn)

**Styling:**
- shadcn `base-nova` style, `baseColor: "neutral"`, `cssVariables: true`
  (`clawteam/board/frontend/components.json:3-12`).
- Tokens are semantic: `bg-background`, `bg-card`, `text-foreground`,
  `text-muted-foreground`, `border-border`, `ring-ring` — these appear 35+
  times across components. Direct `zinc-*` hardcodes only remain in
  `agent-registry.tsx`, `message-stream.tsx`, and `kanban/board.tsx`; new
  code should prefer semantic tokens (recent `topbar.tsx`, `summary-bar.tsx`,
  `peek-panel.tsx` have none).
- `cn()` helper merges Tailwind classes conditionally
  (`src/lib/utils.ts`, using `clsx` + `tailwind-merge`).
- Variants via `class-variance-authority` (`cva(...)`) for shadcn primitives
  (see `src/components/ui/button.tsx:6-41`).

**Components:**
- Props typed as an inline `interface <Component>Props { ... }`
  immediately above the component.
- Function components exported by name:
  `export function Topbar({ ... }: TopbarProps) { ... }`. No default
  exports except `App.tsx`.
- Data hooks in `src/hooks/` — currently only `use-team-stream.ts`, which
  wraps the SSE `/api/events/:team` stream in `useState` + `useEffect` +
  `useRef`.
- All HTTP I/O goes through `src/lib/api.ts` (thin `fetch` wrapper with
  `post<T>`, `patch<T>`, plus named exports `fetchOverview`, `createTask`,
  `updateTask`, `addMember`, `sendMessage`, `fetchProxy`). Components do
  not call `fetch` directly.
- Global state shared via a single `React.createContext` per surface — see
  `TeamContext` in `App.tsx:17-31`.

## Function Design

- Small helpers preferred — `clawteam/cli/commands.py` has ~50 underscore-
  prefixed private helpers (`_dump`, `_output`, `_parse_key_value_items`,
  `_load_skill_content`, ...).
- Keyword-only args used when a call site would otherwise pass 4+
  positionals — `register_agent(team_name, agent_name, backend=..., pid=...)`
  in `clawteam/spawn/subprocess_backend.py:110-116`.
- Static methods grouped on manager classes (`TeamManager.create_team`,
  `TeamManager.add_member`, `TeamManager.cleanup`) — the classes act as
  namespaces for functions that share a conceptual area.

## Comments

- Module-level docstrings on every file: `"""Short purpose sentence."""`.
- Functions that do something non-obvious (atomicity, lock ordering,
  concurrency) carry a prose paragraph — see `clawteam/fileutil.py:28-40`
  and `clawteam/team/mailbox.py:33-40`.
- Inline `# comments` explain *why*, not *what*
  (`clawteam/board/server.py:109-112` — rationale for loading outside a
  lock).
- `# pragma: no cover` used selectively on trivial import-error branches
  (`clawteam/cli/commands.py:139`).

## Module Design

- Each subpackage has an `__init__.py` that re-exports its public API
  (`clawteam/events/__init__.py`, `clawteam/spawn/__init__.py`,
  `clawteam/transport/__init__.py`). Private helpers stay unexported.
- `clawteam/__main__.py` makes the package runnable as
  `python -m clawteam`.
- Entry points registered in `pyproject.toml`:
  ```toml
  [project.scripts]
  clawteam = "clawteam.cli.commands:app"
  clawteam-mcp = "clawteam.mcp.server:main"
  ```
- Optional features are opt-in extras (`[project.optional-dependencies]`:
  `dev`, `p2p`, `plane`) — relevant imports are lazy so the base install
  does not pull `httpx` or `pyzmq`.

---

*Convention analysis: 2026-04-15*
*Update when patterns change*
