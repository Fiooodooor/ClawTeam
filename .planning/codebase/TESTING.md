# Testing Patterns

**Analysis Date:** 2026-04-28

## Test Framework

**Runner:**
- `pytest>=9.0.0,<10.0.0` (declared in `pyproject.toml:32` under `[project.optional-dependencies] dev`).
- Config: `[tool.pytest.ini_options]` in `pyproject.toml:73-74` — `testpaths = ["tests"]`. No conftest plugins or extra options are registered globally.

**Assertion library:**
- Stock `assert` statements with pytest's introspection. No `unittest.TestCase`-style assertions. (Class-based tests do exist for grouping — `TestTaskItem`, `TestTeamMember` — but they still use bare `assert`.)

**Mocking:**
- `unittest.mock` from the standard library: `MagicMock`, `AsyncMock`, `patch`. Imported at module top: `from unittest.mock import MagicMock` (`tests/test_plane_sync.py:4`), `from unittest.mock import AsyncMock, MagicMock, patch` (`tests/test_plane_client.py:4`).
- pytest's `monkeypatch` fixture is the dominant tool — used in 100+ places to set env vars, swap module attributes, and inject fakes (`monkeypatch.setattr("clawteam.spawn.get_backend", lambda _: backend)`).

**Frontend:** No JavaScript/TypeScript test runner is configured. The board frontend (`clawteam/board/frontend/package.json`) only ships `dev`, `build`, `preview` scripts — there are no `test`/`vitest`/`jest` entries. All UI behavior is exercised indirectly via the Python `tests/test_board.py` suite which talks to `BoardCollector` + `BoardHandler`.

**Run commands:**

```bash
pip install -e ".[dev]"        # install dev deps including pytest + ruff
python -m pytest tests/ -v --tb=short    # full suite (matches CI in .github/workflows/ci.yml)
python -m pytest tests/test_plane_sync.py        # single file
python -m pytest tests/board/                    # subdirectory
python -m pytest tests/test_plane_client.py::test_client_init    # single test
ruff check clawteam/ tests/    # lint (also run in CI)
```

CI matrix: Ubuntu + macOS, Python 3.10 / 3.11 / 3.12 (`.github/workflows/ci.yml`).

## Test File Organization

**Location:**
- All tests live under top-level `tests/` (separate from `clawteam/` source). Tests are NOT co-located.
- Most test files sit flat in `tests/` (44 files). One subpackage exists so far: `tests/board/` (currently only `test_liveness.py`) — use this pattern when adding focused groups for a subsystem.

**Naming:**
- One file per source module: `tests/test_plane_client.py` ↔ `clawteam/plane/client.py`, `tests/test_plane_models.py` ↔ `clawteam/plane/models.py`, `tests/board/test_liveness.py` ↔ `clawteam/board/liveness.py`.
- Cross-cutting end-to-end tests get an `_integration` suffix: `tests/test_plane_integration.py`.
- Test functions are flat `def test_<behavior>(...)` named after the behavior asserted (`test_push_new_task_creates_plane_work_item`, `test_handle_work_item_updated_changes_status`, `test_team_start_spawns_runtime_watcher_for_leader`, `test_walks_up_from_cwd_to_find_project_dotclawteam`).
- Optionally grouped under a plain `class TestThing:` (no inheritance, no setUp) to namespace several related tests — used in `tests/test_models.py`, `tests/test_event_bus.py`, `tests/test_harness.py`.

**Structure (current branch):**

```
tests/
├── __init__.py
├── conftest.py                       # autouse isolated_data_dir fixture
├── board/
│   ├── __init__.py
│   └── test_liveness.py              # tmux-window detection (NEW on board-enhancement)
├── test_plane_client.py              # Plane REST client + payload helpers
├── test_plane_config.py              # PlaneConfig pydantic model + JSON roundtrip
├── test_plane_models.py              # PlaneWorkItem / PlaneState / PlaneComment
├── test_plane_mapping.py             # status <-> group + resolve_state_id
├── test_plane_sync.py                # PlaneSyncEngine push/pull (mocked client)
├── test_plane_webhook.py             # _verify_signature + _handle_*_event
├── test_plane_integration.py         # end-to-end: file store ↔ Plane ↔ HITL
├── test_data_dir.py                  # walk-up project-local discovery (NEW)
├── test_spawn_cli.py                 # 25+ CliRunner tests for spawn / launch / team start
├── test_board.py                     # BoardCollector + HTTP handler + SSE cache
└── ... (35 more module-level tests)
```

## Shared Fixtures (`tests/conftest.py`)

The single conftest is small but **critical** — every test runs through `isolated_data_dir`:

```python
@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Point CLAWTEAM_DATA_DIR at a temp dir so every test gets a clean slate."""
    data_dir = tmp_path / ".clawteam"
    data_dir.mkdir()
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(data_dir))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    return data_dir


@pytest.fixture
def team_name():
    return "test-team"
```

