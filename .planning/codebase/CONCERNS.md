# Codebase Concerns

**Analysis Date:** 2026-04-28

> Scope: `board-enhancement` branch. Findings derived directly from the
> live source under `clawteam/spawn/`, `clawteam/plane/`, `clawteam/board/`,
> and `clawteam/board/frontend/src/`. The previous codebase docs were
> stale and were not consulted.

## Tech Debt

**Tmux-injection hardening plan exists but is NOT applied:**
- Issue: A 600-line implementation plan (`docs/superpowers/plans/2026-04-15-tmux-injection-hardening.md`) describes the fix for a Critical RCE in `_inject_prompt_via_buffer`, but none of its steps are present in the live code.
- Files: `clawteam/spawn/tmux_backend.py:272-295` (`inject_runtime_message`), `clawteam/spawn/tmux_backend.py:621-668` (`_inject_prompt_via_buffer`)
- Evidence: `grep _pane_safe_to_inject clawteam/spawn/tmux_backend.py` returns nothing; `tests/test_tmux_injection.py` does not exist.
- Impact: All four issues the plan documents are still live in `main` of this branch (RCE, buffer name clobber, swallowed subprocess errors, brittle `session:window_name` targeting).
- Fix approach: Execute the existing plan as written. Until then, treat `inject_runtime_message` as untrusted and unsafe.

**Server URL routing handled by manual string-splitting:**
- Issue: `clawteam/board/server.py:131-178` and `:180-281` parse paths with hand-rolled `path.startswith(...)` / `path.endswith(...)` chains and tuple-length checks. Adding a route requires editing three places (`do_GET`, `do_POST`, `do_PATCH`) and risks misclassification (e.g., `/api/team/foo/task/extra` would 404 silently rather than route).
- Files: `clawteam/board/server.py`
- Impact: Brittle and easy to introduce shadowed routes. CORS/OPTIONS handling is also inconsistent (only present for PATCH).
- Fix approach: Replace stdlib BaseHTTPRequestHandler with a small router or move to FastAPI/Starlette under `httpx` (already a dependency under the `plane` extra).

**Two divergent agent-liveness mechanisms drift apart:**
- Issue: `clawteam/board/liveness.py:11-40` checks "tmux window with this name exists." `clawteam/spawn/registry.py:171-192` (`_tmux_pane_alive`) checks `pane_dead` and detects when the pane has dropped to a shell. The board uses the shallow check; task-lock-release uses the deeper one.
- Files: `clawteam/board/liveness.py`, `clawteam/spawn/registry.py`
- Impact: Dashboard reports "online" for a member whose CLI crashed and left the tmux window sitting at bash. HITL approval requests routed to that "online" member never get processed (see "False-positive liveness" under Known Bugs).
- Fix approach: Replace `clawteam/board/liveness.py:agents_online` with a call into `spawn.registry.is_agent_alive` per member, falling back to the window-name check only when no registry entry exists.

**Hand-rolled subprocess wrapping with `shell=True` in three places:**
- Issue: `clawteam/spawn/subprocess_backend.py:97-105`, `clawteam/events/hooks.py:90-100`, `clawteam/team/watcher.py:107-116` all execute pre-built shell strings via `subprocess.run(..., shell=True)`. Each takes a different path to assembling the command.
- Files: as above
- Impact: Any future contributor handling a new env-derived parameter risks unquoted interpolation. Today the parameters are sourced from controlled inputs (CLI args, validated identifiers), but the pattern is fragile.
- Fix approach: Centralize into `clawteam/spawn/cli_env.py` with a single helper that takes `argv: list[str]` plus optional pre/post hooks; never accept a pre-joined shell string from callers.

