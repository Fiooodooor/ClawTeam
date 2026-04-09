# Codebase Concerns

**Analysis Date:** 2026-04-28

Scope: live source on branch `board-enhancement` only. Findings resolved by
commits `00a094d`, `efc5f9c`, `1c9a422` (tmux-injection RCE hardening),
`a3b5910` (board "Add Agent" 400), and `427475a` (Plane integration removal)
have been dropped from the prior CONCERNS.md.

---

## Security Considerations

### Board message endpoint accepts attacker-controlled `from`

- Risk: Any client that can reach the board can impersonate any agent in the
  team's mailbox / event log.
- Files: `clawteam/board/server.py:226-246`, `clawteam/team/mailbox.py:72-128`
- What happens: `POST /api/team/<name>/message` reads JSON and calls
  `MailboxManager.send(from_agent=payload.get("from", "board-ui"), ...)`. The
  `from` value is forwarded straight into the persisted `TeamMessage` and the
  per-team event log (`{data_dir}/teams/<name>/events/evt-*.json`) with no
  identity check, no allow-list against `TeamConfig.members`, and no signing.
  The frontend at `clawteam/board/frontend/src/lib/api.ts:54-59` only sends
  `{to, content, summary}`, but a curl request can set
  `{"from":"leader","type":"plan_approved","to":"coder-1",...}` and inject a
  forged approval/idle/broadcast into another agent's inbox — and downstream
  agents have no way to tell it apart from a real peer message.
- Current mitigation: None. Default host is `127.0.0.1` (`clawteam/cli/commands.py:3514`),
  which limits exposure to the local machine; CORS `*` (see next item) means
  any browser tab on that machine can also send the request.
- Recommendations: (a) Drop the `from` field from the request body and derive
  it from a server-known sender id (e.g. always `"board-ui"`, or a
  per-board-session identity); (b) reject any client-supplied `from` that
  matches an existing member's `inbox_name_for(...)`; (c) gate write endpoints
  behind a loopback-only auth token written to `~/.clawteam/board.token` on
  first run.

### CORS `*` and zero authentication on the dashboard server

- Risk: Any process or browser tab on the host (or on the LAN, if `--host` is
  changed) can read team state and execute every write endpoint.
- Files: `clawteam/board/server.py:286, 308, 329, 367`,
  `clawteam/cli/commands.py:3510-3524`
- What happens: `BoardHandler` sets `Access-Control-Allow-Origin: *` on every
  JSON, SSE, and OPTIONS response, and does no authentication anywhere.
  Sensitive endpoints — `POST /api/team/<n>/task`, `/api/team/<n>/member`,
  `/api/team/<n>/message`, `PATCH /api/team/<n>/task/<id>` — accept any
  origin. The default bind is `127.0.0.1`, but `--host 0.0.0.0` makes the
  whole API world-readable/writable with no warning.
- Current mitigation: Default `host=127.0.0.1`. Proxy endpoint (`/api/proxy`)
  has SSRF allow-listing in `_normalize_proxy_target` (`server.py:50-70`).
- Recommendations: (a) Issue a random bearer token at server start and refuse
  requests without it; (b) replace `Access-Control-Allow-Origin: *` with a
  per-request echo of an allow-listed origin (or drop CORS entirely now that
  the React SPA is co-served at `/`); (c) refuse to bind a non-loopback host
  unless `--allow-remote` (or auth) is also passed.

### `.clawteam/` data directory not in `.gitignore` and already committed

- Risk: Project-local agent state — task contents, cost ledgers, lock files,
  team configs — are tracked in git and pushed to the remote. Future
  conversations, agent prompts, and budget data leak through commits.
- Files: `.gitignore` (the strings `clawteam` / `.clawteam` are absent),
  `clawteam/team/models.py:15-46` (`get_data_dir()` resolves to `./.clawteam`
  when present), `.clawteam/` (40+ tracked files, e.g.
  `.clawteam/tasks/board-test/task-*.json`,
  `.clawteam/costs/*/summary.json`, `.clawteam/costs/*/summary.json.lock`).
