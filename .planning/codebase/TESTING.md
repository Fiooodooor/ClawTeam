# Testing Patterns

**Analysis Date:** 2026-04-28

ClawTeam ships a single Python test suite under `tests/`. There is **no
JavaScript/TypeScript test runner** in the repository — the React board has no
unit tests, no Vitest config, no Jest config, no Playwright. All quality gates
for the frontend are: `tsc -b` (typecheck) and `vite build` (bundle).
Frontend behavior is exercised indirectly through the Python server-side tests
in `tests/test_board.py`, which assert on the rendered `index.html` shape and
the JSON API contracts the SPA consumes.

The Plane integration was removed in commit `427475a`; the live tree contains
**no** `tests/test_plane_*.py` files. Older `*.stale` planning docs are stale
and should be ignored.

---

## Test Framework

**Runner:**
- pytest `>=9.0.0,<10.0.0` (declared as a dev extra in
  `pyproject.toml` `[project.optional-dependencies].dev`)
- Configured in `pyproject.toml`:
  ```toml
  [tool.pytest.ini_options]
  testpaths = ["tests"]
  ```
  No `addopts`, no `markers`, no `pythonpath` overrides. Defaults apply.

**Assertion Library:**
- Plain `assert` statements. pytest's assertion rewriting handles diffing.

**Mocking:**
- Built-in pytest `monkeypatch` fixture — preferred for env vars,
  attributes on imported modules, `chdir`, and stubbing module-level
  callables.
- `unittest.mock.patch` / `MagicMock` — used when you need a context-manager
  patch, a parametrized side_effect, or a fake object with auto-spec'd
  attributes. Imported at the top of the file:
  `from unittest.mock import MagicMock, patch`
  (see `tests/test_tmux_injection.py:5`, `tests/board/test_liveness.py:6`,
  `tests/test_waiter.py:6`, `tests/test_tasks.py:3`).

**CLI runner:**
- `from typer.testing import CliRunner` for end-to-end CLI tests against
  `clawteam.cli.commands:app`. Used in `tests/test_spawn_cli.py`,
  `tests/test_cli_commands.py`, `tests/test_inbox_routing.py`,
  `tests/test_profiles.py`, `tests/test_presets.py`.

**Run Commands:**

```bash
# Install with dev extras
pip install -e ".[dev]"

# Run the full suite
pytest

# Run a single file
pytest tests/test_tmux_injection.py

# Run a single test
pytest tests/test_data_dir.py::test_walks_up_from_cwd_to_find_project_dotclawteam

# Verbose, with the assertion failure context
pytest -vv

# Lint (separate from tests)
ruff check .
```

There is no coverage configuration — coverage is not currently enforced.

---

## Test File Organization

**Location:** Separate `tests/` directory at the repo root.

**Tree (live, post Plane-removal):**

```
tests/
├── __init__.py                    # makes tests/ a package
├── conftest.py                    # shared fixtures (autouse data-dir isolation)
├── test_adapters.py
├── test_board.py
├── test_cli_commands.py
├── test_config.py
├── test_context.py
├── test_costs.py
├── test_data_dir.py               # NEW on this branch: get_data_dir walk-up
├── test_event_bus.py
├── test_fileutil.py
├── test_gource.py
├── test_harness.py
├── test_identity.py
├── test_inbox_routing.py
├── test_lifecycle.py
├── test_mailbox.py
├── test_manager.py
├── test_mcp_server.py
├── test_mcp_tools.py
├── test_models.py
├── test_plan_storage.py
├── test_presets.py
├── test_profiles.py
├── test_prompt.py
├── test_registry.py
├── test_runtime_routing.py
├── test_snapshots.py
├── test_spawn_backends.py         # 1489 lines — the largest file
├── test_spawn_cli.py
├── test_store.py
├── test_task_store_locking.py
├── test_tasks.py
├── test_templates.py
├── test_timefmt.py
├── test_tmux_injection.py         # NEW on this branch: 28 tmux-injection tests
├── test_waiter.py
├── test_workspace_manager.py
├── test_wsh_backend.py
└── board/
    ├── __init__.py
    └── test_liveness.py           # NEW on this branch: tmux liveness probes
```