**Plane sync hook can create an infinite push/pull loop:**
- Issue: Webhook receiver calls `store.update(..., force=True)` (`clawteam/plane/webhook.py:71-77`, `:107`, `:111`), which fires `AfterTaskUpdate` (`clawteam/store/file.py:198-205`), which `register_sync_hooks` listens for and re-pushes to Plane (`clawteam/plane/__init__.py:15-31`), which causes Plane to fire another webhook…
- Files: `clawteam/plane/webhook.py`, `clawteam/plane/__init__.py`, `clawteam/store/file.py`
- Impact: Once Plane round-trips the change unmodified, the loop is effectively infinite. Currently mitigated by hand only — no `source` tag on the event, no last-writer suppression.
- Fix approach: Add a `source: str` field to `AfterTaskUpdate`, set it to `"plane-webhook"` from the receiver, and have `_on_task_update` skip events where `source.startswith("plane-")`. Or: pass a `suppress_events=True` flag through `store.update` for inbound-from-Plane writes.

## Known Bugs

**Board UI "Add agent" silently fails (TypeError swallowed):**
- Symptoms: Clicking "Add to Crew" in the dashboard returns a 400 with `TeamManager.add_member() missing 1 required positional argument: 'agent_id'`.
- Files: `clawteam/board/server.py:219`, `clawteam/team/manager.py:139-167`
- Trigger: Use the `+ Agent` button in `agent-registry.tsx`. The handler omits `agent_id`, the Python signature requires it positionally.
- Workaround: Add agents via `clawteam team add-member` CLI.
- Fix: Generate an `agent_id` in the server (e.g. `uuid.uuid4().hex[:12]`) and pass it as the third positional argument.

**Webhook approve/reject keyword matching is too loose:**
- Symptoms: A Plane comment containing the word "approve" anywhere — including "I do not approve of this approach", "approver should be assigned", "approve this later" — flips the task into `in_progress`. Same for "reject".
- Files: `clawteam/plane/webhook.py:96-98`
- Trigger: Any human comment on a tracked Plane issue.
- Workaround: None.
- Fix: Match a structured marker (e.g. require `/approve` or `/reject` at the start of a line) or a configurable command vocabulary.

**False-positive liveness on dashboard after CLI crash:**
- Symptoms: When a tmux window outlives its CLI, the agent-registry shows the member as "online" indefinitely.
- Files: `clawteam/board/liveness.py:11-40`
- Trigger: Any agent CLI exit that leaves the window alive (default tmux behaviour with `remain-on-exit on`, or any wrapper script that returns to bash).
- Workaround: `clawteam team cleanup <team>` or kill the window manually.
- Fix: see "Two divergent agent-liveness mechanisms" in Tech Debt.

**SSE handler holds a thread per client until the next client disconnect:**
- Symptoms: Each `/api/events/<team>` connection spins forever inside `time.sleep(self.interval)` (`clawteam/board/server.py:331-345`). `ThreadingHTTPServer` allocates one OS thread per request; that thread is parked indefinitely. Many tabs → many threads.
- Files: `clawteam/board/server.py:324-345`
- Trigger: Open the dashboard in N browser tabs.
- Workaround: Reload pages.
- Fix: Migrate the SSE endpoint to an async server (Starlette + `sse-starlette` or similar) or set a hard idle deadline that closes the stream after K cycles and lets the client reconnect.

**Plane sync `pull_all` deletes nothing but `push_all` rewrites everything:**
- Symptoms: Tasks deleted in ClawTeam are not removed from Plane. Tasks deleted in Plane are not removed from ClawTeam (mapping by `metadata["plane_issue_id"]`). Worse, `push_all` (`clawteam/plane/sync.py:62-77`) iterates all local tasks and unconditionally re-pushes; an old "completed" status mapped to a Plane state by `resolve_state_id` will overwrite richer Plane state (e.g. "Cancelled" → "completed").
- Files: `clawteam/plane/sync.py`
- Trigger: Manual sync invocation.
- Workaround: Avoid bulk operations; rely on per-task push from the event hook only.
- Fix: Track tombstones for deletions; have `pull_all` honor a `last_synced_at` cursor; teach the engine that some Plane states are terminal and should not be overwritten.

## Security Considerations

