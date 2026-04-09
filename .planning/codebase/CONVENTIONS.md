# Coding Conventions

**Analysis Date:** 2026-04-28

ClawTeam is a hybrid Python + TypeScript repository. The Python package
(`clawteam/`) is the CLI / coordination engine; the TypeScript package
(`clawteam/board/frontend/`) is the React SPA shipped as `clawteam board serve`'s
static bundle. Conventions differ meaningfully between the two halves and are
documented separately below.

The project skill at `skills/clawteam/SKILL.md` is the authoritative reference
for end-user CLI behavior; this document covers source-level conventions only.

---

## Python — `clawteam/`

### Toolchain

- **Python:** `>=3.10` (`pyproject.toml` line 6). Type syntax assumes 3.10
  (`X | None`, PEP 604).
- **Formatter / linter:** `ruff` only — no `black`, no `isort`. Configured in
  `pyproject.toml`:
  - `line-length = 100`
  - `target-version = "py310"`
  - lint rules: `["E", "F", "I", "N", "W"]` with `E501` (line length) ignored
- **Pydantic:** v2 (`pydantic>=2.0.0,<3.0.0`). All models use `model_config`,
  `model_dump_json`, `model_validate`. Never use deprecated `dict()` / `parse_obj()`.

### File header

Every Python module starts with a one-line module docstring describing scope.
Examples:

- `clawteam/fileutil.py` line 1: `"""Atomic file writes and advisory file locking."""`
- `clawteam/team/manager.py` line 1: `"""Team manager for creating and managing teams."""`
- `clawteam/board/liveness.py` line 1: `"""Detects which team members have a live tmux session/window."""`

After the docstring, immediately enable PEP 563 deferred evaluation:

```python
"""Module summary line."""

from __future__ import annotations
```

`from __future__ import annotations` is present in essentially every non-trivial
module (see `clawteam/team/tasks.py`, `clawteam/store/file.py`,
`clawteam/spawn/tmux_backend.py`, `tests/test_tmux_injection.py`,
`tests/test_data_dir.py`).

### Naming

| Element | Style | Example | File |
|---------|-------|---------|------|
| Modules / packages | `snake_case` | `team_manager` is a class, but the module is `manager.py` | `clawteam/team/manager.py` |
| Classes | `PascalCase` | `TeamManager`, `FileTaskStore`, `TmuxBackend`, `MailboxManager` | `clawteam/team/manager.py:50` |
| Functions / methods | `snake_case` | `atomic_write_text`, `get_data_dir`, `_pane_safe_to_inject` | `clawteam/fileutil.py:28` |
| Module-private helpers | leading `_` | `_now_iso`, `_find_project_data_dir`, `_render_runtime_notification` | `clawteam/team/models.py:39`, `clawteam/spawn/tmux_backend.py:733` |
| Constants | `SCREAMING_SNAKE` | `_INJECT_SAFE_COMMANDS`, `_SHELL_ENV_KEY_RE`, `_ALLOWED_PROXY_HOSTS` | `clawteam/spawn/tmux_backend.py:30`, `clawteam/board/server.py:19` |
| Pydantic enum members | lowercase | `TaskStatus.pending`, `MessageType.broadcast` | `clawteam/team/models.py:53` |

Two naming subtleties to honor:

1. **Aliased Pydantic fields use `camelCase` on the wire.** Python attributes
   are `snake_case` but the JSON form (and therefore the disk format and the
   browser API contract) is camelCase. See `Pydantic models` below.
2. **`from` is a Python keyword**, so `TeamMessage.from_agent` is aliased to
   `"from"` for both validation and serialization
   (`clawteam/team/models.py:124`).

### Pydantic v2 models

All shared records are Pydantic v2 models. Two patterns are mandatory:

```python
class TeamMember(BaseModel):
    """A member of a team."""

    model_config = {"populate_by_name": True}

    name: str = Field(alias="name")
    user: str = Field(default="", alias="user")
    agent_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12], alias="agentId")
    agent_type: str = Field(default="general-purpose", alias="agentType")
    joined_at: str = Field(default_factory=_now_iso, alias="joinedAt")
```

(`clawteam/team/models.py:90`)

- `model_config = {"populate_by_name": True}` — accept both the snake_case
  attribute name and the camelCase alias when validating.
