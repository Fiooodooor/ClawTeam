# External Integrations

**Analysis Date:** 2026-04-28

## APIs & External Services

**Project management (first-class on this branch):**
- **Plane** (`makeplane/plane`, self-hosted) — bidirectional task sync + human-in-the-loop (HITL) gate.
  - SDK/Client: custom `PlaneClient` over `httpx` — `clawteam/plane/client.py:41` (sync `httpx.Client`, 30 s timeout)
  - Auth: `X-API-Key` header from `PlaneConfig.api_key` (`clawteam/plane/client.py:50-54`)
  - Base URL pattern: `{cfg.url}/api/v1/workspaces/{workspace_slug}/...` (`client.py:56-58`)
  - Endpoints called: `projects`, `projects/{id}/states` (list/create), `projects/{id}/work-items` (list/get/create/update), `projects/{id}/work-items/{id}/comments` (list/create)
  - Sync engine: `PlaneSyncEngine` (`clawteam/plane/sync.py:23`) — `push_task`, `push_all`, `pull_all`. Mapping: ClawTeam `TaskStatus` ↔ Plane state group (`clawteam/plane/mapping.py:9-22`); preferred state-name resolution falls back to first state in matching group.
  - Sync hook: `register_sync_hooks` (`clawteam/plane/__init__.py:15`) subscribes to the in-process `EventBus` `AfterTaskUpdate` events and auto-pushes per-task changes.
  - Webhook receiver: stdlib `ThreadingHTTPServer` on port 9091 by default — `clawteam/plane/webhook.py:165` (`PlaneWebhookHandler`). Handles `event=issue` (created/updated work items) and `event=issue_comment` (approval/rejection by keyword: `approved`/`approve`/`lgtm` vs `rejected`/`reject`).
  - HITL routing: comments containing approve/reject keywords flip the matching task to `in_progress` / `blocked` and emit a `plan_approved` / `plan_rejected` mailbox message via `MailboxManager` to the task owner or team leader (`clawteam/plane/webhook.py:84-115, 137-162`).
  - Webhook signature: HMAC-SHA256 over the raw body with `PlaneConfig.webhook_secret`, verified via `hmac.compare_digest` (`clawteam/plane/webhook.py:19-21, 174-178`). When secret is empty, requests are accepted unauthenticated.
  - CLI surface: `clawteam plane setup`, `clawteam plane status`, `clawteam plane sync <team> [--direction push|pull|both]`, `clawteam plane webhook <team> [--port N]` — defined in `clawteam/cli/commands.py:4684-4815`.
  - Self-host bootstrap: `scripts/plane-docker-setup.sh` downloads `https://github.com/makeplane/plane/releases/latest/download/setup.sh`, runs the official installer (Docker Compose), default port `8082`, default install dir `~/plane-selfhost`.

**Model Context Protocol (MCP):**
- ClawTeam *exposes* (does not consume) an MCP server via `FastMCP` from the `mcp` package — `clawteam/mcp/server.py:13`.
- Tools registered from `clawteam/mcp/tools/`: `board`, `cost`, `mailbox`, `plan`, `task`, `team`, `workspace`. Console script: `clawteam-mcp`.

**GitHub (read-only proxy):**
- Board server proxies external README fetches through `/api/proxy?url=...` — `clawteam/board/server.py:73-93`.
- Allowlist enforced (`_ALLOWED_PROXY_HOSTS`): `api.github.com`, `github.com`, `raw.githubusercontent.com` only. HTTPS-only; rejects loopback, private, link-local, multicast, reserved IPs and `localhost`. Redirects are explicitly disabled (`_NoRedirectHandler`). `github.com/<owner>/<repo>` URLs are normalized to `api.github.com/repos/<owner>/<repo>/readme` and the resulting `download_url` re-validated.