A nested `tests/board/` package mirrors `clawteam/board/`. Going forward,
prefer subdirectories (`tests/<subsystem>/`) over flat `test_<subsystem>_*.py`
filenames when a subsystem grows beyond ~3 files. The `board/` subpackage
sets the precedent — add `__init__.py` so pytest can collect it as a
package.

**File naming:** `test_<module>.py` — one file per module under test, plus
larger integration-style files for cross-cutting flows (`test_runtime_routing.py`,
`test_inbox_routing.py`).

**Test naming:** `def test_<behavior_in_snake_case>():`. Names describe the
*behavior under test* and are usually a full sentence:

- `test_pane_safe_to_inject_returns_false_for_shells_and_tuis`
- `test_inject_uses_recorded_pane_id_when_available`
- `test_walks_up_from_cwd_to_find_project_dotclawteam`
- `test_falls_back_to_home_when_no_project_found`
- `test_collect_overview_does_not_call_collect_team`
- `test_team_start_spawns_runtime_watcher_for_leader`

---

## Test Structure

### Module header

Every test module begins with a one-line docstring naming the module under
test, followed by `from __future__ import annotations` when the file uses
PEP 604 union syntax in annotations:

```python
"""Tests for the tmux runtime injection safety guards."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from clawteam.spawn import tmux_backend
```

(`tests/test_tmux_injection.py:1-10`)

### Two organization styles in use

**Style A — Class grouping by feature** (preferred for medium/large files):

```python
class TestTaskCreate:
    def test_create_basic(self, store):
        t = store.create("Write tests", description="pytest suite")
        assert t.subject == "Write tests"
        assert t.status == TaskStatus.pending

    def test_create_with_priority(self, store):
        t = store.create("urgent item", priority=TaskPriority.urgent)
        assert t.priority == TaskPriority.urgent


class TestTaskGet:
    def test_get_existing(self, store): ...
    def test_get_nonexistent(self, store): ...
```

(`tests/test_tasks.py:16`, also `tests/test_models.py:17`,
`tests/test_mailbox.py:40`, `tests/test_fileutil.py:11`,
`tests/test_waiter.py:52`)

Classes are bare (no `unittest.TestCase` inheritance) so pytest fixtures
work transparently. Class names follow `Test<Feature>` and tests inside use
the same `test_<behavior>` style.

**Style B — Top-level functions** (for small, focused files):

```python
def test_env_var_wins(tmp_path, monkeypatch):
    forced = tmp_path / "forced"
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(forced))
    monkeypatch.chdir(tmp_path)

    from clawteam.team import models
    assert models.get_data_dir() == forced
```

(`tests/test_data_dir.py:30`, also `tests/test_tmux_injection.py`,
`tests/board/test_liveness.py`, `tests/test_spawn_cli.py`)

Both styles coexist — pick the one that keeps the file readable. Flat test
functions are fine when there's no shared setup; classes are preferred when
tests group naturally around a CRUD verb or scenario.

### Single behavior per test, AAA layout

Each test exercises one behavior. The Arrange-Act-Assert pattern is followed
implicitly:

```python
def test_inject_uses_recorded_pane_id_when_available(monkeypatch):
    # Arrange
    backend = tmux_backend.TmuxBackend()
    backend._agents[("demo", "leader")] = {
        "target": "clawteam-demo:leader",
        "pane_id": "%42",
    }
    envelope = MagicMock(summary="hi", source="w", target="leader", …)

    seen_targets = []
    def fake_run(cmd, *args, **kwargs):
        if "list-panes" in cmd:
            seen_targets.append(cmd[cmd.index("-t") + 1])
            return _completed(stdout="%42\n")
        …
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/tmux")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("time.sleep", lambda _x: None)

    # Act
    ok, _ = backend.inject_runtime_message("demo", "leader", envelope)

    # Assert
    assert ok is True
    assert all(t == "%42" for t in seen_targets), seen_targets
```