Implications for new tests:

- Never write to `~/.clawteam` — the autouse fixture redirects both `CLAWTEAM_DATA_DIR` and `HOME` to a per-test temp directory.
- Test code that calls `monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))` (without `/.clawteam`) is also valid and intentionally **overrides** the autouse fixture by writing into the bare `tmp_path` (used by most plane tests, e.g. `tests/test_plane_sync.py:17`). Both styles coexist.
- If your test relies on the absence of `.clawteam/` in the walk-up path, you must explicitly delete the autouse-created directory and re-set `HOME` — see the `clean_env` autouse fixture in `tests/test_data_dir.py:11-27` for the canonical workaround.

## Test Structure

### Suite organization (function-style, dominant)

Plain top-level functions; per-test fixtures defined nearby:

```python
@pytest.fixture
def setup_team(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))
    TeamManager.create_team(
        name="demo", leader_name="leader", leader_id="leader001",
    )
    return "demo"


@pytest.fixture
def plane_config():
    return PlaneConfig(
        url="http://localhost:8082",
        api_key="test-key",
        workspace_slug="test-ws",
        project_id="proj-1",
        sync_enabled=True,
    )


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.list_states.return_value = [
        PlaneState(id="s-pending", name="Pending", group="unstarted"),
        PlaneState(id="s-progress", name="In Progress", group="started"),
        PlaneState(id="s-done", name="Done", group="completed"),
    ]
    return client


def test_push_new_task_creates_plane_work_item(setup_team, plane_config, mock_client):
    mock_client.create_work_item.return_value = PlaneWorkItem(
        id="plane-issue-1", name="Build feature", state="s-pending",
    )
    engine = PlaneSyncEngine(plane_config, client=mock_client)
    ...
```

Source: `tests/test_plane_sync.py:15-62`.

### Suite organization (class-style, used for grouping pure unit tests)

Plain (no `unittest.TestCase`) class with bare `assert`:

```python
class TestTaskItem:
    def test_defaults(self):
        t = TaskItem(subject="do something")
        assert t.subject == "do something"
        assert t.status == TaskStatus.pending

    def test_alias_serialization(self):
        t = TaskItem(subject="x", blocked_by=["a"], locked_by="agent-1")
        data = json.loads(t.model_dump_json(by_alias=True))
        assert "blockedBy" in data
```

Source: `tests/test_models.py:17-49`. Same shape in `tests/test_event_bus.py`, `tests/test_harness.py`.

### Patterns

- **Setup pattern:** override env via `monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))`, then call domain factories (`TeamManager.create_team`, `TeamManager.add_member`, `FileTaskStore(team).create(...)`) to seed real on-disk state.
- **Teardown pattern:** none — `tmp_path` cleanup is automatic; `monkeypatch` undoes env changes; no explicit fixtures needed.
- **Assertion pattern:** plain `assert lhs == rhs`. For multi-step flows, several asserts in sequence; the failing one localizes the bug.

## Mocking

**Framework:** `unittest.mock` (`MagicMock`, `AsyncMock`, `patch`).

**Pattern A — `MagicMock` returning Pydantic models** (Plane sync/webhook tests):

```python
mock_client = MagicMock()
mock_client.list_states.return_value = [PlaneState(id="s1", name="Pending", group="unstarted")]
mock_client.create_work_item.return_value = PlaneWorkItem(id="plane-issue-1", name="Build feature", state="s-pending")

engine = PlaneSyncEngine(plane_config, client=mock_client)
engine.push_task(team, task)

mock_client.create_work_item.assert_called_once()
call_args = mock_client.update_work_item.call_args
assert call_args[0][0] == "proj-1"
```

Source: `tests/test_plane_sync.py:36-86`. `PlaneSyncEngine.__init__(config, client=None)` accepts an injected client specifically so tests bypass the real `httpx.Client`.

**Pattern B — `monkeypatch.setattr` to swap factories** (spawn CLI tests):

```python
class RecordingBackend:
    def __init__(self):
        self.calls = []
    def spawn(self, **kwargs):
        self.calls.append(kwargs)
        return f"Agent '{kwargs['agent_name']}' spawned"
    def list_running(self):
        return []

backend = RecordingBackend()
monkeypatch.setattr("clawteam.spawn.get_backend", lambda _: backend)
```

Source: `tests/test_spawn_cli.py:20-30, 39, 57-58`. The fakes are tiny inline classes; assertions inspect `backend.calls`.

**Pattern C — `unittest.mock.patch` context manager** (board liveness tests):

