# Testing Patterns

**Analysis Date:** 2026-04-15

## Test Framework

**Runner:**
- pytest (dev dep `pytest>=9.0.0,<10.0.0` in `pyproject.toml`).
- Config in `pyproject.toml`:
  ```toml
  [tool.pytest.ini_options]
  testpaths = ["tests"]
  ```
- No separate `pytest.ini` or `conftest`-level plugins beyond fixtures.

**Assertion Library:**
- Plain `assert` statements (no `unittest.TestCase`, no `hamcrest`).
- `pytest.raises(...)` for expected exceptions; `pytest.fixture` for
  setup; `pytest.mark.skipif(...)` for platform-gated tests.

**Run Commands:**
```bash
pytest                                        # Run all tests
pytest tests/test_mailbox.py                  # Single file
pytest tests/test_mailbox.py::TestSendReceive::test_send_and_receive_single
                                              # Single test
pytest -k "liveness"                          # Name match
pytest -x                                     # Stop on first failure
pytest tests/board/                           # Run a subdirectory
```

**Frontend:**
- No unit tests. The smoke check is `pnpm build`
  (`cd clawteam/board/frontend && pnpm install && pnpm build`), which runs
  `tsc -b && vite build` per `package.json:scripts.build`. TypeScript in
  strict mode + `noUnusedLocals` + `noUncheckedIndexedAccess` catches most
  regressions at build time.

## Test File Organization

**Location and naming:**
- All Python tests live in `/home/jac/repos/ClawTeam/tests/`.
- Flat `test_<area>.py` by feature area, one file per Python module or
  subsystem (44 test files, ~556 `def test_*` functions,
  495+ currently collected by pytest with the in-progress refactors).
- One nested package: `tests/board/` (with its own `__init__.py`) for
  board-specific helpers/tests such as `tests/board/test_liveness.py`.

**Representative layout:**
```
tests/
  __init__.py
  conftest.py                    # global autouse fixtures
  test_models.py                 # Pydantic model behaviour
  test_manager.py                # TeamManager operations
  test_mailbox.py                # mailbox send/receive
  test_tasks.py                  # TaskStore CRUD
  test_task_store_locking.py     # cross-process lock contention
  test_spawn_cli.py              # Typer spawn/launch commands
  test_spawn_backends.py         # tmux/subprocess backend behaviour
  test_registry.py               # spawn.registry liveness
  test_cli_commands.py           # top-level CLI commands
  test_data_dir.py               # get_data_dir() resolution
  test_board.py                  # board collector/server
  test_plane_client.py           # plane REST client
  test_plane_sync.py             # bidirectional sync engine
  ...
  board/
    __init__.py
    test_liveness.py             # tmux_windows / agents_online
```

## Test Structure

**Suite Organization:**
Most files are flat `def test_*(...)` functions. Larger files group
related tests in plain classes (no `TestCase` base) — pytest discovers
methods with a `test_` prefix:

```python
# tests/test_models.py:17-49
class TestTaskItem:
    def test_defaults(self):
        t = TaskItem(subject="do something")
        assert t.status == TaskStatus.pending
        assert len(t.id) == 8

    def test_alias_serialization(self):
        t = TaskItem(subject="x", blocked_by=["a"], locked_by="agent-1")
        data = json.loads(t.model_dump_json(by_alias=True))
        assert "blockedBy" in data
```

**Naming convention** — tests read as sentences:
`test_send_and_receive_single`, `test_collect_overview_sums_inbox_counts_for_all_members`,
`test_spawn_cli_rolls_back_auto_created_team_on_spawn_error`.

**Imports:**
- `from __future__ import annotations` at the top of every test file.
- Direct imports of production code (no re-export shims): `from
  clawteam.team.mailbox import MailboxManager`, `from clawteam.cli.commands
  import app`.

## Global Fixtures — `tests/conftest.py`

Two fixtures drive almost every test:

```python
# tests/conftest.py:10-19
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

**Why this matters:**
- `isolated_data_dir` is `autouse=True`, so every test automatically runs
  against an empty `tmp_path/.clawteam/`. Real `~/.clawteam/` is never
  touched.
- `HOME` / `USERPROFILE` are also repointed so `config_path()` (which
  resolves `Path.home() / ".clawteam" / "config.json"` unconditionally)
  hits the scratch dir instead of the user's real config.
- Tests that need to override the autouse defaults — e.g.
  `tests/test_data_dir.py:10-28` — declare their own autouse fixture that
  deletes `CLAWTEAM_DATA_DIR` and removes the pre-created scratch dir so
  the walk-up discovery logic can be exercised cleanly.

**Per-test fixtures** are defined at module scope when reused inside one
file. Examples:
```python
# tests/test_plane_sync.py:15-44
@pytest.fixture
def setup_team(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))
    TeamManager.create_team(name="demo", leader_name="leader", leader_id="leader001")
    return "demo"

@pytest.fixture
def plane_config():
    return PlaneConfig(url="http://localhost:8082", api_key="test-key", ...)