- What happens: `_find_project_data_dir()` walks up from cwd looking for a
  `.clawteam/` directory and uses it as the data root. The repo currently
  contains such a directory with real test team state, and `git ls-files
  .clawteam` returns 40+ entries. There is no rule in `.gitignore` to keep
  new state from being staged.
- Current mitigation: None.
- Recommendations: (a) Add `/.clawteam/` to `.gitignore`; (b) `git rm -r
  --cached .clawteam` to stop tracking the existing snapshot; (c) consider
  storing only the schema fixtures (e.g. `.clawteam/.gitkeep`) that the test
  suite genuinely needs.

### POST/PATCH bodies are read in full without a size cap

- Risk: A misbehaving or malicious client can send an arbitrarily large
  `Content-Length` and force the server to allocate it before any validation
  runs.
- Files: `clawteam/board/server.py:186, 209, 230, 257`
- What happens: Every write handler does
  `body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8")`
  and then `json.loads(body)`. There is no upper bound, no streaming, and no
  attempt to detect chunked transfer.
- Current mitigation: None.
- Recommendations: Cap `Content-Length` at e.g. 64 KB before reading; reject
  with 413 otherwise.

---

## Fragile Areas

### Two divergent agent-liveness mechanisms

- Files: `clawteam/board/liveness.py:11-40` (board-only path),
  `clawteam/spawn/registry.py:55-90` (registry path used by everything else)
- Why fragile: The board UI computes `isRunning` / `membersOnline` by listing
  tmux window names and matching them by string against `member.name`
  (`clawteam/board/collector.py:54, 81, 95`). Every other consumer
  (`clawteam/harness/conductor.py:22-27`, `clawteam/team/waiter.py:171-175`,
  `clawteam/store/file.py:218-236`, `clawteam/cli/commands.py:3161-3163`)
  uses `clawteam/spawn/registry.py::is_agent_alive`, which checks
  `pane_dead`, falls back to PID, and understands the `subprocess` and `wsh`
  backends. Concrete mismatches:
  - Subprocess- and wsh-backend agents always show `isRunning: false` on the
    board because they have no tmux window with their name.
  - Tmux agents whose window survived but whose foreground process dropped
    back to a shell still show `isRunning: true` on the board, while the
    registry correctly reports them dead (registry filters on
    `pane_current_command in {bash,zsh,sh,fish}`, board does not).
  - The board has no equivalent of `list_zombie_agents`, so long-running
    runaways are invisible to the UI.
- Safe modification: Have `clawteam/board/collector.py` call
  `clawteam/spawn/registry.py::is_agent_alive` per member instead of
  `agents_online()`, and reduce `clawteam/board/liveness.py` to a thin
  fallback when the registry is empty.
- Test coverage: `tests/board/test_liveness.py` only covers the
  string-matching path; nothing reconciles the two implementations.

### SSE thread-per-client handler holds an unbounded daemon thread for life

- Files: `clawteam/board/server.py:324-345` (handler),
  `clawteam/board/server.py:367` (`ThreadingHTTPServer`),
  `clawteam/board/frontend/src/hooks/use-team-stream.ts:21-44` (client opens
  one EventSource per mounted view)
- Why fragile: `ThreadingHTTPServer` (via `ThreadingMixIn`) spawns a new
  daemon thread per accepted connection with no upper bound. `_serve_sse`
  enters `while True: ... time.sleep(self.interval)` and only exits when
  `wfile.flush()` raises `BrokenPipeError` / `ConnectionResetError` /
  `OSError`. There is no idle timeout, no max-connections cap, no per-IP
  cap, and no heartbeat that would cause Python to notice a half-open
  client. Practical effects:
  - A leaked browser tab keeps a thread, an open file descriptor, and
    triggers a `collector.collect_team(...)` rebuild every `interval`
    seconds forever.
  - Each `collect_team` reload rebuilds the message history (200 events)
    and walks the workspace for conflicts (`collector.py:128-184`); with N
    stale clients this is N× the I/O the cache can absorb (the
    `TeamSnapshotCache` only deduplicates within `ttl_seconds`).
  - If the host is moved off `127.0.0.1`, there is no defence against a
    client opening hundreds of `/api/events/<team>` streams to exhaust file
    descriptors and CPU.