**CRITICAL — Tmux paste-into-shell RCE:**
- Risk: When a leader pane drops to a shell (because `claude`/`codex` exited), `_inject_prompt_via_buffer` (`clawteam/spawn/tmux_backend.py:621-668`) pastes raw runtime-notification text and presses Enter. If the message body contains shell metacharacters such as `$(...)` or backticks, they execute as the user that owns the tmux session.
- Files: `clawteam/spawn/tmux_backend.py:272-295`, `:621-668`
- Current mitigation: None in the code. The hardening plan exists but is unimplemented.
- Recommendations: Apply `2026-04-15-tmux-injection-hardening.md` before any further multi-agent demo. At minimum, refuse injection when `pane_current_command` is not in the agent-CLI allowlist.

**Webhook receiver binds 0.0.0.0 by default and signature is OPTIONAL:**
- Risk: `clawteam/plane/webhook.py:209` defaults `host="0.0.0.0"`. `clawteam/plane/webhook.py:174-178` only verifies `X-Plane-Signature` when `webhook_secret` is non-empty; the default `PlaneConfig.webhook_secret == ""` (`clawteam/plane/config.py:21`). Anyone on the network can POST `/`, create tasks, mutate task state with `force=True`, and inject HITL approve/reject messages into agent inboxes.
- Files: `clawteam/plane/webhook.py`, `clawteam/plane/config.py`, `clawteam/cli/commands.py:4784-4815`
- Current mitigation: None in the default path; the CLI never warns when `webhook_secret` is empty.
- Recommendations: Refuse to start when `webhook_secret == ""`. Default `host="127.0.0.1"`. Print a warning if the operator explicitly opts into 0.0.0.0 binding. Add HMAC timing-safe comparison test that exercises the empty-secret path.

**Plane API key + webhook secret stored unencrypted with default file mode:**
- Risk: `clawteam/plane/config.py:42-48` writes `plane-config.json` (containing `api_key`, `webhook_secret`) via `atomic_write_text`. `atomic_write_text` (`clawteam/fileutil.py:28-52`) uses `tempfile.mkstemp` which creates the file with mode 0600, but `os.replace` preserves the temp file's mode. Confirm with `stat`. The data dir resolution allows project-local placement (`.clawteam/` walked up from cwd, `clawteam/team/models.py:39-46`), so secrets can land inside any working tree.
- Files: `clawteam/plane/config.py`, `clawteam/fileutil.py:28-52`, `clawteam/team/models.py:15-46`
- Current mitigation: `mkstemp` defaults to 0600 (good). But `.gitignore` does NOT list `.clawteam/`, so a project-local data dir is at high risk of being committed.
- Recommendations: (1) Add `.clawteam/` to `.gitignore` shipped in the template. (2) On `clawteam plane setup`, refuse to write secrets into a data dir located inside a git work tree unless the user passes `--allow-in-repo`. (3) Document keychain-based options.

**Board API has no authentication and CSRF-friendly CORS:**
- Risk: `clawteam/board/server.py:286,308,329` set `Access-Control-Allow-Origin: *` on every response. POST /PATCH endpoints accept arbitrary state changes (create task, change owner, send message claiming any `from`). When the operator binds the board to anything other than `127.0.0.1` (CLI does support `--host`, `clawteam/cli/commands.py:3514`), every POST is exploitable cross-origin from any browser tab.
- Files: `clawteam/board/server.py:180-281`
- Current mitigation: Default bind is `127.0.0.1` — the only mitigation.
- Recommendations: Either (a) refuse any non-loopback bind, or (b) add a startup-generated bearer token printed to stderr that all `fetch()` calls must include, and tighten CORS to `null` / specific origin. The frontend also needs to send the token.

**Board can impersonate any agent in the message endpoint:**
- Risk: `clawteam/board/server.py:226-246` (`POST /api/team/<name>/message`) takes `from` straight from the JSON body (`payload.get("from", "board-ui")`) and writes it into the inbox. There is no allow-list against the team's actual member names.
- Files: `clawteam/board/server.py:226-246`
- Current mitigation: None.
- Recommendations: Force `from = "board-ui"` (or a fixed operator identity); reject body-supplied `from`. Or, validate that the supplied `from` is an existing member name.

