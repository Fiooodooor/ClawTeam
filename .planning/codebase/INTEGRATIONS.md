# External Integrations

**Analysis Date:** 2026-04-28

This snapshot reflects the post-Plane-removal `board-enhancement` branch.
There is no longer any project-management integration: the
`clawteam/plane/` Python package, its Typer sub-app, its
`extras_require["plane"]`, and all `tests/test_plane_*.py` files were
removed in commit `427475a`. ClawTeam currently has no first-party
integration with Plane, Linear, Jira, GitHub Issues, or any other
external task tracker — task state lives entirely in the file-backed
`TaskStore`.

## APIs & External Services

### Outbound HTTPS

**GitHub README proxy (board dashboard):**
- Single allow-listed proxy endpoint exposed at `GET /api/proxy?url=...`
  in `clawteam/board/server.py:147`.
- Allow-list: `api.github.com`, `github.com`, `raw.githubusercontent.com`
  (`_ALLOWED_PROXY_HOSTS`, `clawteam/board/server.py:19`).
- Hardening:
  - Forces `https` (`_normalize_proxy_target`, line 50).
  - Rejects redirects via a custom `urllib.request.HTTPRedirectHandler`
    (`_NoRedirectHandler`, line 26).
  - Blocks loopback / private / link-local / multicast IPs and the
    literal `localhost` (`_is_blocked_hostname`, line 33).
  - Re-validates the final URL after read to catch redirect-after-allow
    bypasses (line 79).
- Frontend usage: only `clawteam/board/frontend/src/components/modals/set-context.tsx`
  invokes `fetchProxy` (`clawteam/board/frontend/src/lib/api.ts:61`) so the
  user can pull a public README into the "Set Context" dialog.
- Auth: none — endpoint is for public, unauthenticated GitHub content only.

**Outbound model-provider HTTPS (driven by spawned agents, not by
ClawTeam itself):**
- ClawTeam never calls model APIs directly. It launches third-party CLIs
  (`claude`, `codex`, `gemini`, `kimi`, `qwen`, `opencode`, `nanobot`,
  `openclaw`, `pi`) and configures them via env vars.
- Built-in agent presets in `clawteam/spawn/presets.py:43` define
  `base_url` + `auth_env` pairs that get exported into the spawned
  shell. Endpoints referenced from the presets:
  - Anthropic API key only (no base_url override) — `anthropic-official`,
    auth env `ANTHROPIC_API_KEY` (line 46).
  - OpenAI API key only — `openai-official`, auth env `OPENAI_API_KEY`
    (line 56).
  - Google AI Studio (Gemini) — `google-ai-studio`, auth env
    `GEMINI_API_KEY` (line 66).
  - Vertex AI — `gemini-vertex`, env `GOOGLE_GENAI_USE_VERTEXAI=true`,
    `GOOGLE_CLOUD_LOCATION=global` (line 183) — relies on local gcloud ADC.
  - Moonshot Kimi — `https://api.moonshot.cn/anthropic` and
    `https://api.moonshot.cn/v1`, auth env `MOONSHOT_API_KEY` (line 76).
  - DeepSeek — `https://api.deepseek.com/anthropic`, auth env
    `DEEPSEEK_API_KEY` (line 99).
  - Zhipu GLM — `https://open.bigmodel.cn/api/anthropic` (CN) and
    `https://api.z.ai/api/anthropic` (global), auth env `ZHIPU_API_KEY`
    (lines 105, 112).
  - Alibaba Bailian — `https://dashscope.aliyuncs.com/apps/anthropic`
    and `https://coding.dashscope.aliyuncs.com/apps/anthropic`, auth env
    `DASHSCOPE_API_KEY` (lines 117, 128).
  - MiniMax — `https://api.minimaxi.com/anthropic` (CN) and
    `https://api.minimax.io/anthropic` (global), auth env
    `MINIMAX_API_KEY` (lines 138, 148).
  - OpenRouter — `https://openrouter.ai/api` (Claude/Gemini) and
    `https://openrouter.ai/api/v1` (Codex), auth env `OPENROUTER_API_KEY`
    (line 156).
- Profile resolver `clawteam/spawn/profiles.py:162` maps each agent
  basename to the env var its CLI reads:
  - `claude/claude-code` → base URL `ANTHROPIC_BASE_URL`, key
    `ANTHROPIC_AUTH_TOKEN`.
  - `codex/codex-cli` → base URL `OPENAI_BASE_URL`, key `OPENAI_API_KEY`.
  - `gemini` → base URL `GOOGLE_GEMINI_BASE_URL`, key `GEMINI_API_KEY`.
  - `kimi` → base URL `KIMI_BASE_URL`, key `KIMI_API_KEY`.