```python
def _fake_run(stdout: str = "", returncode: int = 0):
    def runner(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0] if args else [], returncode=returncode, stdout=stdout, stderr="")
    return runner


def test_tmux_windows_returns_window_names_when_session_exists():
    with patch("shutil.which", return_value="/usr/bin/tmux"), \
         patch("subprocess.run", side_effect=_fake_run("leader\ncoder-1\n")):
        assert liveness.tmux_windows("my-swarm") == {"leader", "coder-1"}
```

Source: `tests/board/test_liveness.py:11-31`. Use `patch` (context manager) when stubbing stdlib calls; use `monkeypatch.setattr` when stubbing project symbols.

**Pattern D — `MagicMock` as duck-typed lookup** (webhook tests):

```python
mock_states = {"state-1": MagicMock(group="unstarted")}
result = _handle_work_item_event(payload, config, setup_team, mock_states)
```

Source: `tests/test_plane_webhook.py:62-67`. When the production code only reads `obj.group`, a one-attribute `MagicMock` is enough.

**Pattern E — Inline fake `Popen` for subprocess assertions:**

```python
popen_calls = []
class FakePopen:
    def __init__(self, args, **kwargs):
        popen_calls.append(list(args))

import subprocess as _sp
monkeypatch.setattr(_sp, "Popen", FakePopen)
...
watcher_call = next((c for c in popen_calls if "runtime" in c and "watch" in c), None)
assert watcher_call is not None, f"no runtime watch invocation, got: {popen_calls}"
```

Source: `tests/test_spawn_cli.py:168-191`.

**What to mock:**
- HTTP / `httpx` clients — always inject a `MagicMock` configured to return `PlaneWorkItem`/`PlaneState`/etc. instances.
- Spawn backends — replace via `monkeypatch.setattr("clawteam.spawn.get_backend", lambda _: FakeBackend())`.
- Subprocess invocations — `monkeypatch.setattr(subprocess, "Popen", FakePopen)` or `patch("subprocess.run", side_effect=_fake_run(...))`.
- Liveness probes — `patch("clawteam.board.liveness.tmux_windows", return_value={...})` for downstream tests of `agents_online`.

**What NOT to mock:**
- The file-based stores (`TeamManager`, `FileTaskStore`, `MailboxManager`). The autouse `isolated_data_dir` fixture means hitting real disk is cheap and safe — exercise the real serializer/loader paths instead of mocking them.
- Pydantic models. Construct them with real values; that is what catches schema drift (e.g. `tests/test_plane_models.py` constructs everything via `model_validate`).
- `EventBus`. Use a real `EventBus()` and assert by side effect (`tests/test_plane_sync.py:107-130`).

## Fixtures and Factories

- **Fixtures are local to each test module.** There is no shared `tests/factories.py` or model-builder helper. The handful of repeated builders (`setup_team`, `plane_config`, `mock_client`, `states`, `env`, `config`) are defined per file (e.g. `tests/test_plane_sync.py:15-44`, `tests/test_plane_webhook.py:21-28`, `tests/test_plane_integration.py:19-48`).
- **Test data is built directly with the production constructors:** `TeamManager.create_team(...)`, `TeamManager.add_member(...)`, `FileTaskStore(team).create(subject=..., owner=...)`, `PlaneState(id=..., name=..., group=...)`. No JSON fixtures, no test-only factory classes.
- **CliRunner pattern** for Typer commands:
  ```python
  from typer.testing import CliRunner
  from clawteam.cli.commands import app

  runner = CliRunner()
  result = runner.invoke(
      app,
      ["spawn", "tmux", "claude", "--team", "demo", "--agent-name", "alice", "--no-workspace"],
      env={"CLAWTEAM_DATA_DIR": str(tmp_path)},
  )
  assert result.exit_code == 1
  assert "already running" in result.output
  ```
  Source: `tests/test_spawn_cli.py:42-50`. Always pass `env={...}` explicitly (do not rely on the test process env). Assert on `result.exit_code` AND `result.output`.

## Coverage

**Requirements:** None enforced. CI runs `python -m pytest tests/ -v --tb=short` with no `--cov` flag. There is no `coverage.py` config in `pyproject.toml` and no `.coveragerc`.

**View coverage manually:**

```bash
pip install coverage
coverage run -m pytest tests/
coverage report -m
```

## Test Types

### Unit tests

Most files are unit tests in the strict sense — single module under test, no I/O beyond `tmp_path`:

- **Pure logic:** `tests/test_plane_models.py` (Pydantic serialization), `tests/test_plane_mapping.py` (status<->group lookup), `tests/test_plane_config.py` (config defaults + JSON roundtrip), `tests/test_timefmt.py`.
- **HTTP client unit:** `tests/test_plane_client.py` constructs a real `PlaneClient`, asserts on `_headers()` / `_url()` / payload helpers without ever calling out (no `respx`, no live HTTP).
- **Webhook handlers:** `tests/test_plane_webhook.py` calls the underscore-prefixed `_handle_work_item_event` and `_handle_comment_event` directly with a hand-built payload dict instead of spinning up the `ThreadingHTTPServer`.
- **Liveness:** `tests/board/test_liveness.py` patches `shutil.which` + `subprocess.run` and asserts on the parsed set.

