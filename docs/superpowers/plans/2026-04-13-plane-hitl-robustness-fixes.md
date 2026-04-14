# Plane HITL Robustness Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 7 gaps in the Plane integration so it covers the complete vibe-coding HITL workflow: plan tasks in Plane, approve them, track status (Planned → In Progress → Completed → Verified), auto-sync bidirectionally, and notify the leader on all board changes.

**Architecture:** All fixes are surgical changes to existing files. No new modules needed. The `verified` status is added to the enum and mapping. Script paths align with the new CWD-based `get_data_dir()`. The webhook bug gets a one-line fix. Auto-sync hooks are wired into CLI startup. Leader notifications fire on all webhook state changes, not just approvals.

**Tech Stack:** Python 3.10+, Typer CLI, Pydantic, httpx, ClawTeam event bus, Plane REST API v1.3.

---

## File Structure

```
clawteam/team/models.py          — add `verified` to TaskStatus enum
clawteam/plane/models.py         — (no changes)
clawteam/plane/mapping.py        — add `verified` to all mapping dicts
clawteam/plane/webhook.py        — fix state_name bug, add leader notification on all state changes
clawteam/plane/__init__.py       — add AfterTaskCreate subscription
clawteam/plane/config.py         — (no changes, already uses get_data_dir)
clawteam/plane/sync.py           — (no changes)
clawteam/events/types.py         — add AfterTaskCreate dataclass
clawteam/store/file.py           — emit AfterTaskCreate after create
clawteam/cli/commands.py         — wire register_sync_hooks on sync/webhook, add `plane add-agent` command
scripts/open-board.py            — fix path to use CWD
scripts/plane-docker-setup.sh    — fix path to use CWD, seed Verified state

tests/test_plane_mapping.py      — add verified mapping tests
tests/test_plane_sync.py         — update mock for new status
```

---

### Task 1: Fix script path consistency

**Files:**
- Modify: `scripts/open-board.py:13`
- Modify: `scripts/plane-docker-setup.sh:180`

- [ ] **Step 1: Fix open-board.py fallback path**

In `scripts/open-board.py`, change line 13 from:
```python
CONFIG_PATH = Path(os.environ.get("CLAWTEAM_DATA_DIR", Path.home() / ".clawteam")) / "plane-config.json"
```
to:
```python
CONFIG_PATH = Path(os.environ.get("CLAWTEAM_DATA_DIR", Path.cwd() / ".clawteam")) / "plane-config.json"
```

- [ ] **Step 2: Fix plane-docker-setup.sh fallback path**

In `scripts/plane-docker-setup.sh`, change line 180 from:
```bash
CLAWTEAM_DIR="${CLAWTEAM_DATA_DIR:-$HOME/.clawteam}"
```
to:
```bash
CLAWTEAM_DIR="${CLAWTEAM_DATA_DIR:-$(pwd)/.clawteam}"
```

- [ ] **Step 3: Verify both scripts parse correctly**

Run:
```bash
python3 -c "exec(open('scripts/open-board.py').read().split('def ')[0])" && echo "open-board.py OK"
bash -n scripts/plane-docker-setup.sh && echo "setup.sh OK"
```
Expected: Both print OK.

- [ ] **Step 4: Commit**

```bash
git add scripts/open-board.py scripts/plane-docker-setup.sh
git commit -m "fix(plane): align script config paths with project-based CWD default"
```

---

### Task 2: Add `verified` status

**Files:**
- Modify: `clawteam/team/models.py:36-41` — add enum member
- Modify: `clawteam/plane/mapping.py:9-14,29-31,42-47,33-39` — add to all dicts
- Modify: `scripts/plane-docker-setup.sh` — seed "Verified" Plane state
- Test: `tests/test_plane_mapping.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_plane_mapping.py`:
```python
def test_verified_status_mapping():
    from clawteam.plane.mapping import clawteam_status_to_plane_group, plane_group_to_clawteam_status
    from clawteam.team.models import TaskStatus
    assert clawteam_status_to_plane_group(TaskStatus.verified) == "completed"
    assert plane_group_to_clawteam_status("completed", "Verified") == TaskStatus.verified
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.clawteam-venv/bin/pytest tests/test_plane_mapping.py::test_verified_status_mapping -v`
Expected: FAIL with `AttributeError: 'TaskStatus' has no attribute 'verified'`

