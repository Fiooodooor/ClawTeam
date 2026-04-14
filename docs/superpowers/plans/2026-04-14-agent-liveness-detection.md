# Agent Liveness Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Distinguish "SSE connected" from "agents actually running" so users don't inject tasks into a team where no agent process exists.

**Architecture:** Backend probes tmux sessions for each team member (ClawTeam agents run in `tmux` windows inside a session named `clawteam-{team_name}`). Collector returns `isRunning` per member and a `membersOnline` count per team. Frontend demotes the existing "Live" pill to a quiet SSE dot and surfaces an explicit "N/M agents online" badge in the team header. When the count is 0, the badge turns destructive and acts as a warning.

**Tech Stack:** Python stdlib (`subprocess` + `shutil`), existing `TmuxBackend.session_name(team)` helper, React + shadcn Badge.

**Working directories:**
- Backend: `/home/jac/repos/ClawTeam/clawteam/board/`
- Frontend: `/home/jac/repos/ClawTeam/clawteam/board/frontend/`

---

## File Inventory

| File | Change |
|------|--------|
| `clawteam/board/liveness.py` (new) | `tmux_windows(team)` + `agents_online(team, members)` pure functions |
| `tests/board/test_liveness.py` (new) | Unit tests with subprocess mocked |
| `clawteam/board/collector.py` | Per-member `isRunning`; team summary adds `membersOnline` |
| `clawteam/board/frontend/src/types.ts` | Add `isRunning?: boolean` to Member and `membersOnline?: number` to TeamOverview |
| `clawteam/board/frontend/src/components/sidebar.tsx` | Relabel "Live" → "Stream", keep SSE semantics, less prominent |
| `clawteam/board/frontend/src/App.tsx` | New AgentsOnline badge in team header |

---

## Task 1: Backend liveness probe module

**Files:**
- Create: `clawteam/board/liveness.py`
- Create: `tests/board/test_liveness.py`

- [ ] **Step 1: Write the failing test**

Create `tests/board/test_liveness.py`:

```python
"""Tests for the board liveness helpers."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

from clawteam.board import liveness


def _fake_run(stdout: str = "", returncode: int = 0):
    def runner(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0] if args else [],
            returncode=returncode,
            stdout=stdout,
            stderr="",
        )
    return runner


def test_tmux_windows_returns_window_names_when_session_exists():
    with patch("shutil.which", return_value="/usr/bin/tmux"), \
         patch("subprocess.run", side_effect=_fake_run("leader\ncoder-1\n")):
        assert liveness.tmux_windows("my-swarm") == {"leader", "coder-1"}


def test_tmux_windows_returns_empty_when_session_missing():
    with patch("shutil.which", return_value="/usr/bin/tmux"), \
         patch("subprocess.run", side_effect=_fake_run(returncode=1)):
        assert liveness.tmux_windows("missing") == set()


def test_tmux_windows_returns_empty_when_tmux_not_installed():
    with patch("shutil.which", return_value=None):
        assert liveness.tmux_windows("any-team") == set()


def test_agents_online_counts_matching_members():
    with patch("clawteam.board.liveness.tmux_windows", return_value={"leader", "coder-1"}):
        online = liveness.agents_online("t", ["leader", "coder-1", "coder-2"])
    assert online == {"leader": True, "coder-1": True, "coder-2": False}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/jac/.clawteam-venv/bin/python -m pytest tests/board/test_liveness.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'clawteam.board.liveness'`

- [ ] **Step 3: Create `clawteam/board/liveness.py`**

```python
"""Detects which team members have a live tmux session/window."""

from __future__ import annotations

import shutil
import subprocess

from clawteam.spawn.tmux_backend import TmuxBackend


def tmux_windows(team_name: str) -> set[str]:
    """Return the set of window names in the team's tmux session.

    Returns an empty set when tmux is missing, the session does not exist,
    or any subprocess error occurs. Never raises.
    """
    if not shutil.which("tmux"):
        return set()

    session = TmuxBackend.session_name(team_name)
    try:
        result = subprocess.run(
            ["tmux", "list-windows", "-t", session, "-F", "#{window_name}"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (subprocess.TimeoutExpired, OSError):
        return set()

    if result.returncode != 0:
        return set()

    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def agents_online(team_name: str, member_names: list[str]) -> dict[str, bool]:
    """Map each member name → whether a tmux window of the same name is live."""
    windows = tmux_windows(team_name)
    return {name: name in windows for name in member_names}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/jac/.clawteam-venv/bin/python -m pytest tests/board/test_liveness.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add clawteam/board/liveness.py tests/board/test_liveness.py
git commit -m "feat(board): add tmux-based agent liveness probe"
```

