# Board Enhancement: Drag-and-Drop Kanban + Agent Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance the existing ClawTeam board web UI with drag-and-drop task status changes, 6-column kanban (adding Awaiting Approval and Verified), colored agent avatars on task cards, and a PATCH API endpoint to support interactive task updates.

**Architecture:** All changes are additive to the existing `clawteam/board/` infrastructure. The server gains one new PATCH endpoint. The collector expands its task grouping to 6 statuses. The frontend adds SortableJS for drag-and-drop and renders agent identity badges. The TUI renderer adds 2 columns. No new files are created.

**Tech Stack:** Python stdlib HTTP server, SortableJS (CDN, MIT, 28KB), existing SSE infrastructure, Rich (TUI).

---

## File Structure

```
clawteam/board/server.py         — add PATCH /api/team/<name>/task/<id> endpoint
clawteam/board/collector.py      — expand task grouping to 6 statuses
clawteam/board/renderer.py       — add awaiting_approval + verified columns
clawteam/board/static/index.html — 6-col kanban, SortableJS drag-drop, agent avatars, assign dropdown
tests/test_board.py              — add tests for PATCH endpoint and 6-status grouping
```

---

### Task 1: Expand collector task grouping to 6 statuses

**Files:**
- Modify: `clawteam/board/collector.py:96-101`
- Test: `tests/test_board.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_board.py`:

```python
def test_collect_team_groups_all_six_statuses(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))
    from clawteam.team.models import TaskStatus
    TeamManager.create_team(
        name="six", leader_name="leader", leader_id="l001", description="test",
    )
    from clawteam.team.tasks import TaskStore
    store = TaskStore("six")
    store.create(subject="t1")
    store.create(subject="t2")
    t3 = store.create(subject="t3")
    store.update(t3.id, status=TaskStatus.awaiting_approval, force=True)
    t4 = store.create(subject="t4")
    store.update(t4.id, status=TaskStatus.completed, force=True)
    t5 = store.create(subject="t5")
    store.update(t5.id, status=TaskStatus.verified, force=True)

    data = BoardCollector().collect_team("six")
    assert "awaiting_approval" in data["tasks"]
    assert "verified" in data["tasks"]
    assert len(data["tasks"]["awaiting_approval"]) == 1
    assert len(data["tasks"]["verified"]) == 1
    assert "awaiting_approval" in data["taskSummary"]
    assert "verified" in data["taskSummary"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.clawteam-venv/bin/pytest tests/test_board.py::test_collect_team_groups_all_six_statuses -v`
Expected: FAIL with `KeyError: 'awaiting_approval'` (tasks dict only has 4 keys)

- [ ] **Step 3: Update collector to group 6 statuses**

In `clawteam/board/collector.py`, replace lines 96-101:

```python
        grouped: dict[str, list[dict]] = {
            "pending": [],
            "in_progress": [],
            "completed": [],
            "blocked": [],
        }
```

with:

```python
        grouped: dict[str, list[dict]] = {
            "pending": [],
            "in_progress": [],
            "completed": [],
            "blocked": [],
            "awaiting_approval": [],
            "verified": [],
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.clawteam-venv/bin/pytest tests/test_board.py::test_collect_team_groups_all_six_statuses -v`
Expected: PASS

- [ ] **Step 5: Run all board tests**

Run: `~/.clawteam-venv/bin/pytest tests/test_board.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add clawteam/board/collector.py tests/test_board.py
git commit -m "feat(board): expand collector task grouping to 6 statuses"
```

---

### Task 2: Add PATCH endpoint to server

**Files:**
- Modify: `clawteam/board/server.py:166-187` — add `do_PATCH` method and route parsing
- Test: `tests/test_board.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_board.py`:

```python
import json as _json
from unittest.mock import MagicMock, patch


def test_patch_task_updates_status(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))
    from clawteam.team.models import TaskStatus
    TeamManager.create_team(
        name="ptest", leader_name="leader", leader_id="l001", description="test",
    )
    from clawteam.team.tasks import TaskStore
    store = TaskStore("ptest")
    task = store.create(subject="Drag me")

    # Simulate PATCH via server handler
    from clawteam.board.server import BoardHandler
    handler = MagicMock(spec=BoardHandler)
    handler.path = f"/api/team/ptest/task/{task.id}"
    handler.headers = {"Content-Length": "0"}

    body = _json.dumps({"status": "in_progress"}).encode()
    handler.headers = {"Content-Length": str(len(body))}
    handler.rfile = io.BytesIO(body)

    responses = []
    def mock_serve_json(data):
        responses.append(data)
    handler._serve_json = mock_serve_json
    handler.send_error = MagicMock()

    BoardHandler.do_PATCH(handler)

    assert len(responses) == 1
    assert responses[0]["status"] == "ok"
    assert responses[0]["task_id"] == task.id

    updated = store.get(task.id)
    assert updated.status == TaskStatus.in_progress
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.clawteam-venv/bin/pytest tests/test_board.py::test_patch_task_updates_status -v`
Expected: FAIL with `AttributeError: type object 'BoardHandler' has no attribute 'do_PATCH'`