@pytest.fixture
def mock_client():
    client = MagicMock()
    client.list_states.return_value = [PlaneState(...), ...]
    return client
```

## CLI Tests — Typer `CliRunner`

CLI behaviour is covered by `typer.testing.CliRunner`, invoking the real
`app` with the real global callback. The environment is repointed via the
runner's `env=` kwarg in addition to `monkeypatch.setenv`, because
Typer's process-launched command may re-read `os.environ`:

```python
# tests/test_spawn_cli.py:32-50
def test_spawn_cli_exits_nonzero_and_rolls_back_failed_member(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))
    TeamManager.create_team(name="demo", leader_name="leader", leader_id="leader001")
    monkeypatch.setattr("clawteam.spawn.get_backend", lambda _: ErrorBackend())

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["spawn", "tmux", "nanobot", "--team", "demo", "--agent-name", "alice", "--no-workspace"],
        env={"CLAWTEAM_DATA_DIR": str(tmp_path)},
    )

    assert result.exit_code == 1
    assert "Error: command 'nanobot' not found in PATH" in result.output
    assert [member.name for member in TeamManager.list_members("demo")] == ["leader"]
```

The standard assertion set is:
- `result.exit_code == 0` / `== 1` (the CLI always uses 1 for user-facing
  errors).
- substring check on `result.output` for the rich-rendered message (the
  CliRunner strips `[red]` tags but preserves the text).
- a filesystem / in-memory check on side effects
  (`TeamManager.list_members("demo")`, `backend.calls`, etc.).

## Backend Stubs — Substitution Over Mocking

`tests/test_spawn_cli.py` defines tiny hand-written stubs and swaps them
in with `monkeypatch.setattr("clawteam.spawn.get_backend", lambda _: ...)`:

```python
# tests/test_spawn_cli.py:9-29
class ErrorBackend:
    def spawn(self, **kwargs):
        return (
            "Error: command 'nanobot' not found in PATH. "
            "Install the agent CLI first or pass an executable path."
        )
    def list_running(self):
        return []

class RecordingBackend:
    def __init__(self):
        self.calls = []
    def spawn(self, **kwargs):
        self.calls.append(kwargs)
        return f"Agent '{kwargs['agent_name']}' spawned"
    def list_running(self):
        return []
```

This pattern (a small recording class instead of `MagicMock`) is the
preferred style when:
- the backend has a narrow interface that's easy to re-implement;
- assertions need to inspect recorded kwargs (`call["command"]`,
  `call["env"]["KIMI_API_KEY"]`).

`unittest.mock.MagicMock` is used when the real API has many methods
(e.g. `PlaneClient`, see `tests/test_plane_sync.py:36-44`).

## Monkeypatch Patterns

Core moves used throughout:

```python
# Environment isolation (layered on top of autouse conftest fixture)
monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))
monkeypatch.setenv("HOME", str(tmp_path))
monkeypatch.chdir(tmp_path)

# Replace a resolved function by import path (dotted string)
monkeypatch.setattr("clawteam.spawn.get_backend", lambda _: backend)
monkeypatch.setattr("clawteam.spawn.registry.is_agent_alive", lambda team, agent: True)
monkeypatch.setattr("clawteam.spawn.registry.stop_agent", _stop)

# Freeze time for TTL caches
monkeypatch.setattr("clawteam.board.server.time.monotonic", lambda: now["value"])

# Intercept subprocess.Popen with an inline fake that records args
class FakePopen:
    def __init__(self, args, **kwargs):
        popen_calls.append(list(args))
import subprocess as _sp
monkeypatch.setattr(_sp, "Popen", FakePopen)
```

(Examples in `tests/test_spawn_cli.py:170-220`, `tests/test_board.py:93-113`.)

## Mocking Strategy

`unittest.mock.patch` / `MagicMock` / `AsyncMock` are used where:
- the surface is wide (HTTP clients, MCP server);
- the real dependency is expensive (`subprocess.run("tmux ...")`,
  network, git);
- a function must return a specific exception (`side_effect=...`).

Example — `tests/board/test_liveness.py:10-36`:
```python
def _fake_run(stdout: str = "", returncode: int = 0):
    def runner(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0] if args else [],
            returncode=returncode, stdout=stdout, stderr="",
        )
    return runner

def test_tmux_windows_returns_window_names_when_session_exists():
    with patch("shutil.which", return_value="/usr/bin/tmux"), \
         patch("subprocess.run", side_effect=_fake_run("leader\ncoder-1\n")):
        assert liveness.tmux_windows("my-swarm") == {"leader", "coder-1"}