- [ ] **Step 3: Add `verified` to TaskStatus enum**

In `clawteam/team/models.py`, add after `awaiting_approval = "awaiting_approval"`:
```python
    verified = "verified"
```

- [ ] **Step 4: Add `verified` to all mapping dicts in mapping.py**

In `clawteam/plane/mapping.py`:

Add to `_STATUS_TO_GROUP`:
```python
    TaskStatus.verified: "completed",
```

Add to `_STATUS_TO_PREFERRED_NAME`:
```python
    TaskStatus.verified: ["Verified"],
```

Add to `DEFAULT_STATE_NAMES`:
```python
    "verified": ("Verified", "completed"),
```

Update `plane_group_to_clawteam_status` to check for "verified" state name:
```python
def plane_group_to_clawteam_status(group: str, state_name: str = "") -> TaskStatus:
    if state_name.lower() == "awaiting approval":
        return TaskStatus.awaiting_approval
    if state_name.lower() == "verified":
        return TaskStatus.verified
    return _GROUP_TO_STATUS.get(group, TaskStatus.pending)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `~/.clawteam-venv/bin/pytest tests/test_plane_mapping.py -v`
Expected: All PASS.

- [ ] **Step 6: Add "Verified" state to plane-docker-setup.sh**

In `scripts/plane-docker-setup.sh`, in the `DEFAULT_STATES` list inside the Django shell block, add:
```python
    ('Verified',    'completed',  '#0ea5e9'),
```

- [ ] **Step 7: Commit**

```bash
git add clawteam/team/models.py clawteam/plane/mapping.py scripts/plane-docker-setup.sh tests/test_plane_mapping.py
git commit -m "feat(plane): add verified status to complete the HITL status flow"
```

---

### Task 3: Fix webhook `state_name` bug

**Files:**
- Modify: `clawteam/plane/webhook.py:40-43`

- [ ] **Step 1: Fix the missing state_name argument**

In `clawteam/plane/webhook.py`, change lines 40-43 from:
```python
    clawteam_status = (
        plane_group_to_clawteam_status(state_obj.group)
        if state_obj
        else TaskStatus.pending
    )
```
to:
```python
    clawteam_status = (
        plane_group_to_clawteam_status(state_obj.group, state_obj.name)
        if state_obj
        else TaskStatus.pending
    )
```

- [ ] **Step 2: Verify no syntax errors**

Run: `~/.clawteam-venv/bin/python -c "import clawteam.plane.webhook"` 
Expected: No output (clean import).

- [ ] **Step 3: Commit**

```bash
git add clawteam/plane/webhook.py
git commit -m "fix(plane): pass state_name to webhook status mapper for Awaiting Approval detection"
```

---

### Task 4: Add `AfterTaskCreate` event and emit it

**Files:**
- Modify: `clawteam/events/types.py:65-70` — add `AfterTaskCreate`
- Modify: `clawteam/store/file.py:101-108` — emit `AfterTaskCreate` after save

- [ ] **Step 1: Add AfterTaskCreate dataclass**

In `clawteam/events/types.py`, add after the `BeforeTaskCreate` class (after line 70):
```python
@dataclass
class AfterTaskCreate(HarnessEvent):
    """Fired after a task is created and saved."""

    task_id: str = ""
    subject: str = ""
    owner: str = ""
```

- [ ] **Step 2: Emit AfterTaskCreate in FileTaskStore.create()**

In `clawteam/store/file.py`, replace lines 101-108 (the event emission block in `create()`) with:
```python
        try:
            from clawteam.events.global_bus import get_event_bus
            from clawteam.events.types import AfterTaskCreate, BeforeTaskCreate
            bus = get_event_bus()
            bus.emit_async(BeforeTaskCreate(
                team_name=self.team_name, subject=subject, owner=owner,
            ))
            bus.emit_async(AfterTaskCreate(
                team_name=self.team_name, task_id=task.id, subject=subject, owner=owner,
            ))
        except Exception:
            pass