**Approval-comment matching can be triggered by Plane attachments / quoted text:**
- Risk: `comment_html` is HTML; substring matching against `.lower()` hits matches inside `<a href="...approve...">`, image alt text, code blocks, and quoted prior comments. An attacker who can post a comment can flip any tracked task between `in_progress` and `blocked`.
- Files: `clawteam/plane/webhook.py:84-115`
- Current mitigation: Webhook signature (when configured) is the only barrier; given the default empty secret, the barrier is missing.
- Recommendations: Combine with the webhook-secret hardening above; switch to slash-command matching against the visible text (strip HTML first).

**Board `/api/proxy` SSRF surface, partially mitigated:**
- Risk: `_normalize_proxy_target` (`clawteam/board/server.py:50-70`) restricts hostnames to a small allow-list (`api.github.com`, `github.com`, `raw.githubusercontent.com`) and refuses redirects via `_NoRedirectHandler`. Loopback/private IPs are blocked. However, hostname checks happen pre-DNS, so DNS-rebinding to a `github.com`-resolving record under attacker control is not mitigated; the body returned from the GitHub README endpoint flows through `_normalize_proxy_target(download_url)` again, but the second resolution still trusts the response.
- Files: `clawteam/board/server.py:19-93`
- Current mitigation: Allow-list, redirect refusal, private-IP block.
- Recommendations: Resolve hostnames once and reuse the IP for the actual fetch; block when DNS resolves to RFC1918 / loopback / link-local addresses.

## Performance Bottlenecks

**SSE refreshes every team snapshot from disk every `interval` seconds:**
- Problem: `BoardCollector.collect_team` (`clawteam/board/collector.py:68-201`) re-reads every task JSON, every member's inbox count, every event log entry on each call. The `TeamSnapshotCache` (`clawteam/board/server.py:96-117`) only deduplicates concurrent tabs at the same instant.
- Files: `clawteam/board/server.py`, `clawteam/board/collector.py`, `clawteam/store/file.py:259-289`
- Cause: Filesystem-backed store + per-poll full rescan.
- Improvement path: Push diffs over SSE instead of full snapshots; subscribe to `AfterTaskUpdate` / `BeforeInboxSend` events and broadcast only deltas.

**Webhook handler re-instantiates `FileTaskStore` and scans all tasks per event:**
- Problem: `_handle_work_item_event` calls `store.list_tasks()` (`clawteam/plane/webhook.py:49-69`) for every webhook to find the task by `metadata.plane_issue_id`. With N tasks, every webhook is O(N) disk reads.
- Files: `clawteam/plane/webhook.py`, `clawteam/store/file.py:259-289`
- Cause: No reverse index from `plane_issue_id → task_id`.
- Improvement path: Maintain an index file `plane-id-index.json` updated atomically alongside task writes; the store already has a write lock.

**Frontend bundle is 100% client-rendered, ~190 lines but minified:**
- Problem: The Vite bundle (`clawteam/board/static/assets/index-G3o_UaVN.js`) ships React 19, dnd-kit, base-ui, and the full app on every page load. Initial paint waits for full JS download.
- Files: `clawteam/board/frontend/`, `clawteam/board/static/`
- Cause: Client-only SPA pattern.
- Improvement path: Acceptable for a localhost dashboard; only worth revisiting if the board ever hosts multiple users.

## Fragile Areas

**`clawteam/cli/commands.py` is 4819 lines:**
- Files: `clawteam/cli/commands.py`
- Why fragile: Every CLI subcommand lives in a single file; cross-cutting concerns (config loading, console output, JSON output) are duplicated inline. Renaming or relocating a helper requires diff review across thousands of lines.
- Safe modification: Add new subcommands at the end; never rename existing helpers without `git grep`.
- Test coverage: `tests/test_cli_commands.py` exists but cannot reasonably cover every path.