- All on-wire keys go through `Field(alias="…")`. Disk JSON, HTTP responses,
  and CLI `--json` output use the aliases.
- Default IDs come from `uuid.uuid4().hex[:N]` (12 chars for agent IDs, 8 for
  task IDs — `clawteam/team/models.py:154`).
- Default timestamps come from `_now_iso()` returning
  `datetime.now(timezone.utc).isoformat()`. Never use `datetime.utcnow()`
  (naive). See `clawteam/team/models.py:49`.

When `from_agent: str = Field(alias="from", serialization_alias="from")`
is needed (Python keyword collision), supply *both* `alias` and
`serialization_alias` (`clawteam/team/models.py:124`).

**Serialization rules** (used everywhere in `clawteam/cli/commands.py:_dump`):

```python
def _dump(model) -> dict:
    """Dump a pydantic model to dict with by_alias and exclude_none."""
    return json.loads(model.model_dump_json(by_alias=True, exclude_none=True))
```

Every model dump uses `by_alias=True, exclude_none=True`. JSON output is
indented with `indent=2, ensure_ascii=False` for human + machine readers
(`clawteam/cli/commands.py:80`).

### Persistence — `atomic_write_text` and `file_locked`

All disk writes go through `clawteam/fileutil.py`. Never call
`Path.write_text` / `open("w")` directly for shared state.

```python
from clawteam.fileutil import atomic_write_text, file_locked

atomic_write_text(path, content)               # tmp + os.replace, never partial reads

with file_locked(path):                        # advisory lock on <path>.lock
    # read-modify-write a JSON file safely across processes
    ...
```

(`clawteam/fileutil.py:28`, `:55`)

Cross-process safety is taken seriously. `clawteam/store/file.py` ships its own
`_write_lock()` context manager built on the same `fcntl.LOCK_EX` /
`msvcrt.LK_LOCK` primitives (`clawteam/store/file.py:54`). Any code path that
mutates a shared JSON file under `~/.clawteam/` (or its project-local
equivalent) must hold this lock for the entire read-modify-write window.

### Path handling

- Always use `pathlib.Path`, never `os.path.join` for new code.
- The data root is resolved via `get_data_dir()` in `clawteam/team/models.py:15`.
  Resolution order is documented in the function docstring and tested in
  `tests/test_data_dir.py`:
  1. `CLAWTEAM_DATA_DIR` env var
  2. `data_dir` from `~/.config/clawteam/config.json`
  3. nearest `.clawteam/` walking up from `cwd` (project-local, git-style)
  4. `~/.clawteam/` (global fallback)
- Identifiers that build into filesystem paths must go through
  `validate_identifier(...)` and `ensure_within_root(...)` from
  `clawteam/paths.py` to prevent directory traversal. See
  `clawteam/store/file.py:24`, `clawteam/team/manager.py:20`.

### Typer CLI patterns

The CLI is built on Typer and Rich, exposed through `clawteam.cli.commands:app`
(see `pyproject.toml` `[project.scripts]`). Patterns from
`clawteam/cli/commands.py`:

- One root `typer.Typer(no_args_is_help=True)` per `app` and one per command
  group; sub-typers are mounted with `app.add_typer(group_app, name="…")`
  (`clawteam/cli/commands.py:175`, `:259`, `:262`).
- Global options live in `@app.callback()` and write into module-level
  `_json_output` / `_data_dir` flags that downstream commands read
  (`clawteam/cli/commands.py:44`).
- Every command supports `--json` via the global `_output(data, human_fn=…)`
  helper. JSON output is the structured form; the human form is a Rich
  `Table` rendering of the same dict
  (`clawteam/cli/commands.py:77`, `:181`).
- Validation errors print red text and `raise typer.Exit(1)`. Successes print
  green `OK`. See `clawteam/cli/commands.py:215`, `:228`.
- Heavy / optional deps are imported lazily inside the command function
  (`questionary` in `_load_questionary` at `clawteam/cli/commands.py:135`,
  `BoardCollector` import inside `board_*` commands). Top-level imports stay
  cheap so `clawteam --version` is fast.

### Imports

Order (enforced by `ruff` rule `I`):