- [ ] **Step 3: Add do_PATCH to BoardHandler**

In `clawteam/board/server.py`, add after the `do_POST` method (after line 187):

```python
    def do_PATCH(self):
        path = self.path.split("?")[0]
        # PATCH /api/team/<name>/task/<id>
        parts = path.strip("/").split("/")
        if len(parts) == 5 and parts[0] == "api" and parts[1] == "team" and parts[3] == "task":
            team_name = parts[2]
            task_id = parts[4]
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                payload = json.loads(body)
                from clawteam.team.tasks import TaskStore
                from clawteam.team.models import TaskStatus, TaskPriority
                store = TaskStore(team_name)
                kwargs = {}
                if "status" in payload:
                    kwargs["status"] = TaskStatus(payload["status"])
                if "owner" in payload:
                    kwargs["owner"] = payload["owner"]
                if "priority" in payload:
                    kwargs["priority"] = TaskPriority(payload["priority"])
                kwargs["force"] = True
                store.update(task_id, **kwargs)
                self._serve_json({"status": "ok", "task_id": task_id})
            except Exception as e:
                self.send_error(400, str(e))
            return
        self.send_error(404)

    def do_OPTIONS(self):
        """Handle CORS preflight for PATCH requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.clawteam-venv/bin/pytest tests/test_board.py::test_patch_task_updates_status -v`
Expected: PASS

- [ ] **Step 5: Run all board tests**

Run: `~/.clawteam-venv/bin/pytest tests/test_board.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add clawteam/board/server.py tests/test_board.py
git commit -m "feat(board): add PATCH endpoint for task status/owner updates"
```

---

### Task 3: Add 2 columns to TUI renderer

**Files:**
- Modify: `clawteam/board/renderer.py:176-216`

- [ ] **Step 1: Update columns_cfg**

In `clawteam/board/renderer.py`, replace lines 178-183:

```python
        columns_cfg = [
            ("PENDING", "pending", "yellow"),
            ("IN PROGRESS", "in_progress", "cyan"),
            ("COMPLETED", "completed", "green"),
            ("BLOCKED", "blocked", "red"),
        ]
```

with:

```python
        columns_cfg = [
            ("PENDING", "pending", "yellow"),
            ("AWAITING APPROVAL", "awaiting_approval", "magenta"),
            ("IN PROGRESS", "in_progress", "cyan"),
            ("COMPLETED", "completed", "green"),
            ("VERIFIED", "verified", "bright_blue"),
            ("BLOCKED", "blocked", "red"),
        ]
```

- [ ] **Step 2: Verify clean import and render**

Run: `~/.clawteam-venv/bin/python -c "from clawteam.board.renderer import BoardRenderer; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add clawteam/board/renderer.py
git commit -m "feat(board): add awaiting_approval and verified columns to TUI kanban"
```

---

### Task 4: Update frontend — 6 columns, agent avatars, SortableJS drag-and-drop

**Files:**
- Modify: `clawteam/board/static/index.html`

This is the largest task. It modifies 4 sections of `index.html`:
1. CSS variables and grid (add 2 color vars, change grid to 6 cols)
2. HTML kanban skeleton (add 2 column divs)
3. JS `updateDashboard()` (render 6 columns with agent avatars)
4. JS drag-and-drop initialization (SortableJS)

- [ ] **Step 1: Add CSS variables for new statuses**

In the `:root` block (around line 24), after `--color-blocked: #ef4444;`, add:

```css
            --color-approval: #a855f7;
            --color-verified: #0ea5e9;
```

- [ ] **Step 2: Change kanban grid to 6 columns**

Change line 337:

```css
            grid-template-columns: repeat(4, 1fr);
```

to:

```css
            grid-template-columns: repeat(6, 1fr);
```

- [ ] **Step 3: Add CSS for new column headers**

After line 361 (`.k-head-blocked`), add:

```css
        .k-head-approval { border-top: 3px solid var(--color-approval); color: var(--color-approval); border-radius: var(--radius-md) var(--radius-md) 0 0;}
        .k-head-verified { border-top: 3px solid var(--color-verified); color: var(--color-verified); border-radius: var(--radius-md) var(--radius-md) 0 0;}
```

