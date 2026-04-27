# Codebase Concerns

**Analysis Date:** 2026-04-15

## Critical

**Shell injection via tmux paste-buffer:**
- Files: `clawteam/spawn/tmux_backend.py:621-668` (`_inject_prompt_via_buffer`), `clawteam/spawn/tmux_backend.py:670-704` (`_render_runtime_notification`)
- Impact: Paste-buffer writes the rendered notification to the tmux pane and submits it with two `Enter` keys. If the leader's Claude process died and the pane is at a `bash`/`fish` prompt, any incoming message summary or evidence containing `$(...)`, backticks, or `>` redirects executes as a shell command in the agent's cwd. The notification renderer only XML-escapes (`xml.sax.saxutils.escape` at line 687/692/698), which does not neutralize shell metacharacters. Attack path: a worker (or anything that can `clawteam inbox send`) sends a message, the leader's Claude has crashed, the message runs as shell.
- Fix: Detect pane readiness (prompt fingerprint) before paste and abort injection if the Claude TUI is not detected; alternatively wrap the payload in a bracketed-paste sequence or pipe through a tool that cannot interpret shell syntax.

## Important

**Routing policy does same-pair throttling only:**
- Files: `clawteam/team/routing_policy.py:93-156` (`DefaultRoutingPolicy.decide`), `clawteam/team/routing_policy.py:292-294` (`_route_key` = `"{source}->{target}"`)
- Impact: Throttle key is per source->target pair with a hardcoded 30s window. No per-recipient cap, no global cap, no priority-aware bypass. N workers broadcasting to the leader each inject immediately (different pair keys). A medium-priority `message` that lands at t=0 can delay a later `shutdown_request` from the same source until t=30s even though `_priority_for_message` (`clawteam/team/router.py:113-118`) marks shutdown high.
- Fix: Add a per-target token bucket + priority-aware bypass that flushes high-priority envelopes through the throttle.

**`dedupe_key` is computed but never used:**
- Files: `clawteam/team/router.py:65` (sets `dedupe_key`), `clawteam/team/routing_policy.py:380` (sets aggregate `dedupe_key`); no reader anywhere in `routing_policy.py`
- Impact: Duplicate `request_id` (e.g., client retry after timeout) produces duplicate injections; policy state carries the field but never compares it against recent events.
- Fix: Check `dedupe_key` against a bounded recent-events set in `decide()` and short-circuit duplicates.