**Agent CLIs (subprocess-launched, not API-called):**
- ClawTeam shells out to one of several local AI coding CLIs via the spawn adapters (`clawteam/spawn/adapters.py:106-172`):
  - `claude` / `claude-code` (Anthropic Claude Code)
  - `codex` / `codex-cli` (OpenAI Codex CLI)
  - `gemini` (Google Gemini CLI)
  - `kimi` (Moonshot Kimi CLI)
  - `qwen` / `qwen-code` (Alibaba Qwen Code CLI)
  - `opencode` (OpenCode CLI)
  - `nanobot` (Nanobot CLI)
  - `openclaw` (OpenClaw CLI)
  - `pi` (pi-coding-agent CLI)
- Each adapter knows the runtime's flag for non-interactive prompts, workspace flag, and `--skip-permissions`-style override (`--dangerously-skip-permissions`, `--dangerously-bypass-approvals-and-sandbox`, `--yolo`).
- ClawTeam holds no API keys for these providers — auth lives in the user's CLI install.

## Data Storage

**Databases:**
- None. ClawTeam is filesystem-only.

**File Storage:**
- Local filesystem under the resolved data dir (env `CLAWTEAM_DATA_DIR` → user-config `data_dir` → nearest project-local `.clawteam/` → `~/.clawteam/`). Directory walk implemented in `clawteam/team/models.py:15-46`.
- Atomic writes via `clawteam.fileutil.atomic_write_text` (used in `plane/config.py:48`, `transport/p2p.py:14`, etc.).
- Subdirectories observed under `.clawteam/`: `teams/`, `tasks/`, `costs/`, `workspaces/`, plus the new top-level file `plane-config.json`.
- The bundled Plane stack (when self-hosted via `scripts/plane-docker-setup.sh`) stores its own data in Docker volumes managed by Plane's compose file (independent of `.clawteam/`).

**Caching:**
- In-process TTL cache for board snapshots: `TeamSnapshotCache` (`clawteam/board/server.py:96`) — TTL = SSE poll interval (default 2 s). Lazy load outside the lock; latest result wins on race.
- In-process Plane state cache inside `PlaneSyncEngine._states` (`clawteam/plane/sync.py:33-38`) — populated on first lookup, never invalidated within the sync run.

## Authentication & Identity

**Auth Provider:**
- None for ClawTeam itself. The board server has no auth and binds to `127.0.0.1` by default.
- Plane API: API-key auth (`X-API-Key`) configured per project via `clawteam plane setup`, persisted in `.clawteam/plane-config.json`.
- Plane webhooks: HMAC-SHA256 with shared secret (`PlaneConfig.webhook_secret`).

**Agent identity:**
- Agents are identified by `agent_id` (UUID-like) and `name` within a team config; tmux window names mirror the member name (used by liveness detection).

## Monitoring & Observability

**Error Tracking:**
- None. Failures are logged via stdlib `logging` (e.g. `log.warning("Plane sync failed for task %s: %s", ...)` in `clawteam/plane/__init__.py:29`) or surfaced through Rich console output in CLI commands.

**Logs:**
- Stdlib `logging` module; module-level `log = logging.getLogger(__name__)` pattern in `clawteam/plane/sync.py:20`, `clawteam/plane/webhook.py:16`.
- Board HTTP handler suppresses default access logs for SSE endpoints (`clawteam/board/server.py:347-351`).
- No structured-log shipper, no APM agent.

**Metrics:**
- Per-team cost telemetry tracked locally via `clawteam.team.costs.CostStore` (input/output tokens, USD cents) and surfaced through `clawteam cost report`. Nothing is exported off-host.

**Activity visualization (optional):**
- `clawteam/board/gource.py` shells out to the native `gource` binary to render team activity from collected events + git history. No service dependency.

## CI/CD & Deployment

**Hosting:**
- ClawTeam is a CLI/SDK; no managed deployment. The board server runs locally on the developer machine.
- Self-hosted Plane runs in Docker Compose (operator-managed).

**CI Pipeline:**
- GitHub Actions — `.github/workflows/ci.yml`
  - `lint` job: Python 3.12, `ruff check clawteam/ tests/`
  - `test` job: matrix of `{ubuntu-latest, macos-latest} × {3.10, 3.11, 3.12}`, runs `pip install -e ".[dev]"` then `python -m pytest tests/ -v --tb=short`