1. `from __future__ import annotations`
2. stdlib
3. third-party (`typer`, `pydantic`, `rich`, `questionary`)
4. first-party (`from clawteam.…`)

One blank line between groups. Local / lazy imports inside function bodies
are explicitly allowed and frequently used to keep cold-start fast (e.g.
`from clawteam.config import load_config` inside `get_data_dir()`).

### Error handling

- Caller-facing CLI errors: print to `console` with a `[red]…[/red]` Rich tag
  and `raise typer.Exit(1)`. Never `sys.exit` directly from a Typer command.
- Library-layer errors: raise a typed exception (`TaskLockError`,
  `RuntimeError("tmux load-buffer failed …")`). See
  `clawteam/spawn/tmux_backend.py:_run_tmux` (`:685`) — every `subprocess.run`
  whose failure must be observed is wrapped in `_run_tmux` which raises on
  non-zero exit.
- Best-effort side effects (event bus emits, telemetry) are wrapped in
  bare `try/except Exception: pass` (`clawteam/store/file.py:107`).
- Subprocess probes that are allowed to fail silently (e.g. tmux liveness
  detection) explicitly catch `(subprocess.TimeoutExpired, OSError)` and
  return an empty / falsy value (`clawteam/board/liveness.py:28`).

### Subprocess discipline

Two rules learned from the tmux runtime-injection bug fixes (commit on this
branch, covered by `tests/test_tmux_injection.py`):

1. **Check `shutil.which` before invoking external CLIs.** If the binary is
   missing, return a structured failure — never let `FileNotFoundError`
   escape from a library call. See
   `clawteam/board/liveness.py:17`,
   `clawteam/spawn/tmux_backend.py:295`.
2. **Inspect every return code.** Use `_run_tmux(args)` (raises) for
   side-effecting tmux commands, and `subprocess.run(..., capture_output=True,
   text=True)` + manual `returncode` checks for read-only probes. Never use
   `check=True` blindly inside library code — it makes the error message
   less actionable than a hand-rolled `RuntimeError("tmux load-buffer failed
   (exit 1): <stderr>")`.

When generating a unique resource name (paste buffer, temp file, request id),
use `uuid.uuid4().hex[:N]` — see `clawteam/spawn/tmux_backend.py:712`.

### Logging / output

There is no `logging` framework in user-facing code. CLI output goes through
the module-level `console = Console()` from Rich
(`clawteam/cli/commands.py:27`). Library code returns structured values; the
caller decides whether to print.

### Comments and docstrings

- Every public function and class has a triple-quoted docstring on the line
  immediately after the signature.
- Multi-line docstrings start with a one-line summary, blank line, then
  detail. See `clawteam/fileutil.py:28-40` and `clawteam/team/models.py:15-24`
  for canonical examples.
- Inline comments explain *why*, not *what*. The tmux backend has several
  exemplary inline comments about WSL `PROGRAMFILES(X86)` (`:108`),
  `TERM=dumb` from non-interactive shells (`:67`), and Claude nesting
  detection (`:115`).

### Function design

- Prefer keyword arguments for anything beyond two positional parameters.
  Static methods on managers (`TeamManager.create_team(name, leader_name, …)`)
  use keyword-only arguments at call sites in tests
  (`tests/test_board.py:17`).
- Default mutable arguments are forbidden; use `Field(default_factory=list)`
  on Pydantic models and `param: list[str] | None = None` plus an
  `or []` body on plain functions
  (`clawteam/store/file.py:83-95`).

---

## TypeScript — `clawteam/board/frontend/`

The dashboard is React 19 + Vite 6 + Tailwind v4 + shadcn/ui (`base-nova`
style on top of Base UI primitives `@base-ui/react`). The build output is
written to `clawteam/board/static/` and served by the stdlib HTTP server in
`clawteam/board/server.py`.

### Toolchain

- React 19, react-dom 19 (`package.json` lines 16-17)
- TypeScript ~5.8 (`package.json` line 28)
- Vite 6 with `@vitejs/plugin-react` and `@tailwindcss/vite` plugin
  (`vite.config.ts:2-7`)
- Tailwind v4 in CSS-first mode — no `tailwind.config.js`, only
  `@import "tailwindcss"` and `@theme inline {…}` blocks in
  `src/index.css`. The shadcn `components.json` declares
  `"tailwind.config": ""` to make this explicit.