(`tests/test_tmux_injection.py:132`)

---

## Fixtures

### `tests/conftest.py` — autouse data-dir isolation

The single shared conftest is small and aggressive. Every test gets a
clean `~/.clawteam/` rooted in `tmp_path`, automatically:

```python
import pytest


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Point CLAWTEAM_DATA_DIR at a temp dir so every test gets a clean slate."""
    data_dir = tmp_path / ".clawteam"
    data_dir.mkdir()
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(data_dir))
    # Also override HOME so config_path() doesn't hit real ~/.clawteam/config.json
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    return data_dir


@pytest.fixture
def team_name():
    return "test-team"
```

(`tests/conftest.py:1-25`)

**Implications when writing new tests:**

- You **never** need to set `CLAWTEAM_DATA_DIR` yourself for happy-path tests.
- You **never** touch the developer's real `~/.clawteam/`. If a test asserts
  on filesystem state, it's looking at `tmp_path / ".clawteam"`.
- `HOME` and `USERPROFILE` are also redirected — code reading
  `Path.home()` is safe.
- If your test specifically needs to exercise the project-local walk-up
  resolution in `get_data_dir()`, you must override the autouse fixture
  with a local `clean_env` that `monkeypatch.delenv("CLAWTEAM_DATA_DIR",
  raising=False)` — see `tests/test_data_dir.py:11-27` for the canonical
  shape, including the `shutil.rmtree(stray)` step that clears the stray
  `.clawteam/` the autouse fixture pre-creates.

### Common per-file fixtures

```python
@pytest.fixture
def store(team_name):
    return TaskStore(team_name)
```

(`tests/test_tasks.py:11`)

```python
@pytest.fixture
def mailbox():
    m = MagicMock()
    m.receive.return_value = []
    return m

@pytest.fixture
def store():
    s = MagicMock()
    s.list_tasks.return_value = []
    return s

@pytest.fixture
def waiter(mailbox, store):
    return TaskWaiter(
        team_name="test-team",
        agent_name="leader",
        mailbox=mailbox,
        task_store=store,
        poll_interval=0.01,
    )
```

(`tests/test_waiter.py:27-49`)

Fixtures live next to the tests that use them — only the data-dir isolation
is global. Don't promote a fixture to `conftest.py` unless three or more
files actually share it.

---

## Mocking Patterns

### `monkeypatch.setenv` for environment-driven code paths

```python
def test_walks_up_from_cwd_to_find_project_dotclawteam(tmp_path, monkeypatch):
    project = tmp_path / "myrepo"
    (project / ".clawteam").mkdir(parents=True)
    nested = project / "src" / "deep" / "nested"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    from clawteam.team import models
    assert models.get_data_dir() == project / ".clawteam"
```

(`tests/test_data_dir.py:39`)

`monkeypatch.chdir`, `monkeypatch.setenv` / `delenv`, and `monkeypatch.setattr`
on stdlib paths (`subprocess.run`, `os.replace`, `time.sleep`) are the
workhorses.

### `unittest.mock.patch` for context-managed and parametrized stubs

```python
@pytest.mark.parametrize("cmd", ["bash", "zsh", "fish", "sh", "less", "vim", "fzf", "tmux"])
def test_pane_safe_to_inject_returns_false_for_shells_and_tuis(cmd):
    with patch("subprocess.run", return_value=_completed(stdout=f"{cmd}\n")):
        assert tmux_backend._pane_safe_to_inject("session:0") is False
```

(`tests/test_tmux_injection.py:17`)