```

- [ ] **Step 3: Verify clean import**

Run: `~/.clawteam-venv/bin/python -c "from clawteam.events.types import AfterTaskCreate; print('OK')"` 
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add clawteam/events/types.py clawteam/store/file.py
git commit -m "feat(events): add AfterTaskCreate event and emit after task save"
```

---

### Task 5: Wire auto-sync hooks into CLI startup

**Files:**
- Modify: `clawteam/plane/__init__.py` — subscribe to AfterTaskCreate too
- Modify: `clawteam/cli/commands.py:4606-4635` — call `register_sync_hooks` in `plane_sync` and `plane_webhook`

- [ ] **Step 1: Add AfterTaskCreate subscription to register_sync_hooks**

In `clawteam/plane/__init__.py`, replace the full function with:
```python
def register_sync_hooks(bus: EventBus, engine: PlaneSyncEngine, team_name: str) -> None:
    """Subscribe to task events and auto-push changes to Plane."""
    from clawteam.events.types import AfterTaskCreate, AfterTaskUpdate
    from clawteam.store.file import FileTaskStore

    def _on_task_update(event: AfterTaskUpdate) -> None:
        if event.team_name != team_name:
            return
        try:
            store = FileTaskStore(event.team_name)
            task = store.get(event.task_id)
            if task:
                engine.push_task(event.team_name, task)
        except Exception as exc:
            log.warning("Plane sync failed for task %s: %s", event.task_id, exc)

    def _on_task_create(event: AfterTaskCreate) -> None:
        if event.team_name != team_name:
            return
        try:
            store = FileTaskStore(event.team_name)
            task = store.get(event.task_id)
            if task:
                engine.push_task(event.team_name, task)
        except Exception as exc:
            log.warning("Plane sync failed for new task %s: %s", event.task_id, exc)

    bus.subscribe(AfterTaskUpdate, _on_task_update)
    bus.subscribe(AfterTaskCreate, _on_task_create)
```

- [ ] **Step 2: Wire hooks in plane_sync CLI command**

In `clawteam/cli/commands.py`, in the `plane_sync` function (around line 4623 after `engine = PlaneSyncEngine(cfg)`), add:
```python
    try:
        from clawteam.events.global_bus import get_event_bus
        from clawteam.plane import register_sync_hooks
        register_sync_hooks(get_event_bus(), engine, team)
    except Exception:
        pass
```

- [ ] **Step 3: Wire hooks in plane_webhook CLI command**

In `clawteam/cli/commands.py`, in the `plane_webhook` function (after the client/states fetch block, before `serve_webhook`), add the same hook registration block as Step 2 (using the same engine pattern):
```python
    try:
        from clawteam.events.global_bus import get_event_bus
        from clawteam.plane import register_sync_hooks
        from clawteam.plane.sync import PlaneSyncEngine
        sync_engine = PlaneSyncEngine(cfg)
        register_sync_hooks(get_event_bus(), sync_engine, team)
    except Exception as exc:
        console.print(f"[yellow]Warning: auto-sync hooks not registered: {exc}[/yellow]")
```

- [ ] **Step 4: Verify clean import**

Run: `~/.clawteam-venv/bin/python -c "from clawteam.plane import register_sync_hooks; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add clawteam/plane/__init__.py clawteam/cli/commands.py
git commit -m "feat(plane): wire auto-sync hooks into CLI commands for bidirectional push"
```

---

### Task 6: Notify leader on all board state changes via webhook

**Files:**
- Modify: `clawteam/team/models.py:44-63` — add `board_update` message type
- Modify: `clawteam/plane/webhook.py:66-77` — send leader notification on every state change

- [ ] **Step 1: Add board_update message type**

In `clawteam/team/models.py`, in the `MessageType` enum, add:
```python
    board_update = "board_update"
```