**`clawteam/spawn/tmux_backend.py` (704 lines) tightly couples spawn lifecycle, prompt detection, dialog dismissal:**
- Files: `clawteam/spawn/tmux_backend.py`
- Why fragile: Per-CLI special cases (`is_claude_command`, `is_codex_command`, …) interleave with generic readiness polling. Adding a new CLI requires touching `_confirm_workspace_trust_if_prompted`, `_dismiss_codex_update_prompt_if_present`, the readiness heuristic in `_wait_for_cli_ready`, and `spawn` itself.
- Safe modification: Mirror the pattern of an existing CLI (codex is the closest reference); add tests in `tests/test_spawn_backends.py`.
- Test coverage: Heavy mocking; per-CLI trust-prompt branches are exercised but the readiness-stabilization heuristic in `_wait_for_cli_ready` (lines 535-588) is not directly tested.

**Project-local data-dir discovery walks parents from cwd:**
- Files: `clawteam/team/models.py:15-46`
- Why fragile: Running `clawteam` from anywhere inside a project tree changes the data dir compared to running it from outside. If two projects share a parent directory containing `.clawteam/`, state bleeds between them.
- Safe modification: Always pass `--data-dir` (env: `CLAWTEAM_DATA_DIR`) when scripting.
- Test coverage: `tests/test_data_dir.py` exists; verify it covers the parent-walk behavior.

**Dashboard "Add agent" path generates no `agent_id` (and silently 400s — see Known Bugs).**

## Scaling Limits

**FileTaskStore — single advisory lock per team:**
- Current capacity: Light-to-moderate concurrency within a single team. Lock is process-wide (`fcntl.LOCK_EX`).
- Limit: Updates serialize team-wide. With many agents racing through `update`, throughput is capped by disk fsync latency.
- Files: `clawteam/store/file.py:54-75`
- Scaling path: The `task_store` config field is already a string ("file" today). Implement a Redis or SQLite store and switch via that field.

**Event log keeps every message forever:**
- Current capacity: Unbounded; `MailboxManager._log_event` (`clawteam/team/mailbox.py:48-59`) writes one JSON file per event with no rotation.
- Limit: Long-running teams accumulate inodes and slow down `get_event_log` (which globs and sorts on every call).
- Files: `clawteam/team/mailbox.py`, `clawteam/board/collector.py:128-150`
- Scaling path: Cap retention at N days or M files; compact older events to a daily JSONL file.

**ThreadingHTTPServer for the dashboard:**
- Current capacity: One thread per concurrent client.
- Limit: SSE streams park threads indefinitely (see "SSE handler holds a thread per client" under Known Bugs).
- Files: `clawteam/board/server.py:354-373`
- Scaling path: Move to an async HTTP server.

## Dependencies at Risk

**`httpx` is in the `plane` optional extra, but `clawteam/plane/__init__.py` is imported unconditionally by `clawteam/config.py`:**
- Risk: `clawteam/config.py:12` does `from clawteam.plane.config import PlaneConfig` at module import. If a user installs without the `plane` extra, this import still succeeds because `PlaneConfig` itself only depends on pydantic. However, `clawteam/plane/client.py` imports `httpx` at module load — calling any sync command will `ImportError` for users without the extra.
- Files: `clawteam/plane/client.py:7`, `clawteam/plane/sync.py`, `pyproject.toml`
- Impact: Confusing failure mode when Plane sync is referenced from any code path that imports `sync.py`.
- Migration plan: Either move `httpx` into the base dependency set or guard `client.py` imports with try/except and emit a clean "install with `pip install clawteam[plane]`" message.

**`@dnd-kit/react` is at `^0.4.0`:**
- Risk: Pre-1.0 API; minor versions can be breaking. The Kanban drag-drop in `clawteam/board/frontend/src/components/kanban/board.tsx` uses `isSortable`, `useSortable`, and the `DragDropProvider` API which may change.
- Files: `clawteam/board/frontend/package.json`, `clawteam/board/frontend/src/components/kanban/`
- Impact: Future `npm install` could break the board.
- Migration plan: Pin the version exactly (drop the caret) until `@dnd-kit/react` ships 1.0.