- shadcn style: `"style": "base-nova"` (`components.json:3`),
  `"baseColor": "neutral"`, `"iconLibrary": "lucide"`.
- Drag-and-drop: `@dnd-kit/react` (Kanban board)
- Class composition helpers: `clsx` + `tailwind-merge` exposed as `cn()` in
  `src/lib/utils.ts`.

### File and directory naming

| Element | Style | Example |
|---------|-------|---------|
| Component / hook / lib filenames | `kebab-case.tsx` / `.ts` | `agent-registry.tsx`, `peek-panel.tsx`, `task-card.tsx`, `use-team-stream.ts` |
| Directories | `kebab-case` | `components/kanban/`, `components/modals/`, `components/ui/` |
| Component exports | `PascalCase` named exports | `export function Topbar(...)`, `export function Board(...)` |
| Hooks | `useFoo` named export from `kebab-case` file | `useTeamStream` in `hooks/use-team-stream.ts` |
| Types | `PascalCase` interface in `src/types.ts` | `TeamData`, `Member`, `Task`, `TaskStatus` |
| Type-only constants | `SCREAMING_SNAKE` | `TASK_STATUSES`, `STATUS_LABELS`, `STATUS_COLORS` (`types.ts:49-73`) |

The `App.tsx` and `main.tsx` entry points are the only PascalCase filenames —
this is the standard Vite-React template and should be kept as-is.

### Style: no semicolons

The whole frontend omits trailing semicolons at the end of statements. Verified
across `App.tsx`, `main.tsx`, `lib/api.ts`, all `components/*.tsx`, and all
`components/ui/*.tsx` files (zero matches for `;\s*$`). The single exception
is the `"use client"` directive at the top of files copied verbatim from
shadcn (currently only `components/ui/dialog.tsx:1`).

This is not enforced by a linter (no eslint / prettier config is checked in
under the frontend directory), so contributors must mirror the existing
style by hand. New files: omit semicolons.

Other style points observed throughout:

- Double-quoted strings (`import { foo } from "bar"`).
- 2-space indentation.
- Trailing commas in multiline object / arg lists.
- Arrow components only for inline callbacks; top-level components use
  `export function Name() {}`.

### Imports and path aliases

- The `@/*` alias maps to `./src/*`. Configured in both
  `tsconfig.json:4-6` and `vite.config.ts:9-11`. Always import via the alias:
  `import { Button } from "@/components/ui/button"` — never relative `../..`
  paths across the `src/` tree.
- `components.json` aliases mirror this: `components → @/components`,
  `ui → @/components/ui`, `utils → @/lib/utils`, `hooks → @/hooks`,
  `lib → @/lib`. Honor these when running `shadcn add`.

Import groups (consistent across files, though not linter-enforced):

1. React / react-dom
2. Third-party libs (`@base-ui/react/...`, `@dnd-kit/react`,
   `class-variance-authority`, `lucide-react`)
3. `@/components/...`
4. `@/hooks/...`
5. `@/lib/...`
6. `@/types` (type-only)

Use `import type { ... }` for type-only imports
(`App.tsx:15`, `peek-panel.tsx:19`).

### shadcn / Base UI primitive pattern

UI primitives in `src/components/ui/` are generated by the shadcn CLI on the
`base-nova` style and wrap `@base-ui/react/<primitive>`. The canonical pattern
(from `components/ui/button.tsx`):

```tsx
import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center …",
  {
    variants: { variant: { default: "...", outline: "...", … }, size: {...} },
    defaultVariants: { variant: "default", size: "default" },
  },
)

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
```

Rules:

- Always re-export both the component and its `cva` variants object so that
  callers can compose styles (`buttonVariants({ variant: "outline" })`).
- Always set `data-slot="<primitive>"` on the wrapper. Sibling primitives use
  this for adjacency selectors.
- Always pipe className through `cn(...)` so consumer overrides win the
  tailwind-merge conflict resolution.
- Type the props as `<Primitive>.Props & VariantProps<typeof variants>` —
  do not redeclare prop interfaces by hand.

### Tailwind v4 + theme tokens

All theme colors are CSS variables in `src/index.css` and exposed as Tailwind
utilities through the `@theme inline { … }` block:

```css
:root {
  --background: oklch(0.145 0 0);
  --foreground: oklch(0.985 0 0);
  --primary: oklch(0.985 0 0);
  --primary-foreground: oklch(0.205 0 0);
  --status-pending: #f59e0b;
  --status-progress: #3b82f6;
  /* … */
}

@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-primary: var(--primary);
  /* … */
}
```

Conventions:

- **Always reference theme tokens, never raw color values.** Use
  `bg-background`, `text-foreground`, `bg-card/60`, `text-muted-foreground`,
  `border-border` — not `bg-zinc-950` or `text-white`.
  (Counter-example: `agent-registry.tsx` still uses raw `zinc-*` classes; new
  components should not copy that.)
- Status colors are sourced via `STATUS_COLORS[status]` from `src/types.ts:67`,
  which resolves to `var(--color-status-pending)` etc. Components that paint
  status (kanban column header, task card glow) inject the value via inline
  `style={{ background: `linear-gradient(…, ${color}, …)` }}` because the
  color name is dynamic at runtime
  (`components/kanban/column.tsx:23`, `components/kanban/task-card.tsx:46`).
- Use `oklch(...)` for new theme colors; the existing palette is uniformly
  oklch except for the status accents.
- Custom utility classes live in `src/index.css` (e.g. `.atmosphere`,
  `.dot-grid` at `index.css:75-89`). Keep them small and themable.

### React component patterns

- **Functional components only.** No class components anywhere.
- **Named exports for components, default export only for `App`.**
  `App.tsx` uses `export default function App()`; everything else exports by
  name.
- Component props are declared as a top-level `interface FooProps` directly
  above the component:

  ```tsx
  interface BoardProps {
    teamName: string
    tasks: TasksByStatus
    onPeek: (taskId: string) => void
  }

  export function Board({ teamName, tasks, onPeek }: BoardProps) { … }
  ```

  (`components/kanban/board.tsx:8`).
- Local state is `useState`, side effects are `useEffect`, derived values use
  `useMemo` when the dependency cost is real
  (`peek-panel.tsx:63`).
- Refs use `useRef` typed explicitly: `useRef<{ x: number; y: number } | null>(null)`
  (`task-card.tsx:25`).
- Cross-tree state is shared via a single React context exposed by `App.tsx`:
  `TeamContext` + `useTeam()` hook (`App.tsx:23-31`). Don't reach for Redux /
  Zustand — the SSE-driven team snapshot is small and re-rendering top-down is
  fine.

### Data fetching

All HTTP calls live in `src/lib/api.ts` and target the `/api` prefix proxied
to the Python server (`vite.config.ts:17-21` proxies `/api` to
`http://localhost:8080` in dev). Pattern:

```ts
async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`)
  return res.json()
}
```

(`lib/api.ts:3`)

- Generic helpers (`post<T>`, `patch<T>`) for the verb, then per-endpoint
  named exports (`createTask`, `updateTask`, `addMember`, `sendMessage`).
- Always `encodeURIComponent` path segments.
- Errors throw; UI callers `.catch(console.error)` at the call site (e.g.
  `Board.onDragEnd`).

### Realtime: SSE via custom hook

The team snapshot is streamed over SSE. The hook lives at
`src/hooks/use-team-stream.ts`:

- Returns `{ data, isConnected }`; both are derived state on `useState`.
- Uses a `useRef` to dedupe identical consecutive payloads.
- Distinguishes SSE liveness (`isConnected`) from agent liveness — the latter
  is computed from `data.team.membersOnline` in `App.tsx:95`.
- Always close the `EventSource` in the effect cleanup.

### Tokens vs raw values cheat-sheet

| Use this | Not this |
|----------|----------|
| `bg-background`, `text-foreground` | `bg-zinc-950`, `text-white` |
| `border-border`, `bg-card`, `bg-muted/50` | `border-zinc-800`, `bg-zinc-900` |
| `text-muted-foreground` | `text-zinc-500` |
| `text-destructive` | `text-red-500` |
| `bg-primary text-primary-foreground` | `bg-blue-600 text-white` |
| Inline `style={{ color: STATUS_COLORS[s] }}` for status accents | hard-coded per-status hex |

---

*Convention analysis: 2026-04-28*