```python
def test_tmux_windows_returns_window_names_when_session_exists():
    with patch("shutil.which", return_value="/usr/bin/tmux"), \
         patch("subprocess.run", side_effect=_fake_run("leader\ncoder-1\n")):
        assert liveness.tmux_windows("my-swarm") == {"leader", "coder-1"}
```

(`tests/board/test_liveness.py:22`)

Use `patch(...)` context managers when:
- you want a `@pytest.mark.parametrize`'d patch,
- you patch two cooperating callables (`shutil.which` + `subprocess.run`)
  for the duration of one assertion,
- the patched symbol is referenced as a string path
  (`"clawteam.board.server.urllib.request.build_opener"`).

Use `monkeypatch.setattr(...)` when:
- the patch should last the whole test (no `with` indent),
- you're patching attributes on an *imported module object*
  (e.g. `monkeypatch.setattr(subprocess, "run", fake_run)`).

### Fake subprocess with a `_completed` helper

The tmux-heavy tests share a tiny helper to build `subprocess.CompletedProcess`
objects:

```python
def _completed(stdout: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def fake_run(cmd, *args, **kwargs):
    if "list-panes" in cmd:
        return _completed(stdout="%1\n")
    if "display-message" in cmd:
        return _completed(stdout="claude\n")
    if "paste-buffer" in cmd:
        return _completed(returncode=1)
    return _completed()
```

(`tests/test_tmux_injection.py:13`, also `tests/board/test_liveness.py:11`)

Pattern: dispatch on a substring of `cmd` (the argv list passed to
`subprocess.run`). Each test asserts on the side-effecting argv either via
`returncode=1` to drive failure paths or by appending to a `seen_targets`
list closed over by the fake.

For unique-buffer-per-call assertions, capture every invocation:

```python
def test_inject_uses_unique_buffer_name_per_call(monkeypatch):
    calls = []
    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        return _completed()
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("time.sleep", lambda _x: None)

    tmux_backend._inject_prompt_via_buffer("session:0", "leader", "first")
    tmux_backend._inject_prompt_via_buffer("session:0", "leader", "second")

    buf_names = [
        cmd[cmd.index("-b") + 1]
        for cmd in calls
        if isinstance(cmd, list) and "-b" in cmd
    ]
    assert len(set(buf_names)) >= 2, f"buffer names collided: {buf_names}"
```

(`tests/test_tmux_injection.py:59`) — note the `monkeypatch.setattr("time.sleep",
lambda _x: None)` to keep the test fast.

### Stubbing static / class methods on managers

```python
monkeypatch.setattr(TeamManager, "discover_teams", staticmethod(fake_discover))
monkeypatch.setattr(BoardCollector, "collect_team_summary", fake_summary)
```

(`tests/test_board.py:208-209`)

When monkeypatching a `@staticmethod`, wrap the replacement in
`staticmethod(...)` so attribute access produces an unbound callable.

### Asserting on raised exceptions

```python
def test_inject_raises_when_load_buffer_fails(monkeypatch):
    def fake_run(cmd, *args, **kwargs):
        if "load-buffer" in cmd:
            return _completed(returncode=1)
        return _completed()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("time.sleep", lambda _x: None)

    with pytest.raises(RuntimeError, match="load-buffer"):
        tmux_backend._inject_prompt_via_buffer("session:0", "leader", "x")
```

(`tests/test_tmux_injection.py:80`)

Always pass `match=` so the test fails on the wrong-but-still-RuntimeError case.

---

## Typer CLI Tests

End-to-end CLI tests construct a `CliRunner`, invoke `app` with argv and
explicit `env=`, and assert on `result.exit_code` and `result.output`.