- [ ] **Step 2: Add leader notification on all state changes in webhook**

In `clawteam/plane/webhook.py`, in `_handle_work_item_event`, after the existing `store.update()` call (line 69-73) and the approval request check (line 75-76), add a notification for all state changes. Replace the block from line 66 to 77:
```python
    elif action == "updated":
        for task in store.list_tasks():
            if task.metadata.get("plane_issue_id") == plane_id:
                store.update(
                    task.id,
                    subject=name,
                    status=clawteam_status,
                    force=True,
                )
                if state_obj and state_obj.group == "unstarted" and "approv" in (getattr(state_obj, "name", "") or "").lower():
                    _send_approval_request(team_name, task.id, name)
                # Notify leader of all board state changes
                _send_board_update(team_name, task.id, name, state_obj.name if state_obj else str(clawteam_status))
                return {"action": "updated", "task_id": task.id}

        return {"action": "skipped", "reason": "no matching task"}
```

- [ ] **Step 3: Add _send_board_update function**

In `clawteam/plane/webhook.py`, add after `_send_approval_request` (after line 134):
```python
def _send_board_update(team_name: str, task_id: str, subject: str, new_state: str) -> None:
    try:
        from clawteam.team.mailbox import MailboxManager
        from clawteam.team.manager import TeamManager

        leader_inbox = TeamManager.get_leader_inbox(team_name)
        if leader_inbox:
            mailbox = MailboxManager(team_name)
            mailbox.send(
                from_agent="plane-webhook",
                to=leader_inbox,
                msg_type=MessageType.board_update,
                content=f"Task '{subject}' (id={task_id}) moved to '{new_state}' on Plane board.",
                summary=f"{subject} → {new_state}",
            )
    except Exception as exc:
        log.warning("Failed to send board update: %s", exc)
```

- [ ] **Step 4: Verify clean import**

Run: `~/.clawteam-venv/bin/python -c "import clawteam.plane.webhook; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add clawteam/team/models.py clawteam/plane/webhook.py
git commit -m "feat(plane): notify leader on all board state changes via webhook"
```

---

### Task 7: Add `plane add-agent` CLI command

**Files:**
- Modify: `clawteam/cli/commands.py` — add `add-agent` subcommand to `plane_app`

- [ ] **Step 1: Add the CLI command**

In `clawteam/cli/commands.py`, after the `plane_webhook` function, add:
```python
@plane_app.command("add-agent")
def plane_add_agent(
    plane_user_id: str = typer.Argument(..., help="Plane user UUID"),
    agent_name: str = typer.Argument(..., help="ClawTeam agent name"),
):
    """Map a Plane user to a ClawTeam agent for assignee-based routing."""
    from clawteam.plane.config import load_plane_config, save_plane_config

    cfg = load_plane_config()
    cfg.user_to_agent[plane_user_id] = agent_name
    save_plane_config(cfg)
    console.print(f"[green]Mapped Plane user {plane_user_id[:12]}... → agent '{agent_name}'[/green]")
```

- [ ] **Step 2: Verify command is registered**

Run: `~/.clawteam-venv/bin/clawteam plane add-agent --help`
Expected: Help text showing `plane_user_id` and `agent_name` arguments.

- [ ] **Step 3: Commit**

```bash
git add clawteam/cli/commands.py
git commit -m "feat(plane): add 'plane add-agent' CLI command for user→agent mapping"
```

---

## Self-Review

**Spec coverage:**
- ✅ Script paths align with CWD — Task 1
- ✅ Verified status — Task 2
- ✅ Webhook state_name bug — Task 3
- ✅ AfterTaskCreate event — Task 4
- ✅ Auto-sync hooks wired — Task 5
- ✅ Leader notified on all changes — Task 6
- ✅ user_to_agent CLI — Task 7

**Placeholder scan:** No TBD/TODO/placeholders found.

**Type consistency:** `TaskStatus.verified` used consistently across models.py, mapping.py, and tests. `AfterTaskCreate` used in types.py, file.py, and `__init__.py`. `MessageType.board_update` used in models.py and webhook.py.