**`@base-ui/react` is at `^1.4.0`:**
- Risk: New library, small ecosystem. Components in `clawteam/board/frontend/src/components/ui/` (dialog, sheet, select) are thin wrappers over Base UI primitives.
- Files: `clawteam/board/frontend/src/components/ui/`
- Migration plan: Ensure component wrappers expose stable props so a future swap (Radix UI) doesn't ripple.

## Missing Critical Features

**No data-dir migration tool:**
- Problem: The branch introduces project-local `.clawteam/` discovery (`clawteam/team/models.py:39-46`). Users with state in `~/.clawteam/` who later create a project-local dir get split state with no merge path.
- Blocks: Adoption of project-local mode.

**No webhook secret rotation flow:**
- Problem: `clawteam plane setup` only sets the API key/URL; there is no command to set or rotate `webhook_secret`. To set it the user must edit `plane-config.json` by hand.
- Blocks: Operationally setting the only auth control on the webhook receiver.

**No way to deregister a Plane integration cleanly:**
- Problem: Setting `sync_enabled = false` is the only off switch. Tasks already carrying `metadata.plane_issue_id` will silently re-link if sync is re-enabled.
- Blocks: Switching between Plane projects safely.

**Dashboard cannot delete tasks or members:**
- Problem: UI exposes create/update; no DELETE handlers in `clawteam/board/server.py`.
- Blocks: Closing the workflow loop entirely from the UI.

## Test Coverage Gaps

**Tmux runtime injection has zero direct tests:**
- What's not tested: `_inject_prompt_via_buffer`, `inject_runtime_message`, `_render_runtime_notification`.
- Files: `clawteam/spawn/tmux_backend.py:272-295`, `:621-704`
- Risk: The Critical RCE has no regression coverage; even after the hardening plan lands, future refactors could re-introduce it.
- Priority: High.

**Plane webhook receiver has no end-to-end test for HTTP flow:**
- What's not tested: `PlaneWebhookHandler.do_POST`, signature failure paths, the optional-secret bypass, malformed JSON handling, the loop-back-into-`AfterTaskUpdate` scenario.
- Files: `clawteam/plane/webhook.py:165-203`
- Risk: Auth bypass and infinite-loop hazards rely entirely on code review.
- Priority: High.

**Board server endpoints lack handler-level tests:**
- What's not tested: POST `/api/team/<name>/member` (the Add Agent silent-failure bug), POST `/api/team/<name>/message` (the impersonation hole), the proxy SSRF allow-list edge cases.
- Files: `clawteam/board/server.py:180-281`
- Risk: Functional bugs ship undetected; security checks are not regression-tested.
- Priority: High.

**Frontend has no automated tests:**
- What's not tested: Anything. There is no `vitest`, `jest`, or Playwright config in `clawteam/board/frontend/`.
- Files: `clawteam/board/frontend/`
- Risk: SSE reconnection logic in `use-team-stream.ts`, drag-and-drop in `board.tsx`, save-on-blur in `peek-panel.tsx` are all untested.
- Priority: Medium for behaviour, High for the SSE auto-reconnect loop on `onerror`.

**Liveness divergence is not asserted:**
- What's not tested: That `clawteam/board/liveness.py:agents_online` agrees with `clawteam/spawn/registry.py:is_agent_alive` for the same target.
- Files: `clawteam/board/liveness.py`, `clawteam/spawn/registry.py`
- Priority: Medium.

**Plane sync cycle / loop is not tested:**
- What's not tested: That an inbound webhook does not cause an outbound push (or that the outbound push is suppressed by some marker).
- Files: `clawteam/plane/webhook.py`, `clawteam/plane/__init__.py`, `tests/test_plane_sync.py`
- Priority: High once the loop fix lands.

---

*Concerns audit: 2026-04-28*