### Inbound HTTP

**Board dashboard HTTP server** (`clawteam/board/server.py`,
`ThreadingHTTPServer` started by `serve()` at line 354):
- Default bind `127.0.0.1:8080` (`clawteam/cli/commands.py:3513`).
- Routes (handler `BoardHandler`, line 120):
  - `GET /` and `GET /index.html` → static `index.html`.
  - `GET /assets/*` → Vite-built JS/CSS/maps from `clawteam/board/static/assets/`.
  - `GET /api/overview` → all-team summary.
  - `GET /api/team/<name>` → full team snapshot.
  - `GET /api/events/<name>` → SSE stream (`text/event-stream`), pushes
    cached snapshot every `interval` seconds.
  - `GET /api/proxy?url=...` → GitHub README proxy (described above).
  - `POST /api/team/<name>/task` → create task.
  - `POST /api/team/<name>/member` → add agent (omitting `agent_id` is
    allowed since fix in commit `a3b5910`).
  - `POST /api/team/<name>/message` → send mailbox message.
  - `PATCH /api/team/<name>/task/<id>` → update task fields.
  - `OPTIONS *` → CORS preflight (`Access-Control-Allow-Origin: *`).
- Rate limiting / auth: none. CORS is wide open. Server is intended for
  loopback-only operation.

### Inbound stdio

**FastMCP server** (`clawteam/mcp/server.py`):
- Entry point `clawteam-mcp` (`pyproject.toml:41`), wrapper module
  `clawteam/mcp/__main__.py`.
- Transport: stdio via `mcp.run()` from the `mcp` SDK.
- Tools registered (26 total) in `clawteam/mcp/tools/__init__.py`:
  team CRUD (`team_list`, `team_get`, `team_members_list`, `team_create`,
  `team_member_add`), tasks (`task_list`, `task_get`, `task_stats`,
  `task_create`, `task_update`), mailbox (`mailbox_send`, `mailbox_broadcast`,
  `mailbox_receive`, `mailbox_peek`, `mailbox_peek_count`), plans
  (`plan_submit`, `plan_get`, `plan_approve`, `plan_reject`), board
  (`board_overview`, `board_team`), cost (`cost_summary`), workspace
  (`workspace_agent_diff`, `workspace_file_owners`,
  `workspace_cross_branch_log`, `workspace_agent_summary`).
- Each tool function is wrapped in `_tool` (`clawteam/mcp/server.py:16`)
  which translates exceptions through `clawteam/mcp/helpers.py
  translate_error`.

## Data Storage

### Primary store

**File-backed JSON on disk:**
- Resolution order in `clawteam/team/models.py:15` (`get_data_dir`):
  1. `CLAWTEAM_DATA_DIR` env.
  2. `data_dir` field in `~/.clawteam/config.json`.
  3. Nearest `.clawteam/` walking up from `cwd` (project-local discovery
     introduced in commit `2f13883`).
  4. `~/.clawteam/`.
- Layout under the resolved data dir:
  - `teams/<team>/config.json` — `TeamConfig` (`clawteam/team/manager.py:24`).
  - `teams/<team>/inboxes/<inbox_name>/` — per-member mailbox JSONs
    (`clawteam/team/mailbox.py`).
  - `teams/<team>/peers/<agent>.json` — P2P transport peer registry
    (`clawteam/transport/p2p.py:22`).
  - `teams/<team>/spawn_registry.json` — agent process metadata used for
    liveness checking (`clawteam/spawn/registry.py:18`).
  - `tasks/<team>/` — task store backed by `FileTaskStore`
    (`clawteam/store/file.py`, dispatched from `clawteam/store/__init__.py`).
  - `costs/<team>/` — cost ledger (`clawteam/team/costs.py`).
  - `sessions/<team>/` — session persistence for agent resume.
  - `workspaces/<team>/` — git worktrees when the workspace feature is
    enabled.
- All writes go through `clawteam/fileutil.py atomic_write_text`
  (mkstemp + `os.replace`) and inbox/registry mutations use
  `clawteam/fileutil.py file_locked` for cross-process safety.
- All path joins are constrained by `paths.ensure_within_root` and team
  identifiers are validated against `_IDENTIFIER_RE = ^[A-Za-z0-9._-]+$`
  (`clawteam/paths.py:8`).

**Configuration store:**
- `~/.clawteam/config.json` (`clawteam/config.py:76`). Held separate from
  the `data_dir` so user-wide settings (presets, profiles, plugin list,
  hook list) survive switching between project-local data dirs.

### Plugin-extensible stores