```python
from typer.testing import CliRunner

from clawteam.cli.commands import app
from clawteam.team.manager import TeamManager


class RecordingBackend:
    def __init__(self):
        self.calls = []

    def spawn(self, **kwargs):
        self.calls.append(kwargs)
        return f"Agent '{kwargs['agent_name']}' spawned"

    def list_running(self):
        return []


def test_team_start_spawns_all_existing_members(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    TeamManager.create_team(name="existing", leader_name="leader", leader_id="l001")
    TeamManager.add_member("existing", "worker-1", "w001", agent_type="coder")
    TeamManager.add_member("existing", "worker-2", "w002", agent_type="reviewer")

    backend = RecordingBackend()
    monkeypatch.setattr("clawteam.spawn.get_backend", lambda _: backend)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["team", "start", "existing", "--no-workspace"],
        env={"CLAWTEAM_DATA_DIR": str(tmp_path)},
    )

    assert result.exit_code == 0, result.output
    spawned_names = {call["agent_name"] for call in backend.calls}
    assert spawned_names == {"leader", "worker-1", "worker-2"}
```

(`tests/test_spawn_cli.py:122`)

Conventions:

1. **Recording backends** — define a tiny class in the test file that records
   spawn args and returns a deterministic message (see `RecordingBackend`,
   `ErrorBackend` at `tests/test_spawn_cli.py:9-29`). Don't mock the entire
   `SpawnBackend` interface.
2. **Patch the factory, not the backend class** —
   `monkeypatch.setattr("clawteam.spawn.get_backend", lambda _: backend)`.
   This honors the `_global_app_state` callback path inside Typer.
3. **Always pass `env=` explicitly** to `runner.invoke` even though
   `monkeypatch.setenv` already set the same value. The `env=` mapping is
   what the spawned subprocess sees.
4. **Assert on `result.exit_code` *first*, then on `result.output`.**
   Include `result.output` as the assertion message so failures explain
   themselves: `assert result.exit_code == 0, result.output`.
5. **Normalize multi-line CLI output** before substring matching:
   `normalized = " ".join(result.output.split())`
   (`tests/test_spawn_cli.py:101`).
6. **For Popen-based watchers**, fake the class:
   ```python
   class FakePopen:
       def __init__(self, args, **kwargs):
           popen_calls.append(list(args))
   monkeypatch.setattr(subprocess, "Popen", FakePopen)
   ```
   (`tests/test_spawn_cli.py:170`)

---

## Concurrency / Locking Tests

The locking tests in `tests/test_task_store_locking.py` use `multiprocessing`
with the `fork` start method, gated behind a skip marker:

```python
@pytest.mark.skipif("fork" not in mp.get_all_start_methods(), reason="requires fork start method")
def test_only_one_agent_can_claim_task_concurrently(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))
    store = TaskStore("demo")
    task = store.create("demo task")

    ctx = mp.get_context("fork")
    result_queue = ctx.Queue()

    proc_a = ctx.Process(target=_claim_task, args=(str(tmp_path), task.id, "agent-a", 0.3, result_queue))
    proc_b = ctx.Process(target=_claim_task, args=(str(tmp_path), task.id, "agent-b", 0.0, result_queue))

    proc_a.start()
    time.sleep(0.05)
    proc_b.start()

    results = sorted(result_queue.get(timeout=10) for _ in range(2))
    proc_a.join(timeout=10)
    proc_b.join(timeout=10)

    assert [result[1] for result in results].count("ok") == 1
    assert [result[1] for result in results].count("err") == 1
    assert any(result[2] == "TaskLockError" for result in results if result[1] == "err")
```

(`tests/test_task_store_locking.py:40`)

For thread-level concurrency tests (atomic write tests), use plain `threading`
with an `errors` list and assert it stays empty
(`tests/test_fileutil.py:53-71`).

---

## What to Mock (and What Not To)

**Always mock:**
- `subprocess.run` and `subprocess.Popen` — never invoke real `tmux`,
  `gource`, or spawn-backend processes from a unit test.
- `shutil.which` — controls whether the binary appears installed.
- `time.sleep` — replace with `lambda _x: None` to keep tests fast
  (`tests/test_tmux_injection.py:67`).
- `time.monotonic` when testing TTL caches
  (`tests/test_board.py:97`).