- No frontend CI (board / website) is wired into the workflow.

## Environment Configuration

**Required env vars:** none for default operation.

**Optional env vars:**
- `CLAWTEAM_DATA_DIR` — override data directory (also settable via `--data-dir` CLI flag). Read in `clawteam/team/models.py:25` and `clawteam/cli/commands.py:64-66`.
- `CLAWTEAM_TRANSPORT` — `file` (default) or `p2p` (requires `pip install clawteam[p2p]`). Read implicitly by `clawteam/transport/` factory.

**Secrets locations:**
- Plane API key + webhook secret: `.clawteam/plane-config.json` (NOT in `.gitignore` — operators must avoid committing the project-local data dir).
- No other secrets touched by ClawTeam itself; agent-CLI provider keys live in those CLIs' own config (e.g. `~/.claude`, `~/.codex`, etc.).

## Webhooks & Callbacks

**Incoming:**
- `POST /` on the Plane webhook receiver (`PlaneWebhookHandler.do_POST`, `clawteam/plane/webhook.py:170`).
  - Default bind: `0.0.0.0:9091` (configurable via `clawteam plane webhook <team> --port N` or `PlaneConfig.webhook_port`).
  - Header: `X-Plane-Signature: <hex(hmac_sha256(body, secret))>` (verified when `webhook_secret` is set).
  - Supported events: `issue` (created/updated → mirror into ClawTeam task store), `issue_comment` (approval/rejection keywords → flip task status + dispatch HITL mailbox message).
  - Response: JSON `{action, ...}` describing the action taken (`created`, `updated`, `approved`, `rejected`, `skipped`, `ignored`).

**Outgoing:**
- Plane REST writes from `PlaneClient` (POST `work-items`, PATCH `work-items/{id}`, POST `work-items/{id}/comments`, POST `states`).
- `urllib.request` GETs to the GitHub allowlist (`api.github.com`, `raw.githubusercontent.com`) via the board's `/api/proxy` (`clawteam/board/server.py:73-93`).
- No outbound calls to Anthropic / OpenAI / Google / etc. — those go through the spawned agent CLIs, not from ClawTeam itself.

## Real-time Streams

**Server-Sent Events (board → browser):**
- Endpoint: `GET /api/events/<team>` — `clawteam/board/server.py:324`
- Content-Type: `text/event-stream`; CORS `*`; pushes a JSON team snapshot every `interval` seconds (default 2.0 s) using the shared `TeamSnapshotCache`.
- Client: `useTeamStream` hook in `clawteam/board/frontend/src/hooks/use-team-stream.ts:9` using browser `EventSource`. Tracks last payload to skip identical pushes.

**Agent liveness (board internal):**
- `clawteam/board/liveness.py:11` shells out to `tmux list-windows -t clawteam-<team> -F '#{window_name}'` to derive the set of live agents. Distinct from SSE liveness so the dashboard can show "stream connected" while reporting "0/N agents online".

## Inter-process Transports (internal)

**File transport (default):**
- Filesystem-backed mailboxes under `.clawteam/teams/<team>/inboxes/` (`clawteam/transport/file.py`). Atomic writes; lockless single-writer-per-file convention.

**P2P transport (optional):**
- ZeroMQ PUSH/PULL — `clawteam/transport/p2p.py:28`. PULL socket bound per agent, peer discovery via `peers/<agent>.json`, automatic fallback to `FileTransport` when a peer is unreachable. Activated via `CLAWTEAM_TRANSPORT=p2p` and the `p2p` extra (`pyzmq`).

**Tmux injection (HITL into running agent panes):**
- `clawteam/spawn/tmux_backend.py` + `clawteam runtime inject` / `clawteam runtime watch` (`commands.py:2040-2131`) push structured notifications into a live tmux pane so a running agent picks up new inbox messages without restart.

---

*Integration audit: 2026-04-28*