---

## Task 2: Wire liveness into collector

**Files:**
- Modify: `clawteam/board/collector.py` (both `collect_team` and `collect_team_summary`)

- [ ] **Step 1: Add `membersOnline` to team summary**

Open `clawteam/board/collector.py`. At the top of the file add:

```python
from clawteam.board.liveness import agents_online
```

Then in `collect_team_summary`, right after the existing member-iteration loop that computes `total_inbox` and `leader_name`, add:

```python
        online_map = agents_online(team_name, [m.name for m in config.members])
        members_online = sum(1 for v in online_map.values() if v)
```

Update the returned dict to include `"membersOnline": members_online`:

```python
        return {
            "name": config.name,
            "description": config.description,
            "leader": leader_name,
            "members": len(config.members),
            "membersOnline": members_online,
            "tasks": tasks_total,
            "pendingMessages": total_inbox,
        }
```

- [ ] **Step 2: Add per-member `isRunning` and team-level count to `collect_team`**

In `collect_team`, just before the `members = []` list is built, add:

```python
        online_map = agents_online(team_name, [m.name for m in config.members])
```

Inside the `for m in config.members:` loop, add `isRunning` to `entry`:

```python
            entry = {
                "name": m.name,
                "agentId": m.agent_id,
                "agentType": m.agent_type,
                "joinedAt": m.joined_at,
                "memberKey": inbox_name,
                "inboxName": inbox_name,
                "inboxCount": mailbox.peek_count(inbox_name),
                "isRunning": online_map.get(m.name, False),
            }
```

At the end of the function, in the returned `team` block, add `membersOnline`:

```python
            "team": {
                "name": config.name,
                "description": config.description,
                "leadAgentId": config.lead_agent_id,
                "leaderName": leader_name,
                "createdAt": config.created_at,
                "budgetCents": config.budget_cents,
                "membersOnline": sum(1 for v in online_map.values() if v),
            },
```

- [ ] **Step 3: Update the overview fallback**

In `collect_overview`, the exception fallback constructs a synthetic dict. Add `membersOnline: 0` there too so the shape stays consistent:

```python
                result.append({
                    "name": name,
                    "description": meta.get("description", ""),
                    "leader": "",
                    "members": meta.get("memberCount", 0),
                    "membersOnline": 0,
                    "tasks": 0,
                    "pendingMessages": 0,
                })
```

- [ ] **Step 4: Sanity check: hit the live endpoint**

Run: `curl -s http://localhost:8080/api/overview | python3 -m json.tool | head -20`
Expected: each team now shows `"membersOnline": 0` (since no agents spawned yet).

Run: `curl -s http://localhost:8080/api/team/verify-test | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['team']['membersOnline'], [(m['name'], m['isRunning']) for m in d['members']])"`
Expected: `0 [('leader', False)]` (or similar).

- [ ] **Step 5: Commit**

```bash
git add clawteam/board/collector.py
git commit -m "feat(board): surface agent liveness in collector output"
```

---

## Task 3: Frontend types + UI

**Files:**
- Modify: `clawteam/board/frontend/src/types.ts`
- Modify: `clawteam/board/frontend/src/components/sidebar.tsx`
- Modify: `clawteam/board/frontend/src/App.tsx`

- [ ] **Step 1: Extend types**

Open `clawteam/board/frontend/src/types.ts`. Find the `Member` interface — add `isRunning?: boolean`. Find the interface describing `team` inside `TeamData` (it has `name`, `leaderName`, `description`, etc.) — add `membersOnline?: number`. Find `TeamOverview` — add `membersOnline?: number`.