**Task store backends** (`clawteam/store/__init__.py:8`):
- Resolution: `backend` arg → `CLAWTEAM_TASK_STORE` env → `task_store`
  field in config → `"file"`.
- Only `FileTaskStore` ships; the docstring notes redis/sql are
  potential future backends, but no other implementations exist.

**Transport backends** (`clawteam/transport/__init__.py:15`):
- `"file"` (default) — `FileTransport` in `clawteam/transport/file.py`,
  uses inbox directories under the data dir.
- `"p2p"` — `P2PTransport` in `clawteam/transport/p2p.py`, ZeroMQ
  PUSH/PULL with `FileTransport` fallback for offline peers; only loaded
  when the optional `p2p` extra is installed.
- Custom transports may register through `register_transport`.

### Caching

**In-memory snapshot cache (board SSE):**
- `TeamSnapshotCache` in `clawteam/board/server.py:96`, TTL = SSE push
  interval. Shared across HTTP handlers under a `threading.Lock`. No
  external cache — Redis/Memcached are not used.

### File storage (binary)

- No object storage. Gource video export writes to the local filesystem
  via `ffmpeg` (`clawteam/board/gource.py:363`).

## Authentication & Identity

**End-user auth:**
- None. ClawTeam is a single-user local CLI; there is no login system,
  no session token, no user database.
- The `user` field on a team member (`clawteam/team/models.py:96`) is a
  cosmetic identifier (defaults to `CLAWTEAM_USER` env var) used to
  scope inbox directory names.
- Agent identity helpers in `clawteam/identity.py`.

**Provider auth:**
- API keys for model providers are read from environment variables only
  (no token persistence inside the repo). Profile env-mapping happens in
  `clawteam/spawn/profiles.py:127` (`apply_profile`) using
  `os.environ.get(profile.api_key_env)`.

**Board dashboard auth:**
- None. Bound to `127.0.0.1` by default; CORS is wide open
  (`Access-Control-Allow-Origin: *` in
  `clawteam/board/server.py:288, 308, 329`). Anyone with network
  access to the bind address can read team state and POST/PATCH tasks.

## Process / Liveness Integrations

These are not third-party services, but they are external systems
ClawTeam shells out to. Three different liveness signals coexist:

**1. tmux liveness** (per-agent process check):
- `clawteam/spawn/registry.py:171` `_tmux_pane_alive` calls
  `tmux list-panes -t <target> -F "#{pane_dead} #{pane_current_command}"`
  and treats `pane_dead == 1` or a foreground shell (`bash/zsh/sh/fish`)
  as dead. Falls back to PID alive check if the tmux target is missing
  (e.g. after tile operations).

**2. Tmux-window-name liveness (board UI)**:
- `clawteam/board/liveness.py:11` `tmux_windows()` runs
  `tmux list-windows -t clawteam-<team> -F "#{window_name}"` and the
  collector marks each member as `isRunning` when its name appears in
  the window set (`clawteam/board/collector.py:81`).
- Distinct from the spawn-registry check — this is what populates
  `members[].isRunning` and `team.membersOnline` in the SSE payload.

**3. SSE liveness (transport-level, post-`908b8ab`)**:
- `clawteam/board/frontend/src/hooks/use-team-stream.ts` exposes
  `isConnected` driven by `EventSource.onopen` (true) and
  `EventSource.onerror` (false). The topbar pill in
  `clawteam/board/frontend/src/components/topbar.tsx:81` shows "Stream
  live" / "Stream offline" purely from this signal, independent of
  whether any agent is alive.
- The header agents-online badge in `clawteam/board/frontend/src/App.tsx:94`
  reflects the tmux-window signal and stays accurate even when the SSE
  stream is healthy but every agent has exited.

**Tmux-injection hardening (commits `00a094d`, `efc5f9c`, `1c9a422`)**:
- `_pane_safe_to_inject` in `clawteam/spawn/tmux_backend.py:672` runs
  `tmux display-message -p -t <target> "#{pane_current_command}"` and
  refuses injection unless the foreground command is in
  `_INJECT_SAFE_COMMANDS` (line 656: claude / codex / gemini / kimi /
  qwen / opencode / nanobot / openclaw / pi / node / python / python3).
  Blocks paste-buffer injection into a stray shell or sub-TUI that
  could execute `$(...)`.
- `_inject_prompt_via_buffer` (line 701) uses a per-call unique buffer
  name (`prompt-<agent>-<uuid8>`) so concurrent injections cannot clobber
  each other; every `tmux load-buffer / paste-buffer / send-keys` call
  is checked through `_run_tmux` (line 685) which raises on non-zero
  exit instead of silently swallowing failures.