**InboxWatcher consumes messages destructively:**
- Files: `clawteam/team/watcher.py:56` (`self.mailbox.receive(...)`), `clawteam/team/mailbox.py:186-207` (`receive` uses `consume=True` / acks via `ClaimedMessage`)
- Impact: Any competing caller of `clawteam inbox receive` (including an instruction in the leader's own prompt) races the watcher; whichever process acks first wins and the other sees nothing. The ack is unconditional on parse success, so even a transport that later fails mid-dispatch loses the message.
- Fix: Introduce a peek+claim+commit protocol where the ack only fires after the router acknowledges successful injection.

**Two `team start` invocations = two watchers racing on `runtime_state.json`:**
- Files: `clawteam/team/routing_policy.py:258-272` (`read_state`), `clawteam/team/routing_policy.py:274-290` (`_save_state`), `clawteam/cli/commands.py:1302-1315` (watcher spawn)
- Impact: Read-modify-write on `runtime_state.json` is atomic at the filesystem level (`os.replace`) but not transactional across readers. Two watchers reading near-simultaneously both compute decisions from the same baseline and then overwrite each other; one throttle decision is lost and a second injection fires that should have been aggregated.
- Fix: Wrap state access in a POSIX `fcntl.flock` (or equivalent) file lock, or refactor to a single owner process per team.

**Watcher lifecycle missing:**
- Files: `clawteam/cli/commands.py:1302-1315` (`_sp.Popen(..., stdout=DEVNULL, stderr=DEVNULL, start_new_session=True)`), `clawteam/cli/commands.py:1656-1671` (`team_cleanup`) and `clawteam/team/manager.py:191-221` (`TeamManager.cleanup`)
- Impact: The detached watcher inherits no supervision. Nothing tracks its PID, nothing polls the tmux session, nothing kills it during `team cleanup`. After cleanup it keeps polling inboxes; the inbox directory auto-creates on next receive, silently resurrecting the team dir with empty config references.
- Fix: Write a PID file on watcher launch and have both `team cleanup` and a periodic tmux-session probe terminate it.

**Duplicate / renamed tmux windows break injection silently:**
- Files: `clawteam/spawn/tmux_backend.py:272-295` (`inject_runtime_message`), `clawteam/spawn/tmux_backend.py:621-668` (`_inject_prompt_via_buffer`)
- Impact: Target is built as `clawteam-{team}:{agent_name}`. `list-panes` is checked (line 278), but `load-buffer`, `paste-buffer`, `send-keys`, and `delete-buffer` never check their return codes (lines 640-666, all with `stdout=PIPE, stderr=PIPE` and no `check=True`). If the user renamed a pane or has a stale duplicate window, the buffer paste returns non-zero and `_inject_prompt_via_buffer` still returns `None`, which the caller treats as success. The route is then marked `injected` in `runtime_state.json` although no agent received it.
- Fix: Check each subprocess return code and raise a specific exception captured by `inject_runtime_message` so the policy records a real failure.

**Missing or duplicate `lead_agent_id`:**
- Files: `clawteam/cli/commands.py:1254-1258` (linear scan with silent empty fallback), `clawteam/team/manager.py:140-167` (`add_member` only rejects duplicate `(name, user)`, not duplicate `agent_id`)
- Impact: If `lead_agent_id` does not match any member (typo, config drift), `leader_name` stays empty: `team_start` skips the watcher (line 1303 guards on `leader_name`), prompts are built with `leader_name=""` (line 1276), and downstream templates embed the empty string. `add_member` has no guard against re-adding the same `agent_id` under a different name, so the scan at line 1255 can match the wrong member.
- Fix: Validate `lead_agent_id` against current members inside `TeamManager.add_member` / `create_team` and fail loudly in `team_start` when no leader is resolved.

**Claimed-before-routing lossy path:**
- Files: `clawteam/team/mailbox.py:174-184` (`_parse_claimed_messages` calls `item.ack()` at line 182 before returning), `clawteam/team/watcher.py:56-72` (watcher routes after `receive` returned; any router exception is caught to a warn)
- Impact: The message is acked (and thus deleted in the file transport) the moment JSON parsing succeeds. If `route_message` then throws mid-dispatch (e.g., tmux invocation failure, policy IO error), the watcher logs a warning and the message is gone from the inbox — only the event log at `teams/{team}/events/evt-*.json` retains it, and nothing replays events.
- Fix: Keep the claim open until `route_message` returns success; quarantine on failure so the message is either redelivered or examined.

**Hook-triggered cascade risk:**
- Files: `clawteam/events/hooks.py:77-102` (`_make_shell_handler` runs arbitrary `subprocess.run(command, shell=True, ...)` with event data in env)
- Impact: Shell hooks typically call back into `clawteam` (e.g., post a status on `AfterInboxReceive`), which emits more events, which re-fire hooks. No loop detection, no depth limit, no per-event hook cooldown. A trivially misconfigured hook that reacts to `AfterInboxReceive` by sending a message creates an infinite amplification loop until the 30s `subprocess.run` timeout happens to break it.
- Fix: Track a per-process event depth counter and short-circuit hook execution past a depth threshold.

## Minor

**Unbounded event-log growth:**
- Files: `clawteam/team/mailbox.py:48-59` (`_log_event` writes `teams/{team}/events/evt-{ms}-{uuid}.json` per send/broadcast); no pruning anywhere; `team cleanup` at `clawteam/team/manager.py:192-221` only removes the team dir as a whole.
- Impact: Long-running teams accumulate one JSON file per message forever; directory listings and tooling that walks `events/` slow down linearly.
- Fix: Add retention by count or age in `_log_event` (or a separate compaction pass).

**Unbounded `pendingEnvelopes` in runtime_state during throttling:**
- Files: `clawteam/team/routing_policy.py:321-340` (`_append_pending` stores the full envelope dict on every buffered message), `clawteam/team/routing_policy.py:332-336` (only `pendingSummaries` slices to `_PENDING_SUMMARY_LIMIT`)
- Impact: A stuck route (target never flushes) grows `pendingEnvelopes` without bound, bloating `runtime_state.json` and slowing every read-modify-write cycle.
- Fix: Cap `pendingEnvelopes` to a max (oldest-dropped or collapsed) mirroring the summary cap.

**Content-based idle lookalikes get no special handling:**
- Files: `clawteam/team/router.py:113-118` (`_priority_for_message` dispatches on `MessageType` only)
- Impact: A `message` envelope whose body is effectively an idle/blocker notification is routed as medium and throttled like chatter.
- Fix: Add lightweight content heuristics (or require the sender to use `MessageType.idle`) before assigning priority.

**Frontend bundle size — no code splitting:**
- Files: `clawteam/board/frontend/vite.config.ts` (no `rollupOptions.output.manualChunks`), `clawteam/board/frontend/src/components/` (large flat import tree)
- Impact: `pnpm build` emits ~535 KB (gzip ~174 KB) as a single chunk; page load blocks on the whole app even for the minimal summary view.
- Fix: Add `manualChunks` (split shadcn, charts, and kanban) plus `React.lazy` for routes.

**Plane integration parked but still ships:**
- Files: `clawteam/plane/client.py`, `clawteam/plane/config.py`, `clawteam/plane/mapping.py`, `clawteam/plane/models.py`, `clawteam/plane/sync.py`, `clawteam/plane/webhook.py`, `scripts/plane-docker-setup.sh`, `tests/test_plane_client.py`, `tests/test_plane_config.py`, `tests/test_plane_integration.py`, `tests/test_plane_mapping.py`, `tests/test_plane_models.py`, `tests/test_plane_sync.py`, `tests/test_plane_webhook.py`
- Impact: Decision is to keep for now; the module is unused but carries imports, test runtime, and dependency churn; contributors must keep it passing on every refactor.
- Fix: Either wire it into a feature flag + CI-only test lane, or delete behind a branch.

**`agent-registry.tsx` skipped the shadcn/token migration:**
- Files: `clawteam/board/frontend/src/components/agent-registry.tsx:40,41,42,45,50,60,67,68,78,83,95`
- Impact: Inner content still uses `zinc-*` hardcoded palette classes instead of the semantic tokens that the rest of the board adopted in commit `0afcc9b`. Theme switches won't touch this component; future palette edits need a second pass.
- Fix: Replace `zinc-*` hardcodes with the semantic tokens (`border-border`, `bg-muted`, `text-muted-foreground`, etc.) used in the other components.

---

*Concerns audit: 2026-04-15*
*Update as issues are fixed or new ones discovered*