Do not invent new fields. Do not change existing ones.

- [ ] **Step 2: Demote sidebar "Live" to a calmer "Stream" label**

Open `clawteam/board/frontend/src/components/sidebar.tsx`. Change the text of the status pill from `Live` / `Offline` to `Stream live` / `Stream offline`, keeping the same color logic. Replace the block:

```tsx
        <span className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
          {isConnected ? "Live" : "Offline"}
        </span>
```

with:

```tsx
        <span className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
          Stream {isConnected ? "live" : "offline"}
        </span>
```

- [ ] **Step 3: Add AgentsOnline badge in `App.tsx` team header**

Open `clawteam/board/frontend/src/App.tsx`. Add the Badge import at the top (alongside existing Button import):

```tsx
import { Badge } from "@/components/ui/badge"
```

Find the header's eyebrow line:

```tsx
                  <div className="flex items-center gap-3 text-[11px] font-medium uppercase tracking-[0.3em] text-muted-foreground">
                    <span>Swarm</span>
                    <span className="size-1 rounded-full bg-muted-foreground/60" />
                    <span className="font-mono normal-case tracking-normal">
                      {data.members.length} agents
                    </span>
                  </div>
```

Replace with:

```tsx
                  <div className="flex items-center gap-3 text-[11px] font-medium uppercase tracking-[0.3em] text-muted-foreground">
                    <span>Swarm</span>
                    <span className="size-1 rounded-full bg-muted-foreground/60" />
                    <span className="font-mono normal-case tracking-normal">
                      {data.members.length} agents
                    </span>
                    <span className="size-1 rounded-full bg-muted-foreground/60" />
                    {(() => {
                      const online = data.team.membersOnline ?? 0
                      const total = data.members.length
                      const allOnline = total > 0 && online === total
                      const noneOnline = online === 0
                      return (
                        <Badge
                          variant={noneOnline ? "destructive" : "secondary"}
                          className="gap-1.5 font-mono text-[10px] normal-case tracking-normal"
                        >
                          <span
                            className={
                              "size-1.5 rounded-full " +
                              (noneOnline
                                ? "bg-destructive-foreground/80"
                                : allOnline
                                ? "bg-emerald-400"
                                : "bg-amber-400")
                            }
                          />
                          {noneOnline
                            ? "No agents running"
                            : `${online}/${total} online`}
                        </Badge>
                      )
                    })()}
                  </div>
```

- [ ] **Step 4: Build**

Run (from `clawteam/board/frontend`):
`pnpm build`
Expected: build succeeds with no TS errors.

- [ ] **Step 5: Visual verify in browser**

Open http://localhost:8080. Select `verify-test`. Confirm:
- Sidebar bottom pill reads `Stream live` (not `Live`).
- Header shows a destructive Badge `• No agents running`.
- Launch agents via `clawteam launch verify-test` in another shell (or spawn a window manually: `tmux new-session -d -s clawteam-verify-test -n leader 'sleep 300'`), then refresh — Badge should flip to `1/1 online` with green dot.

- [ ] **Step 6: Commit**

```bash
git add clawteam/board/frontend/src/types.ts clawteam/board/frontend/src/components/sidebar.tsx clawteam/board/frontend/src/App.tsx
git commit -m "feat(board): show agents-online badge, soften SSE indicator"
```

---

## Self-review notes

- **Spec coverage:** 1) tmux probe = Task 1; 2) collector exposes data = Task 2; 3) UI splits SSE from agent liveness = Task 3. All three requirements from the brainstorm are covered.
- **Type consistency:** `membersOnline` (number) and `isRunning` (bool) names are identical across backend and frontend.
- **Fail-safe:** liveness probe swallows every subprocess failure (timeout, missing tmux, nonexistent session) and returns empty — never breaks the SSE stream.
- **Performance:** `tmux list-windows` runs once per team per collector call (every 2s via SSE), bounded at 2s timeout each. Two teams = max 4s additional latency worst case, in practice <50ms when tmux is local.
- **YAGNI:** no "agent last-seen" timestamps, no heartbeat files, no state diffs. If users later want "agent stopped at 12:03", that's a follow-up.