- Spawn now records `pane_id` (e.g. `%42`) alongside the
  `session:window` target (`clawteam/spawn/tmux_backend.py:230`), and
  runtime injections target the stable `pane_id` first
  (`inject_runtime_message`, line 293) so window renames or tile moves
  do not break message delivery.

## Spawn-pipeline integrations

**Tmux backend** (`clawteam/spawn/tmux_backend.py`):
- Default backend (`default_backend = "tmux"` in
  `clawteam/config.py:58`).
- Creates session `clawteam-<team>` and one window per agent, named
  after the agent. Sets `pane-exited` and `pane-died` tmux hooks that
  call `clawteam lifecycle on-exit` / `on-crash`
  (`clawteam/spawn/tmux_backend.py:158`).

**Subprocess backend** (`clawteam/spawn/subprocess_backend.py`):
- POSIX + Windows. Launches `subprocess.Popen` with `shell=True`,
  installs an exit hook by chaining `lifecycle on-exit`.

**Wsh backend** (`clawteam/spawn/wsh_backend.py`):
- Targets TideTerm / WaveTerminal. JSON-RPC over Unix socket
  `~/.local/share/tideterm/tideterm.sock` (with fallback to
  `~/.local/state/waveterm/tideterm.sock`) using
  `clawteam/spawn/wsh_rpc.py WshRpcClient`. Methods used:
  `ControllerInputCommand`, `BlockInfoCommand`. Block lifecycle managed
  via the `wsh` CLI (`wsh blocks list --json`,
  `wsh deleteblock -b <block>`).

## Monitoring & Observability

**Error tracking:**
- None. No Sentry, Datadog, or equivalent SDK is imported anywhere
  under `clawteam/`.

**Logs:**
- CLI/Server output goes to stdout/stderr via `rich.Console` or stdlib
  `print`. Board SSE log lines are suppressed in
  `BoardHandler.log_message` (`clawteam/board/server.py:347`) to keep
  the console quiet.
- Per-agent activity is captured by tmux scrollback (visual) and by
  the file-based mailbox/event log
  (`MailboxManager.get_event_log`, called in
  `clawteam/board/collector.py:130`).

**Cost tracking:**
- Internal only — `clawteam/team/costs.py CostStore` aggregates per-team
  token / cost events into the `costs/<team>/` directory; surfaced via
  `clawteam cost ...` and the board `cost` payload
  (`clawteam/board/collector.py:152`).

**Visualization:**
- `clawteam board gource` shells out to the optional `gource` and
  `ffmpeg` binaries to render activity videos
  (`clawteam/board/gource.py`).

## CI/CD & Deployment

**CI:**
- GitHub Actions, single workflow `.github/workflows/ci.yml`.
  - `lint` job: `ruff check clawteam/ tests/` on Python 3.12.
  - `test` job: matrix `{ubuntu-latest, macos-latest} × {3.10, 3.11, 3.12}`,
    runs `pip install -e ".[dev]"` + `python -m pytest tests/ -v --tb=short`.

**Hosting / deployment:**
- Not applicable. Distribution is a Python wheel (Hatchling) installed
  by end users.

**Marketing site:**
- `website/` (separate `package.json` at repo root) builds a Vite SPA;
  no deployment configuration is committed to the repo.

## Environment Configuration

**Required environment variables (functional):**
- None are strictly required at startup. ClawTeam runs entirely off the
  resolved data directory, falling back to `~/.clawteam/`.
- Any model-provider env (e.g. `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
  …) is required only for the matching spawned agent CLI.

**Common environment variables (operational):**
- See STACK.md → "Environment variables" for the full list registered
  in `clawteam/config.py:103`.

**Secrets location:**
- ClawTeam neither reads nor stores any secret directly. Secrets sit in
  the user's shell environment, in `~/.clawteam/config.json` only when
  the user pastes them into a profile (no built-in encryption), or in
  agent CLIs' own credential stores (e.g. `~/.config/anthropic/`).
- The repo's `.gitignore` ignores `.env` at the root (line 9). The
  scratch script `scripts/openclaw_worker.sh` reads from `.env` files
  if present but never commits them.

## Webhooks & Callbacks

**Incoming:**
- None. The board HTTP server has no webhook routes (the previous Plane
  webhook receiver was removed alongside the Plane subpackage in
  commit `427475a`).

**Outgoing:**
- None. ClawTeam emits internal events through
  `clawteam/events/global_bus.py get_event_bus()` (e.g.
  `AfterWorkerSpawn` from `clawteam/spawn/tmux_backend.py:267`), but
  the bus is in-process only — there is no HTTP push, no message
  broker, no outbound webhook delivery.

---

*Integration audit: 2026-04-28*