- Network calls — patch `urllib.request.build_opener` and friends with a
  `FakeResponse`/`FakeOpener` class
  (`tests/test_board.py:304-329`).

**Never mock:**
- `pathlib.Path` operations — write to `tmp_path` instead.
- `json.loads` / `json.dumps` — round-trip real data.
- Pydantic models — instantiate them. They're cheap.
- `atomic_write_text` / `file_locked` — exercise the real lock-and-write
  path; the autouse fixture redirects writes to `tmp_path`.

**Test the real thing when you can:**
- Storage: instantiate `TaskStore("test-team")` and call `create()` /
  `get()` / `update()` against the real on-disk format. The autouse fixture
  isolates the data dir.
- Team config: `TeamManager.create_team(...)` then read back from disk via
  `TeamManager.get_team(...)`.
- Mailbox: `MailboxManager(team_name).send(...)` then `.receive(...)`.

---

## Common Patterns

### Asserting on disk state

```python
def test_create_persists_to_disk(self, store):
    t = store.create("persistent")
    loaded = store.get(t.id)
    assert loaded is not None
    assert loaded.subject == "persistent"
```

(`tests/test_tasks.py:41`)

Reload through the public API rather than reading the JSON file directly —
this catches schema-drift bugs as well as IO bugs.

### Asserting on Pydantic round-trips

```python
def test_serialization_uses_from_alias(self):
    msg = TeamMessage(from_agent="a", to="b", content="c")
    dumped = json.loads(msg.model_dump_json(by_alias=True, exclude_none=True))
    assert "from" in dumped
    assert "from_agent" not in dumped
```

(`tests/test_models.py:93`)

Always serialize with `by_alias=True, exclude_none=True` (the production
contract) and assert on the alias-form keys, not the Python attribute names.

### Asserting on the dashboard JSON contract

The frontend has no tests of its own, so the JSON shape it consumes is
locked down by `tests/test_board.py`:

```python
teams = BoardCollector().collect_overview()

assert teams == [
    {
        "name": "demo",
        "description": "demo team",
        "leader": "leader",
        "members": 1,
        "membersOnline": 0,
        "tasks": 0,
        "pendingMessages": 0,
    }
]
```

(`tests/test_board.py:30`)

When you change the `BoardCollector.collect_team` / `collect_overview` shape,
update the corresponding TypeScript types in
`clawteam/board/frontend/src/types.ts` (`TeamOverview`, `TeamData`,
`Member`, `Task`) **and** add/adjust an exact-match assertion in
`tests/test_board.py`.

### Asserting on the served HTML

Because the SPA replaces an HTML-templating server, there is one canary test
that locks in the SPA shell shape:

```python
def test_board_ui_is_react_spa_shell():
    """The dashboard is now a React SPA; escaping is handled by React at render time."""
    html = Path("clawteam/board/static/index.html").read_text(encoding="utf-8")
    assert '<div id="root"></div>' in html
    assert "/assets/index-" in html
```

(`tests/test_board.py:335`) — keep this test green to guarantee no inline
user-data interpolation is reintroduced into the served HTML.

---

## Anti-patterns (do not copy)

- **Do not call `os.environ` directly to set state.** Use
  `monkeypatch.setenv` so cleanup is automatic.
- **Do not assume the autouse fixture is enough** when your test exercises
  `get_data_dir()` walk-up logic. Override it locally — see
  `tests/test_data_dir.py:11-27`.
- **Do not invoke real `subprocess.run`** in a unit test. Patch
  `subprocess.run` with a fake that dispatches on argv.
- **Do not skip the return-code check on `subprocess.run`** when writing
  *production* code — the corresponding tests
  (`test_inject_raises_when_load_buffer_fails`,
  `test_inject_raises_when_paste_buffer_fails`) will fail loudly.
- **Do not write tests against `/tmp` or the developer's real `~/.clawteam`.**
  Always use `tmp_path`.

---

*Testing analysis: 2026-04-28*
