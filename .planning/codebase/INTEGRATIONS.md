# External Integrations

**Analysis Date:** 2026-04-15

ClawTeam is a local-first multi-agent coordination CLI. It has no hosted backend — every integration listed below runs on the user's workstation, is reached over localhost, or is a CLI tool spawned as a child process. There are no first-party cloud services.

## APIs & External Services

### Plane (self-hosted project management)

**Status:** Parked. The board/kanban UI (`clawteam/board/`) replaced this flow, but the Plane code still ships as an optional integration. Its dependency lives in the `[plane]` extra (`pyproject.toml:38-40`), so core installs don't pull it in.

- **Purpose:** Bidirectional sync of ClawTeam tasks ↔ Plane work items; webhook-driven HITL (human-in-the-loop) triggers for agents.
- **Code:** `clawteam/plane/` — `client.py`, `sync.py`, `webhook.py`, `mapping.py`, `models.py`, `config.py`, `__init__.py`.
- **Integration method:** REST API via `httpx` (sync client, 30 s timeout). The `PlaneClient` (`clawteam/plane/client.py:41-76`) hits `{base_url}/api/v1/workspaces/{workspace_slug}/...` for projects, states, work items, comments.
- **Auth:** `X-API-Key` header (`clawteam/plane/client.py:50-54`). Values come from `PlaneConfig.api_key` stored in `<data_dir>/plane-config.json` (`clawteam/plane/config.py:26-48`). `api_key` may be blank for self-hosted instances that run open.
- **Config fields** (`clawteam/plane/config.py:13-23`): `url`, `api_key`, `workspace_slug`, `project_id`, `sync_enabled`, `webhook_secret`, `webhook_port` (default 9091), `state_mapping`.
- **Sync engine:** `PlaneSyncEngine` (`clawteam/plane/sync.py:23-40`) maps statuses via `plane_group_to_clawteam_status` and pushes on `AfterTaskUpdate` events (hook wiring: `clawteam/plane/__init__.py:15-31`).
- **Webhook receiver:** stdlib `ThreadingHTTPServer` at `clawteam/plane/webhook.py:9` listening on the configured port. Signature is verified with HMAC-SHA256 using `webhook_secret` (`clawteam/plane/webhook.py:19-22`). On `work_item` events it mirrors changes into `FileTaskStore` and emits internal `MessageType` events for HITL.
- **Priority/status mapping:** `_CLAWTEAM_TO_PLANE_PRIORITY` in `clawteam/plane/client.py:19-27` (low/medium/high/urgent; Plane's `none` folds back to `medium`).

### Anthropic Claude / Claude Code CLI

**Purpose:** The primary agent runtime. ClawTeam never calls the Anthropic API directly; it spawns the `claude` CLI inside a tmux window and injects the agent's prompt.

- **Integration method:** subprocess via `tmux new-window` (`clawteam/spawn/tmux_backend.py:130-141`). The command is the user's installed `claude` (or any compatible CLI); the adapter detects Claude with `is_claude_command(...)` at `clawteam/spawn/adapters.py:37-48` and appends `--dangerously-skip-permissions` when `skip_permissions=True` (the default).
- **System prompt injection:** when a system prompt is provided, `tmux_backend.py:96-98` inserts `--append-system-prompt <text>` before any `-p` argument. The per-agent task prompt is built by `build_agent_prompt(...)` in `clawteam/spawn/prompt.py:27-106` — identity block, workspace block, task body, cross-agent context, and the coordination protocol (pointing agents back at `clawteam task list|update`, `clawteam inbox send`, `clawteam cost report`).
- **Auth:** inherited from the user's shell environment. No key is read by ClawTeam itself — the spawned `claude` process handles `ANTHROPIC_API_KEY`.
- **Nesting fix:** when the leader is itself a Claude session, `tmux_backend.py:115` unsets `CLAUDECODE CLAUDE_CODE_ENTRYPOINT CLAUDE_CODE_SESSION` inside the pane so the child refuses-to-start guard is bypassed.
- **Alternate endpoints:** built-in presets in `clawteam/spawn/presets.py` wire `claude` against third-party Anthropic-compatible gateways (Moonshot, Zhipu, DeepSeek, MiniMax, Bailian, OpenRouter) by setting `ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_*_MODEL`, and a custom `base_url`. ClawTeam never sends requests here — it just exports env vars into the tmux pane before invoking `claude`.

### OpenAI Codex CLI (and other native CLIs)

**Purpose:** Optional alternate agent backend. Codex is not called via SDK — it's just another CLI binary that ClawTeam can spawn.

- **Integration method:** same tmux-spawn path. `is_codex_command(...)` detection in `clawteam/spawn/adapters.py:40-41` appends `--dangerously-bypass-approvals-and-sandbox` instead of Claude's flag.
- **Presets:** `openai-official` (`clawteam/spawn/presets.py:54-63`) binds `codex` to `OPENAI_API_KEY`. Additional native CLIs supported by `NativeCliAdapter` (`clawteam/spawn/adapters.py:20-80+`): `gemini`, `kimi`, `qwen`, `opencode`, `nanobot`, `pi`, `openclaw` — each with its own flag handling for skip-permissions, workspace, and prompt delivery.
- **Auth:** each CLI reads its own env var (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `MOONSHOT_API_KEY`, `DASHSCOPE_API_KEY`, `DEEPSEEK_API_KEY`, `ZHIPU_API_KEY`, `MINIMAX_API_KEY`, `OPENROUTER_API_KEY`). ClawTeam just forwards them.

### MCP (Model Context Protocol) servers

**Purpose:** Expose ClawTeam's team/task/mailbox/plan/board/cost/workspace operations as tools that can be called by agent processes (Claude Code, Codex, etc.) to coordinate without shelling out to the CLI.

- **Code:** `clawteam/mcp/` — `server.py`, `tools/*.py`, `helpers.py`, `__main__.py`.
- **Runtime:** `FastMCP("clawteam")` from the official `mcp` SDK (`clawteam/mcp/server.py:8-13`). The server is exposed as the `clawteam-mcp` console script (`pyproject.toml:44`) and runs over stdio (`mcp.run()` at `clawteam/mcp/server.py:32-33`).
- **Tools registered** (`clawteam/mcp/tools/__init__.py:28-55`): `team_*`, `task_*`, `mailbox_*` (send/broadcast/receive/peek/peek_count), `plan_*` (submit/get/approve/reject), `board_overview`, `board_team`, `cost_summary`, `workspace_agent_diff`, `workspace_file_owners`, `workspace_cross_branch_log`, `workspace_agent_summary`.
- **Error translation:** every tool is wrapped to rethrow through `translate_error(...)` (`clawteam/mcp/server.py:16-25`) so internal exceptions surface as MCP errors.
- **How agents connect:** the host agent (Claude Code, etc.) registers `clawteam-mcp` as a stdio MCP server in its own config. ClawTeam does not start the MCP server itself — the agent runtime does.

### Tmux (agent orchestration backend)

**Purpose:** Sole default runtime for spawned agents. Each agent gets its own named window inside a session called `clawteam-<team>` so you can attach and watch work happen live.

- **Code:** `clawteam/spawn/tmux_backend.py`, complemented by `clawteam/spawn/subprocess_backend.py` and `clawteam/spawn/wsh_backend.py` for headless modes.
- **Integration method:** plain subprocess calls to the `tmux` CLI (`shutil.which("tmux")` availability check at `clawteam/spawn/tmux_backend.py:56-57`). Key invocations: `tmux has-session` → `tmux new-session -d -s clawteam-<team> -n <agent>` or `tmux new-window -t clawteam-<team> -n <agent>` (`clawteam/spawn/tmux_backend.py:122-141`).
- **Lifecycle hooks:** `pane-exited` and `pane-died` are wired back to `clawteam lifecycle on-exit/on-crash` via `tmux set-hook` (`clawteam/spawn/tmux_backend.py:147-164`). This is how ClawTeam detects crashes and records abandoned tasks.
- **Liveness detection:** `clawteam/board/liveness.py:11-40` runs `tmux list-windows -t <session> -F "#{window_name}"` to compute per-member online status for the board.
- **Env sanitation:** only shell-safe env names (regex `[A-Za-z_][A-Za-z0-9_]*`) are exported, to work around WSL hosts that have names like `PROGRAMFILES(X86)` (`clawteam/spawn/tmux_backend.py:29,108-109`). Inherited `TERM=dumb` is rewritten to `xterm-256color` so interactive CLIs like Codex don't refuse to start (`tmux_backend.py:64-66`).

### Docker

**Purpose:** Required only by the Plane self-hosted deployment script. Not required by core ClawTeam.

- **Code:** `scripts/plane-docker-setup.sh` — downloads Plane's upstream installer from `github.com/makeplane/plane/releases/latest/download/setup.sh` and runs `docker compose up -d` on the resulting `plane-app/` checkout. Default port 8082.
- **How it's reached:** not at all by ClawTeam directly. The user runs the script, then feeds the resulting URL and API token into `clawteam plane setup --url http://localhost:8082 --api-key <token>`, which writes `<data_dir>/plane-config.json`.

### GitHub (board proxy endpoint)

**Purpose:** The board dashboard lets users paste a GitHub URL to render the repo's README inside the UI. To dodge browser CORS, the Python server proxies the fetch.

- **Code:** `clawteam/board/server.py:50-93, 147-162`.
- **Integration method:** server-side `urllib.request` fetch at `GET /api/proxy?url=<target>` (`clawteam/board/server.py:147-162`).
- **Allowlist** (`clawteam/board/server.py:19-23`): `api.github.com`, `github.com`, `raw.githubusercontent.com`. HTTPS only. `github.com/<owner>/<repo>` is rewritten to `https://api.github.com/repos/<owner>/<repo>/readme`, then the `download_url` from that JSON is fetched as raw text.
- **Safety guards:**
  - `_NoRedirectHandler` (`server.py:26-30`) rejects HTTP 3xx responses so the proxy can't be bounced to an unvetted host.
  - `_is_blocked_hostname` (`server.py:33-47`) denies localhost, loopback, private, link-local, multicast, and reserved IPs — blocking SSRF against the host's metadata service and internal network.
  - 10 s timeout on both the metadata and content fetches. `User-Agent: ClawTeam-Server` is sent.
- **Auth:** none — only anonymous public endpoints are reachable through the allowlist.

### Event bus (internal, with user-defined shell hooks)

**Purpose:** In-process publish/subscribe for lifecycle events (worker spawn/exit/crash, task create/update, message send/receive, plan approval, etc.). Primarily internal but becomes an integration surface when users wire shell hooks.

- **Code:** `clawteam/events/bus.py` (the `EventBus` class), `clawteam/events/types.py` (dataclass event types like `BeforeWorkerSpawn`, `AfterWorkerSpawn`, `WorkerExit`, `WorkerCrash`, `AfterTaskUpdate`, …), `clawteam/events/hooks.py` (user hooks), `clawteam/events/global_bus.py` (singleton accessor).
- **Delivery model:** synchronous, priority-ordered handlers (`clawteam/events/bus.py:42-60`); optional `emit_async` fire-and-forget via a `ThreadPoolExecutor`.
- **User-configurable hooks** (`clawteam/config.py:41-48` `HookDef` + `clawteam/events/hooks.py:18-60`): entries in `config.hooks` bind an `event` name to either:
  - `action = "shell"` → the `command` string is run via `subprocess` with the event dataclass serialized into env vars. This is how users plug ClawTeam into arbitrary external systems (curl a webhook, send a Slack message, kick a CI job, etc.).
  - `action = "python"` → a dotted module path resolved via `importlib` and called with the event.
- **Plane sync hook:** when Plane sync is enabled, `register_sync_hooks(...)` in `clawteam/plane/__init__.py:15-31` subscribes `AfterTaskUpdate` to push changes upstream.

## Data Storage

**Databases:** None. No SQLite, no Postgres, no Redis in core.

**File stores (local disk, JSON, atomic writes):**
- Tasks — `<data_dir>/tasks/<team>/task-<id>.json` (`clawteam/store/file.py:24-38`). Locking via `fcntl` on POSIX, `msvcrt` on Windows (`clawteam/store/file.py:14-17`).
- Teams — `<data_dir>/teams/<team>/config.json` (+ `spawn_registry.json`).
- Mailbox — `<data_dir>/teams/<team>/inboxes/<agent>/msg-<ts>-<uuid>.json` (`clawteam/team/mailbox.py:32-40`).
- Costs — `<data_dir>/costs/`.
- Workspaces — `<data_dir>/workspaces/` (git worktrees, see `clawteam/workspace/git.py`).
- Plane config — `<data_dir>/plane-config.json` (`clawteam/plane/config.py:26-28`).
- User config — `~/.clawteam/config.json` (fixed, not under `data_dir`; `clawteam/config.py:78-80`).

**Transport layer** (`clawteam/transport/`):
- `file` (default) — same JSON-on-disk approach as the mailbox. Cross-platform locking.
- `p2p` — optional ZeroMQ transport gated behind the `[p2p]` extra (`pyproject.toml:35-37`, `pyzmq>=25,<27`). Selected via `CLAWTEAM_TRANSPORT=p2p` or `config.transport`.

## Authentication & Identity

ClawTeam has no user auth of its own. It runs as a local CLI; identity is derived from:
- `CLAWTEAM_USER` env var (or `config.user`).
- Agent identity in `clawteam/identity.py` (reads `CLAWTEAM_AGENT_*` env vars injected by the spawn backend).

External service auth is delegated:
- The spawned agent CLI handles its own auth (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, …).
- Plane uses `X-API-Key` from local config (see above).
- GitHub proxy is anonymous public-only.

## Monitoring & Observability

- **Logging:** Python `logging` module, `log = logging.getLogger(__name__)` scattered through the codebase (e.g. `clawteam/plane/webhook.py:16`, `clawteam/plane/sync.py:20`). No structured log shipping.
- **Error tracking:** none (no Sentry, no Honeybadger).
- **Analytics:** none.
- **Real-time monitoring:** the board dashboard itself (`clawteam/board/`) — Server-Sent Events at `GET /api/events/<team>` push full team snapshots to the UI every ~2 s (`clawteam/board/server.py:324-345`). A tiny TTL cache (`TeamSnapshotCache` at `server.py:96-117`) shares snapshots across concurrent SSE clients.
- **Visualization:** optional `gource` binary integration in `clawteam/board/gource.py` — emits custom log format (`timestamp|username|type|path`) and shells out to `gource` to render an animated view of team activity.

## CI/CD & Deployment

**Hosting:** not applicable — distributed as a Python package.

**CI Pipeline:**
- GitHub Actions — `.github/workflows/ci.yml` (the only workflow).
- `lint` job: Python 3.12 on Ubuntu, `pip install ruff`, `ruff check clawteam/ tests/`.
- `test` job: matrix of `{ubuntu-latest, macos-latest} × {3.10, 3.11, 3.12}`, installs `.[dev]`, runs `pytest -v --tb=short`.
- No secrets required.

**Release:** no automated publish workflow; releases are manual `hatch build` / `twine upload` operations driven by the maintainer.

## Environment Configuration

**Required for base functionality:** none — ClawTeam runs with zero env vars and a fresh `.clawteam/` dir.

**Optional for features:**
- Plane: `<data_dir>/plane-config.json` (via `clawteam plane setup`).
- Agent CLIs: whichever auth env var the chosen CLI expects (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc.).
- Agent spawn overrides: `CLAWTEAM_DATA_DIR`, `CLAWTEAM_TRANSPORT`, `CLAWTEAM_DEFAULT_BACKEND`, etc. (see `STACK.md` → Configuration).

**Mock/stub:** tests redirect all file state to `tmp_path` via the autouse `isolated_data_dir` fixture (`tests/conftest.py:10-19`). There is no mocked Anthropic/OpenAI traffic because ClawTeam never calls those APIs directly — the spawn backend is simply not exercised in unit tests.

## Webhooks & Callbacks

**Incoming:**
- Plane → ClawTeam at `POST /` on the port in `PlaneConfig.webhook_port` (default 9091). Signature header verified with `hmac.new(secret, body, sha256).hexdigest()` compared via `hmac.compare_digest` (`clawteam/plane/webhook.py:19-22`). Handled events include `work_item` (`created`/`updated`/`deleted`) in `_handle_work_item_event` (`webhook.py:24-80+`). Active only when Plane sync is enabled.

**Outgoing:**
- None from ClawTeam itself. Users can fire outbound calls via shell hooks on event-bus events (see Event bus above), but nothing outbound is built in.

---

*Integration audit: 2026-04-15*
*Update when adding/removing external services*