### Integration tests

Distinguished by file name `_integration` and exercise multiple subsystems through their public API:

- `tests/test_plane_integration.py` — end-to-end: agent creates task in `FileTaskStore`, `PlaneSyncEngine.push_task` writes through a mocked client, then `_handle_work_item_event` / `_handle_comment_event` simulates the inbound webhook and asserts the file store ends up in the right state. Three scenarios: full round-trip, HITL approval comment, human-creates-task.
- `tests/test_plane_sync.py:test_event_hook_pushes_on_task_update` — wires a real `EventBus`, registers the real `register_sync_hooks`, emits `AfterTaskUpdate`, and asserts the mock Plane client was called.
- `tests/test_spawn_cli.py` — invokes the full Typer app via `CliRunner` with mocked spawn backends, exercising config loading, profile resolution, team auto-creation/rollback, runtime-watcher launch, repo/worktree handling. The largest test file in the repo (624 lines, 25+ tests).
- `tests/test_board.py` — drives `BoardCollector` and `BoardHandler` against real on-disk teams; covers SSE snapshot caching and proxy normalization.

### E2E tests

None for the frontend. There is a manual visual checklist (root-level PNG screenshots: `board-full-page.png`, `board-team-selected.png`, `board-peek-panel.png`) and a `.playwright-mcp/` directory of ad-hoc captures, but no scripted Playwright/Cypress runs.

## Common Patterns

### Async testing

The codebase imports `AsyncMock` (`tests/test_plane_client.py:4`) but the **Plane client is synchronous** (`httpx.Client`, not `httpx.AsyncClient`), so no `@pytest.mark.asyncio` markers exist anywhere and `pytest-asyncio` is not a dependency. Do not introduce async test patterns without first making the corresponding production code async.

### Concurrency / IPC testing

For things like task locking, real `multiprocessing` is used with a `fork`-only skip marker — the only `@pytest.mark.*` in the suite:

```python
@pytest.mark.skipif("fork" not in mp.get_all_start_methods(), reason="requires fork start method")
def test_only_one_agent_can_claim_task_concurrently(monkeypatch, tmp_path: Path):
    ...
    ctx = mp.get_context("fork")
    proc_a = ctx.Process(target=_claim_task, args=(...))
    proc_a.start()
    ...
    assert [r[1] for r in results].count("ok") == 1
    assert [r[1] for r in results].count("err") == 1
```

Source: `tests/test_task_store_locking.py:40-69`. The worker function is module-level (must be picklable for fork) and re-imports `clawteam` modules under the per-process `CLAWTEAM_DATA_DIR` env.

### Error testing

Pattern is to invoke the action and assert on side effects rather than `pytest.raises`:

```python
result = runner.invoke(app, [...], env={...})
assert result.exit_code == 1
assert "Error: command 'nanobot' not found in PATH" in result.output
assert [m.name for m in TeamManager.list_members("demo")] == ["leader"]   # rollback verified
```

Source: `tests/test_spawn_cli.py:32-50`. Note the rollback assertion in line 50 — error tests should also verify cleanup happened.

### Webhook / HMAC verification

Build the signature with the real `hmac` + `hashlib` and feed the same body to the verifier:

```python
def test_verify_signature_valid():
    secret = "webhook-secret-123"
    body = b'{"event": "issue.updated"}'
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert _verify_signature(body, sig, secret) is True
```

Source: `tests/test_plane_webhook.py:30-38`. No mocking of the crypto — exercise the real path.

### Pydantic model parsing

Use `Model.model_validate(dict)` with realistic API-shaped payloads, then assert on attributes. Verify forward-compat with extra-fields:

```python
def test_work_item_extra_fields_ignored():
    data = {"id": "abc-123", "name": "task", "state": "s1", "priority": "none", "unknown_future_field": True}
    item = PlaneWorkItem.model_validate(data)
    assert item.id == "abc-123"
```

Source: `tests/test_plane_models.py:62-70`.

### Walk-up / data-dir tests

When testing `get_data_dir()` (or anything that walks up the cwd looking for `.clawteam/`), you MUST first remove the autouse fixture's stray directory:

```python
@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAWTEAM_DATA_DIR", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    stray = tmp_path / ".clawteam"
    if stray.is_dir():
        import shutil
        shutil.rmtree(stray)
```

Source: `tests/test_data_dir.py:11-27`. This is the only safe way to test `_find_project_data_dir` because the global autouse fixture would otherwise be picked up as the "project root".

---

*Testing analysis: 2026-04-28*