```

**What gets mocked:**
- External CLIs: `subprocess.run`, `shutil.which` (tmux, git).
- Network: `httpx.Client` via `MagicMock` (plane client tests).
- `subprocess.Popen` when the test must not actually spawn a child.
- `time.monotonic` for TTL cache expiry.
- Backend factories and registry helpers via `monkeypatch.setattr` on the
  dotted import path.

**What is *not* mocked:**
- Pydantic models — tests construct real `TeamConfig`, `TaskItem`, etc.
- `TeamManager` / `MailboxManager` / `TaskStore` — they run against the
  real file store under `tmp_path` because the autouse fixture already
  gives isolation.
- `Path`, `json`, atomic file helpers — exercised end-to-end.

## Concurrency Tests

Real processes are used for lock tests — `multiprocessing.get_context("fork")`
is required and the test is skipped on platforms without fork:

```python
# tests/test_task_store_locking.py:40-74
@pytest.mark.skipif("fork" not in mp.get_all_start_methods(), reason="requires fork start method")
def test_only_one_agent_can_claim_task_concurrently(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))
    store = TaskStore("demo")
    task = store.create("demo task")

    ctx = mp.get_context("fork")
    result_queue = ctx.Queue()
    proc_a = ctx.Process(target=_claim_task, args=(str(tmp_path), task.id, "agent-a", 0.3, result_queue))
    proc_b = ctx.Process(target=_claim_task, args=(str(tmp_path), task.id, "agent-b", 0.0, result_queue))
    proc_a.start(); time.sleep(0.05); proc_b.start()
    results = sorted(result_queue.get(timeout=10) for _ in range(2))
    ...
    assert [r[1] for r in results].count("ok") == 1
    assert [r[1] for r in results].count("err") == 1
```

## Fixtures, Factories, and Test Data

There is **no** `tests/fixtures/` directory and no shared factory module.
Instead:

- Small constructor calls go inline: `TeamManager.create_team(name="demo",
  leader_name="leader", leader_id="leader001")`.
- A local helper function is defined at the top of the file when it
  repeats 3+ times, e.g. `_create_team(name)` in
  `tests/test_registry.py:16-17`, `_make_mailbox(team_name)` in
  `tests/test_mailbox.py:17-21`, `_inbox_path(...)` / `_peer_path(...)` in
  `tests/test_mailbox.py:24-37`.
- Module-scope `@pytest.fixture` for anything a single file needs
  repeatedly (`client`, `plane_config`, `mock_client`, `setup_team`).
- Team / task names are deterministic strings (`"demo"`, `"test-team"`,
  `"my-swarm"`) — no Faker, no uuid randomisation in tests.

## Common Patterns

**Error Testing:**
```python
# CLI layer — inspect exit_code + output
result = runner.invoke(app, ["team", "start", "ghost"], env={...})
assert result.exit_code == 1
assert "ghost" in result.output

# Library layer — pytest.raises with optional match
with pytest.raises(ValueError, match="Invalid team name"):
    TeamManager.create_team(name="bad/name", ...)
```

**Async / Threaded Testing:**
- Most code is synchronous. For the SSE server and event bus, tests
  construct the primitive (`TeamSnapshotCache`) directly and drive it
  through its public API — see `tests/test_board.py:74-113`.
- `AsyncMock` is used in plane tests (`tests/test_plane_client.py:4`)
  for the httpx async surface.

**Filesystem assertions:**
- Round-trip: write via production API, re-read via production API, assert
  equality (`tests/test_models.py:44-49` for Pydantic JSON round-trips).
- Path assertions use the real `Path` API under `tmp_path`, not string
  compares.

## Test Types

**Unit tests** — dominant. Single class/function in isolation, real file
store under `tmp_path` is considered "in-process" state and not mocked.
Examples: `tests/test_models.py`, `tests/test_fileutil.py`,
`tests/test_paths.py` (not present; validation covered in manager tests),
`tests/test_identity.py`.

**Integration tests** — exercise Typer CLI plus file store plus backend
stubs. Examples: `tests/test_spawn_cli.py`, `tests/test_cli_commands.py`,
`tests/test_board.py` (HTTP collector + mailbox + team manager).

**E2E / smoke** — none automated. The frontend smoke is `pnpm build`.
Webhook and plane integration tests use `MagicMock` for the HTTP layer
rather than spinning up a real Plane instance.

## Coverage

- No coverage tool configured in `pyproject.toml` (no `pytest-cov`, no
  `.coveragerc`). Coverage is tracked informally.
- No enforced percentage, no CI gate on coverage.

## Recent Known-Good Reference Points

As of 2026-04-15 these tests are the canonical examples to mirror when
adding new tests:

- `tests/test_board.py` — HTTP collector/server, TTL cache, SSE behaviour.
- `tests/test_data_dir.py` — bespoke per-file autouse fixture override.
- `tests/test_spawn_cli.py` — `CliRunner`, backend stub classes,
  `monkeypatch.setattr` of dotted paths.
- `tests/board/test_liveness.py` — subprocess mocking via
  `unittest.mock.patch` with a fake `CompletedProcess` factory.
- `tests/test_models.py` — Pydantic alias round-trips and enum behaviour.
- `tests/test_task_store_locking.py` — cross-process locking via
  `multiprocessing.fork`.

Total test count: 556 `def test_*` functions across 44 files; latest
passing run reported 552 green.

---

*Testing analysis: 2026-04-15*
*Update when test patterns change*