- [ ] **Step 4: Add CSS for agent avatar**

After the `.blocked-label` rule (line 385), add:

```css
        .agent-avatar {
            width: 24px; height: 24px; border-radius: 50%;
            display: inline-flex; align-items: center; justify-content: center;
            font-size: 11px; font-weight: 600; color: #fff;
            flex-shrink: 0;
        }
        .task-card.sortable-ghost {
            opacity: 0.4;
            border: 2px dashed rgba(99, 102, 241, 0.6);
        }
        .task-card.sortable-chosen {
            box-shadow: 0 8px 24px rgba(0,0,0,0.5);
            transform: rotate(1deg);
        }
```

- [ ] **Step 5: Add SortableJS CDN script**

Before the closing `</head>` tag (line ~6 area, after the style block), add:

```html
    <script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/Sortable.min.js"></script>
```

- [ ] **Step 6: Update HTML kanban skeleton**

Replace lines 635-640 (the kanban board HTML in `renderDashboardSkeleton()`) with:

```html
            <div class="kanban-board" id="ui-kanban">
                <div class="kanban-col"><div class="k-head k-head-pending"><span>Pending Intake</span><span id="c-pending">0</span></div><div class="k-body" id="col-pending" data-status="pending"></div></div>
                <div class="kanban-col"><div class="k-head k-head-approval"><span>Awaiting Approval</span><span id="c-approval">0</span></div><div class="k-body" id="col-approval" data-status="awaiting_approval"></div></div>
                <div class="kanban-col"><div class="k-head k-head-progress"><span>In Progress</span><span id="c-progress">0</span></div><div class="k-body" id="col-progress" data-status="in_progress"></div></div>
                <div class="kanban-col"><div class="k-head k-head-completed"><span>Completed</span><span id="c-completed">0</span></div><div class="k-body" id="col-completed" data-status="completed"></div></div>
                <div class="kanban-col"><div class="k-head k-head-verified"><span>Verified</span><span id="c-verified">0</span></div><div class="k-body" id="col-verified" data-status="verified"></div></div>
                <div class="kanban-col"><div class="k-head k-head-blocked"><span>Blocked</span><span id="c-blocked">0</span></div><div class="k-body" id="col-blocked" data-status="blocked"></div></div>
            </div>
```

- [ ] **Step 7: Update summary cards**

Replace the summary cards HTML in `updateDashboard()` (lines 661-678) with:

```javascript
        document.getElementById('ui-summary').innerHTML = `
            <div class="stat-card glass-panel pending">
                <div class="stat-value" style="color: var(--color-pending)">${taskSummary.pending || 0}</div>
                <div class="stat-label">Pending Intake</div>
            </div>
            <div class="stat-card glass-panel">
                <div class="stat-value" style="color: var(--color-approval)">${taskSummary.awaiting_approval || 0}</div>
                <div class="stat-label">Awaiting Approval</div>
            </div>
            <div class="stat-card glass-panel progress">
                <div class="stat-value" style="color: var(--color-progress)">${taskSummary.in_progress || 0}</div>
                <div class="stat-label">In Execution</div>
            </div>
            <div class="stat-card glass-panel completed">
                <div class="stat-value" style="color: var(--color-completed)">${taskSummary.completed || 0}</div>
                <div class="stat-label">Completed</div>
            </div>
            <div class="stat-card glass-panel">
                <div class="stat-value" style="color: var(--color-verified)">${taskSummary.verified || 0}</div>
                <div class="stat-label">Verified</div>
            </div>
            <div class="stat-card glass-panel blocked">
                <div class="stat-value" style="color: var(--color-blocked)">${taskSummary.blocked || 0}</div>
                <div class="stat-label">Blocked</div>
            </div>
        `;
```

Also update the `.summary-grid` CSS (around line 290) from `grid-template-columns: repeat(4, 1fr)` to `repeat(6, 1fr)`.

- [ ] **Step 8: Add agent avatar helper function**

Add this helper function before `updateDashboard()` (around line 644):

```javascript
    function agentColor(name) {
        let hash = 0;
        for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
        const colors = ['#f59e0b','#3b82f6','#10b981','#ef4444','#a855f7','#ec4899','#14b8a6','#f97316','#6366f1','#84cc16'];
        return colors[Math.abs(hash) % colors.length];
    }

    function agentAvatar(name) {
        if (!name) return '';
        const initials = name.slice(0, 2).toUpperCase();
        const bg = agentColor(name);
        return `<span class="agent-avatar" style="background:${bg}" title="${escapeHtml(name)}">${initials}</span>`;
    }
```