- Safe modification: (a) Cap concurrent SSE streams (e.g. a
  `BoundedSemaphore`); (b) detect client disconnect by polling
  `self.connection.recv(0, MSG_PEEK)` or by writing a `:keepalive\n\n`
  comment whose flush failure is the disconnect signal; (c) put the loop
  body on a wall-clock deadline (auto-close after N minutes, let the SPA
  reconnect via `EventSource`'s built-in retry).
- Test coverage: None — there is no test for thread lifetime, disconnect
  handling, or concurrent-client behaviour in `tests/test_board.py`.

### `team_name` reaches `BoardCollector.collect_team` without prior validation

- Files: `clawteam/board/server.py:135-146, 312-322`,
  `clawteam/board/collector.py:38-66, 68-201`,
  `clawteam/team/mailbox.py:41-46`
- Why fragile: The HTTP layer parses `team_name` out of the URL and passes
  it straight to `BoardCollector` / `MailboxManager`. The latter calls
  `validate_identifier(team_name, "team name")` and raises `ValueError`,
  but: (a) the exception bubbles up to `_serve_team` only if it happens
  during `collect_team`, which catches `ValueError` and returns a
  reasonable 404; (b) for `_serve_sse` the same `ValueError` is caught
  inside the loop (`server.py:338-339`) and the bad value sits in the URL
  forever, so the loop runs the same failing call every `interval`
  seconds with the same exception traceback being re-built each time.
- Safe modification: Call `validate_identifier(team_name, "team name")` at
  the top of `do_GET` / `do_POST` / `do_PATCH` and 400 immediately.

### Board write paths skip `MailboxManager.send` argument validation

- Files: `clawteam/board/server.py:225-246`, `clawteam/team/mailbox.py:72-128`
- Why fragile: The handler accepts `payload.get("type", "message")` and
  passes it as `msg_type=` to `mailbox.send`. `mailbox.send` declares the
  parameter typed as `MessageType`, but at runtime any string is forwarded
  to `TeamMessage(type=msg_type, ...)` and Pydantic raises `ValueError`
  only inside the constructor. The handler catches everything via `except
  Exception as e: self.send_error(400, str(e))`, which echoes raw
  exception text (often a multi-line Pydantic dump) back to the client and
  into stderr.
- Safe modification: Validate `msg_type` against `MessageType.__members__`
  up front; replace `except Exception` with a tighter
  `except (ValueError, KeyError)` and a stable error envelope.

---

## Tech Debt

### Identical "team_name parts split" routing repeated four times

- Files: `clawteam/board/server.py:182-247, 253-281`
- Issue: Each POST/PATCH handler re-parses `path.strip("/").split("/")`,
  re-checks `len(parts) == 4`, re-reads `Content-Length`, re-decodes the
  body, and uses an identical `try/except Exception → 400` block. The four
  branches differ only in their endpoint suffix and the `MailboxManager` /
  `TaskStore` / `TeamManager` call.
- Files: `clawteam/board/server.py:180-281`
- Impact: Every new endpoint copies the boilerplate (and its bugs — no
  Content-Length cap, broad `except Exception`, raw exception text in 400
  bodies). The handler is already 373 lines and growing.
- Fix approach: Extract a small dispatch table — `(method, regex) →
  callable(team_name, payload)` — and a `_read_json_body(max_bytes=65536)`
  helper that does size capping and JSON parsing.

### `BoardCollector.collect_team` swallows every exception per side-channel

- Files: `clawteam/board/collector.py:128-183`
- Issue: Cost summary, conflict scan, and event-log read are each wrapped
  in `try: ... except Exception: pass`. A real bug in `CostStore`,
  `detect_overlaps`, or `MailboxManager.get_event_log` is silently dropped
  and the field is omitted from the SSE payload, which the frontend then
  interprets as "no data".
- Impact: Hard to debug regressions — the user sees an empty cost panel,
  but there is no log line and the test suite passes because the failure
  path is never asserted.
- Fix approach: Replace with `except (FileNotFoundError, ValueError)` for
  the known-soft-fail cases and let everything else surface; add a
  lightweight logger.

### `BoardHandler` uses class-level `collector`/`team_cache` injection

- Files: `clawteam/board/server.py:120-127, 354-365`
- Issue: `serve()` mutates class attributes on `BoardHandler` before
  starting the server. Any second `serve()` call in the same process (e.g.
  a future test harness or library embedding) overwrites global state. The
  `team_cache` instance is shared across all requests but is invisible
  from the handler signature.
- Fix approach: Pass the collector + cache as constructor args via a
  `partial(BoardHandler, ...)` factory or replace `BaseHTTPRequestHandler`
  with a `Server` subclass that owns the collector.

---

## Test Coverage Gaps

### Board HTTP handlers are tested only for happy paths

- What's not tested: `clawteam/board/server.py` has no test for the
  message endpoint at all (`POST /api/team/<n>/message`), no test for
  attacker-controlled `from`, no test for oversize bodies, no test for
  team-name validation, and no test asserting that PATCH/POST refuse
  malformed JSON gracefully.
- Files: `tests/test_board.py` (covers proxy SSRF, member POST, task
  PATCH, snapshot cache, but not message send)
- Risk: Regressions in the impersonation surface or SSE lifetime won't be
  caught by CI.
- Priority: High (impersonation), Medium (SSE / size cap)

### No test reconciles the two liveness implementations

- What's not tested: Behaviour when an agent is in
  `clawteam/spawn/registry.py` but not in tmux (and vice versa).
- Files: `tests/board/test_liveness.py`,
  `tests/test_registry.py`
- Risk: The board can keep showing dead agents as online indefinitely
  without any test failure.
- Priority: Medium

### SSE handler has no lifetime test

- What's not tested: Client-disconnect handling, max-connections behaviour,
  whether `_serve_sse` actually exits when the socket closes, whether
  `team_name` validation is enforced before the loop starts.
- Files: `tests/test_board.py:263` exercises a single iteration via
  monkeypatching, but never the loop.
- Risk: Thread / FD leaks accumulate silently.
- Priority: Medium

---

## Scaling Limits

### `TeamSnapshotCache` is per-team but `BoardCollector.collect_team` is O(events × messages)

- Files: `clawteam/board/collector.py:128-150` (200-event cap on event-log
  read), `clawteam/team/mailbox.py:61-70`
- Current capacity: 200 most-recent events parsed and re-serialized on
  every cache miss; one cache miss per team per `interval` seconds.
- Limit: For active teams the event log grows without bound (each
  `MailboxManager._log_event` writes a new file under
  `{data_dir}/teams/<n>/events/evt-*.json`); the directory is `glob`'d
  every cache miss with `sorted(... reverse=True)`. At ~10⁵ events the
  directory listing becomes the dominant cost.
- Scaling path: Tail-only read (e.g. keep an offset file), or move the
  event log to an append-only ndjson file so `sorted(...)` over thousands
  of small files is no longer required.

### Per-connection daemon threads with no upper bound

- See "SSE thread-per-client" above.
- Current capacity: Whatever the OS allows.
- Limit: File-descriptor exhaustion / RAM per thread (~8 MB stack default).
- Scaling path: `BoundedSemaphore` + 503 on overflow, or migrate to
  `asyncio` / `aiohttp` for the SSE path.

---

*Concerns audit: 2026-04-28*