- [ ] **Step 9: Update kanban rendering to 6 columns with avatars**

Replace the kanban rendering block (lines 728-743) with:

```javascript
        const COLUMNS = [
            {key: 'pending', id: 'pending'},
            {key: 'awaiting_approval', id: 'approval'},
            {key: 'in_progress', id: 'progress'},
            {key: 'completed', id: 'completed'},
            {key: 'verified', id: 'verified'},
            {key: 'blocked', id: 'blocked'},
        ];
        COLUMNS.forEach(({key, id}) => {
            const list = tasks[key] || [];
            document.getElementById(`c-${id}`).innerText = list.length;
            document.getElementById(`col-${id}`).innerHTML = list.length === 0 ?
                '<div style="text-align:center;color:var(--text-tertiary);margin-top:24px;font-size:13px;letter-spacing:0.05em;">NO DATA</div>' :
                list.map(t => `
                    <div class="task-card ${key === 'blocked' ? 'blocked-card' : ''}" data-task-id="${escapeHtml(t.id || '')}">
                        <div class="task-id">#${escapeHtml((t.id || '').substring(0,8))}</div>
                        <div class="task-subj">${escapeHtml(t.subject || '')}</div>
                        <div class="task-own">
                            ${agentAvatar(t.owner)}
                            ${escapeHtml(t.owner || 'Unassigned')}
                        </div>
                        ${key === 'blocked' && t.blockedBy && t.blockedBy.length ? `<div class="blocked-label">Blocked by: ${t.blockedBy.map(v => escapeHtml(v)).join(', ')}</div>` : ''}
                    </div>
                `).join('');
        });

        initSortable();
```

- [ ] **Step 10: Add SortableJS initialization**

Add after the `updateDashboard()` function:

```javascript
    let sortablesInitialized = false;

    function initSortable() {
        if (sortablesInitialized || typeof Sortable === 'undefined') return;
        document.querySelectorAll('.k-body').forEach(col => {
            new Sortable(col, {
                group: 'kanban',
                animation: 200,
                ghostClass: 'sortable-ghost',
                chosenClass: 'sortable-chosen',
                onEnd: async function(evt) {
                    const taskId = evt.item.dataset.taskId;
                    const newStatus = evt.to.dataset.status;
                    if (!taskId || !newStatus || !currentTeam) return;
                    try {
                        await fetch(`/api/team/${encodeURIComponent(currentTeam)}/task/${encodeURIComponent(taskId)}`, {
                            method: 'PATCH',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({status: newStatus})
                        });
                    } catch(e) {
                        console.error('Failed to update task status', e);
                    }
                }
            });
        });
        sortablesInitialized = true;
    }
```

- [ ] **Step 11: Reset sortable flag on team switch**

In the `connectSSE()` function (around line 557), add at the top of the function:

```javascript
        sortablesInitialized = false;
```

- [ ] **Step 12: Verify by starting the server**

Run:
```bash
~/.clawteam-venv/bin/clawteam board serve test-plane --port 8080
```

Open `http://localhost:8080` in a browser. Expected:
- 6 kanban columns visible
- Agent avatars (colored circles with initials) on task cards
- Drag a task between columns → status changes in `.clawteam/` file
- SSE pushes update back to the page

- [ ] **Step 13: Commit**

```bash
git add clawteam/board/static/index.html
git commit -m "feat(board): add 6-column kanban with drag-and-drop and agent avatars"
```

---

## Self-Review

**Spec coverage:**
- Drag-and-drop status changes → Task 4 Steps 10-11 (SortableJS `onEnd` → PATCH)
- PATCH endpoint → Task 2 (status, owner, priority)
- Agent avatars → Task 4 Steps 8-9 (`agentAvatar()` with deterministic color)
- 6 kanban columns → Task 4 Steps 2,6 (CSS grid + HTML)
- Awaiting Approval + Verified in collector → Task 1
- TUI 6 columns → Task 3
- Tests → Tasks 1-2 include tests

**Placeholder scan:** No placeholders found. All code is complete.

**Type consistency:**
- `TaskStatus` enum values used: `pending`, `in_progress`, `completed`, `blocked`, `awaiting_approval`, `verified` — consistent across collector, server, renderer, and frontend.
- PATCH endpoint uses `TaskStatus(payload["status"])` which accepts all valid enum values.
- Frontend `data-status` attributes match the enum values exactly.
- Column IDs in HTML use shortened forms (`approval`, `progress`, `verified`) while `data-status` uses full enum values — these are separate namespaces and don't conflict.
