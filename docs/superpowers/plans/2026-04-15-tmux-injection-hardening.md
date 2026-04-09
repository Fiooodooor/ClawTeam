# Tmux Injection Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the bash-pane RCE in `inject_runtime_message`, stop silent injection failures, and fix renamed/duplicate window targeting.

**Architecture:** Three layered defenses in `clawteam/spawn/tmux_backend.py`. (1) Before any injection, query the target pane's current foreground command with `tmux display-message -p '#{pane_current_command}'`; refuse to inject if the pane is sitting on a shell or generic TUI. (2) Use a per-call unique paste buffer name to prevent concurrent-write clobber, and check every tmux subprocess return code so failures surface as `False` instead of phantom success. (3) Capture the tmux pane ID (`%N`) at spawn time and store it on the agent registry; injection targets by pane ID instead of `session:window_name`, which stays stable across renames and disambiguates duplicates.

**Tech Stack:** Python stdlib (`subprocess`, `uuid`, `tempfile`), pytest with `monkeypatch` for tmux subprocess mocking.

**Working directory:** `/home/jac/repos/ClawTeam`

**Python interpreter:** `/home/jac/.clawteam-venv/bin/python`

---

## File Inventory

| File | Change |
|------|--------|
| `clawteam/spawn/tmux_backend.py` | New helpers `_pane_safe_to_inject`, `_run_tmux`. Modified `_inject_prompt_via_buffer`, `inject_runtime_message`, `spawn`, `_agents` registry shape. |
| `tests/test_tmux_injection.py` | New file with TDD tests for safety check, buffer uniqueness, return-code checking, pane-ID targeting. |

---

## Background context

Codex audit (in `docs/superpowers/plans/` git history if needed) found:

1. **Critical RCE**: if the leader's `claude` process dies, the tmux pane drops to bash. `_inject_prompt_via_buffer` then pastes message text + `Enter` into bash — any `$(...)` or backticks in a worker's message are executed.
2. Buffer name `prompt-{agent_name}` is shared across concurrent injections → clobber.
3. Subprocess `subprocess.run(...)` calls in `_inject_prompt_via_buffer` ignore return codes — failed paste reports success.
4. Injection target is `session:window_name`. Rename or duplicate windows break it silently.

Current code paths:
- `clawteam/spawn/tmux_backend.py:272-295` — `inject_runtime_message` probes existence of `session:window_name`, then calls `_inject_prompt_via_buffer`.
- `clawteam/spawn/tmux_backend.py:621-668` — `_inject_prompt_via_buffer`. Hardcoded buffer name on line 632, four unchecked `subprocess.run` calls.
- `clawteam/spawn/tmux_backend.py:128-138` — `spawn` creates window with bare agent name as window name, no pane-ID capture.

---

## Task 1: Refuse injection when pane is on a shell or generic TUI

**Files:**
- Modify: `clawteam/spawn/tmux_backend.py` (add `_pane_safe_to_inject` helper; call from `inject_runtime_message` before invoking `_inject_prompt_via_buffer`)
- Test: `tests/test_tmux_injection.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tmux_injection.py`:

```python
"""Tests for the tmux runtime injection safety guards."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from clawteam.spawn import tmux_backend


def _completed(stdout: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


@pytest.mark.parametrize("cmd", ["bash", "zsh", "fish", "sh", "less", "vim", "fzf", "tmux"])
def test_pane_safe_to_inject_returns_false_for_shells_and_tuis(cmd):
    with patch("subprocess.run", return_value=_completed(stdout=f"{cmd}\n")):
        assert tmux_backend._pane_safe_to_inject("session:0") is False


@pytest.mark.parametrize("cmd", ["claude", "codex", "gemini", "node", "python"])
def test_pane_safe_to_inject_returns_true_for_known_agent_clis(cmd):
    with patch("subprocess.run", return_value=_completed(stdout=f"{cmd}\n")):
        assert tmux_backend._pane_safe_to_inject("session:0") is True


def test_pane_safe_to_inject_returns_false_when_tmux_query_fails():
    with patch("subprocess.run", return_value=_completed(returncode=1)):
        assert tmux_backend._pane_safe_to_inject("session:0") is False


def test_inject_runtime_message_refuses_on_unsafe_pane():
    backend = tmux_backend.TmuxBackend()
    envelope = MagicMock(summary="hi", source="w", target="leader",
                         channel="direct", priority="high",
                         evidence=[], recommended_next_action="",
                         payload={}, dedupe_key="d", created_at="t",
                         requires_injection=True)

    def fake_run(cmd, *args, **kwargs):
        if "list-panes" in cmd:
            return _completed(stdout="%1\n")  # pane exists
        if "display-message" in cmd:
            return _completed(stdout="bash\n")  # but it's a shell
        return _completed()

    with patch("shutil.which", return_value="/usr/bin/tmux"), \
         patch("subprocess.run", side_effect=fake_run):
        ok, reason = backend.inject_runtime_message("demo", "leader", envelope)
    assert ok is False
    assert "shell" in reason.lower() or "unsafe" in reason.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/jac/repos/ClawTeam && /home/jac/.clawteam-venv/bin/python -m pytest tests/test_tmux_injection.py -v`
Expected: 4 failures with `AttributeError: module 'clawteam.spawn.tmux_backend' has no attribute '_pane_safe_to_inject'` for the helper tests, and the inject test fails because the safety check isn't wired in.

- [ ] **Step 3: Add the helper at module scope, just above `_inject_prompt_via_buffer`**

Insert in `clawteam/spawn/tmux_backend.py` immediately before the `def _inject_prompt_via_buffer(` definition:

```python
# Foreground commands a pane may be running where it is *safe* to paste a
# notification block. Anything not on this list — bash, zsh, fish, less,
# vim, fzf, tmux itself, etc. — would interpret the paste as terminal input
# (potentially executing $() / backticks). Refuse injection in those cases.
_INJECT_SAFE_COMMANDS = frozenset({
    "claude",
    "codex",
    "gemini",
    "node",      # claude-cli runs as node when not symlinked
    "python",
    "python3",
})


def _pane_safe_to_inject(target: str) -> bool:
    """Return True only when the pane's foreground command looks like an agent CLI."""
    probe = subprocess.run(
        ["tmux", "display-message", "-p", "-t", target, "#{pane_current_command}"],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        return False
    cmd = probe.stdout.strip().lower()
    return cmd in _INJECT_SAFE_COMMANDS
```

- [ ] **Step 4: Wire safety check into `inject_runtime_message`**

Replace the existing `inject_runtime_message` body (around `clawteam/spawn/tmux_backend.py:272-295`) so it calls `_pane_safe_to_inject` after the pane-existence probe:

```python
    def inject_runtime_message(self, team: str, agent_name: str, envelope) -> tuple[bool, str]:
        """Best-effort runtime injection into an existing tmux agent pane."""
        if not shutil.which("tmux"):
            return False, "tmux not installed"

        target = f"{self.session_name(team)}:{agent_name}"
        probe = subprocess.run(
            ["tmux", "list-panes", "-t", target, "-F", "#{pane_id}"],
            capture_output=True,
            text=True,
        )
        if probe.returncode != 0 or not probe.stdout.strip():
            return False, f"tmux target '{target}' not found"

        if not _pane_safe_to_inject(target):
            return False, (
                f"refusing to inject into '{target}': pane is not running an "
                "agent CLI (likely a shell or sub-TUI)"
            )

        try:
            _inject_prompt_via_buffer(
                target,
                agent_name,
                _render_runtime_notification(envelope),
            )
        except Exception as exc:
            return False, f"runtime injection failed for '{target}': {exc}"

        return True, f"Injected runtime notification into {target}"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/jac/repos/ClawTeam && /home/jac/.clawteam-venv/bin/python -m pytest tests/test_tmux_injection.py -v`
Expected: all 7 parametrized + standalone tests pass.

- [ ] **Step 6: Commit**

```bash
git add clawteam/spawn/tmux_backend.py tests/test_tmux_injection.py
git commit -m "fix(spawn): refuse tmux injection when pane is on a shell or sub-TUI

Closes the Critical RCE: if a leader agent's CLI dies and the pane
drops to bash, any worker message containing \$() or backticks would
have been executed as a shell command. Now we probe the pane's
foreground command with tmux display-message and inject only when it
is one of the known agent CLIs (claude/codex/gemini/node/python)."
```

---

## Task 2: Unique paste buffers + return-code checking

**Files:**
- Modify: `clawteam/spawn/tmux_backend.py` (`_inject_prompt_via_buffer` + new `_run_tmux` helper)
- Test: `tests/test_tmux_injection.py` (append cases)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tmux_injection.py`:

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
    # Each injection uses 3 buffer-named tmux calls (load, paste, delete);
    # the buffer name should differ between the two injections.
    assert len(set(buf_names)) >= 2, f"buffer names collided: {buf_names}"


def test_inject_raises_when_load_buffer_fails(monkeypatch):
    def fake_run(cmd, *args, **kwargs):
        if "load-buffer" in cmd:
            return _completed(returncode=1)
        return _completed()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("time.sleep", lambda _x: None)

    with pytest.raises(RuntimeError, match="load-buffer"):
        tmux_backend._inject_prompt_via_buffer("session:0", "leader", "x")


def test_inject_raises_when_paste_buffer_fails(monkeypatch):
    def fake_run(cmd, *args, **kwargs):
        if "paste-buffer" in cmd:
            return _completed(returncode=1)
        return _completed()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("time.sleep", lambda _x: None)

    with pytest.raises(RuntimeError, match="paste-buffer"):
        tmux_backend._inject_prompt_via_buffer("session:0", "leader", "x")


def test_inject_runtime_message_returns_false_on_paste_failure(monkeypatch):
    backend = tmux_backend.TmuxBackend()
    envelope = MagicMock(summary="hi", source="w", target="leader",
                         channel="direct", priority="high",
                         evidence=[], recommended_next_action="",
                         payload={}, dedupe_key="d", created_at="t",
                         requires_injection=True)

    def fake_run(cmd, *args, **kwargs):
        if "list-panes" in cmd:
            return _completed(stdout="%1\n")
        if "display-message" in cmd:
            return _completed(stdout="claude\n")
        if "paste-buffer" in cmd:
            return _completed(returncode=1)
        return _completed()

    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/tmux")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("time.sleep", lambda _x: None)

    ok, reason = backend.inject_runtime_message("demo", "leader", envelope)
    assert ok is False
    assert "paste-buffer" in reason
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/jac/repos/ClawTeam && /home/jac/.clawteam-venv/bin/python -m pytest tests/test_tmux_injection.py -v`
Expected: the 4 new tests fail because: buffer name is hardcoded `prompt-{agent_name}` (collision), and `subprocess.run` returns are never checked.

- [ ] **Step 3: Add `_run_tmux` helper just above `_inject_prompt_via_buffer`**

Insert in `clawteam/spawn/tmux_backend.py`:

```python
def _run_tmux(args: list[str]) -> None:
    """Run a tmux subcommand and raise RuntimeError on non-zero exit.

    Replaces the unchecked ``subprocess.run`` calls that previously masked
    paste-buffer / load-buffer failures as success.
    """
    result = subprocess.run(
        ["tmux", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip() or "(no stderr)"
        raise RuntimeError(f"tmux {args[0]} failed (exit {result.returncode}): {stderr}")
```

- [ ] **Step 4: Rewrite `_inject_prompt_via_buffer` to use unique buffer + checked calls**

Add `import uuid` near the top of `clawteam/spawn/tmux_backend.py` if it isn't already imported. Then replace the body of `_inject_prompt_via_buffer` (around lines 621-668) with:

```python
def _inject_prompt_via_buffer(
    target: str,
    agent_name: str,
    prompt: str,
) -> None:
    """Inject a prompt into a tmux pane via ``load-buffer`` / ``paste-buffer``.

    Uses a per-call unique buffer name so concurrent injections can't clobber
    each other. Every tmux subcommand return code is checked; failures raise
    RuntimeError instead of silently reporting success.
    """
    buf_name = f"prompt-{agent_name}-{uuid.uuid4().hex[:8]}"
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, prefix="clawteam-prompt-"
    ) as f:
        f.write(prompt)
        tmp_path = f.name

    try:
        _run_tmux(["load-buffer", "-b", buf_name, tmp_path])
        _run_tmux(["paste-buffer", "-b", buf_name, "-t", target])
        time.sleep(0.5)
        _run_tmux(["send-keys", "-t", target, "Enter"])
        time.sleep(0.3)
        _run_tmux(["send-keys", "-t", target, "Enter"])
        # Best-effort cleanup: don't blow up if tmux already deleted the buffer.
        try:
            _run_tmux(["delete-buffer", "-b", buf_name])
        except RuntimeError:
            pass
    finally:
        os.unlink(tmp_path)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/jac/repos/ClawTeam && /home/jac/.clawteam-venv/bin/python -m pytest tests/test_tmux_injection.py -v`
Expected: all tests in the file pass (Task 1 + Task 2 = 11 tests total).

- [ ] **Step 6: Commit**

```bash
git add clawteam/spawn/tmux_backend.py tests/test_tmux_injection.py
git commit -m "fix(spawn): unique tmux paste buffers + check return codes

Concurrent injections to the same agent used to share the buffer name
prompt-{agent}, racing each other to clobber the buffer between
load-buffer and paste-buffer. Every tmux subprocess.run also discarded
its return code, so failed pastes silently reported success. Each call
now uses a UUID-suffixed buffer and a _run_tmux helper that raises on
non-zero exit, surfacing failures to the caller."
```

---

## Task 3: Pane-ID-based injection targeting

**Files:**
- Modify: `clawteam/spawn/tmux_backend.py` (`spawn` records `pane_id`; `inject_runtime_message` prefers it)
- Test: `tests/test_tmux_injection.py` (append cases)

- [ ] **Step 1: Read the existing `spawn` body to confirm where the pane is created and how the registry is shaped**

Run: `grep -n "self._agents" clawteam/spawn/tmux_backend.py`
Expected: shows where `_agents` dict is mutated (likely after the new-window/new-session call). The current shape is `self._agents[agent_name] = target_string`. Task 3 needs to change that to `self._agents[(team, agent_name)] = {"target": target_string, "pane_id": pane_id}` — confirm by reading the surrounding ~20 lines so you don't accidentally break the rest of the class.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_tmux_injection.py`:

```python
def test_spawn_records_pane_id(monkeypatch, tmp_path):
    backend = tmux_backend.TmuxBackend()

    def fake_run(cmd, *args, **kwargs):
        if "has-session" in cmd:
            return _completed(returncode=1)  # session not present yet
        if "new-session" in cmd or "new-window" in cmd:
            return _completed()
        if "display-message" in cmd and "#{pane_id}" in (cmd[-1] if cmd else ""):
            return _completed(stdout="%42\n")
        if "list-panes" in cmd:
            return _completed(stdout="%42\n")
        return _completed()

    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/tmux")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("time.sleep", lambda _x: None)

    backend.spawn(
        command=["claude"],
        agent_name="leader",
        agent_id="l001",
        agent_type="leader",
        team_name="demo",
        prompt="hi",
        env=None,
        cwd=str(tmp_path),
        skip_permissions=True,
    )

    record = backend._agents.get(("demo", "leader"))
    assert record is not None
    assert record.get("pane_id") == "%42"


def test_inject_uses_recorded_pane_id_when_available(monkeypatch):
    backend = tmux_backend.TmuxBackend()
    backend._agents[("demo", "leader")] = {
        "target": "clawteam-demo:leader",
        "pane_id": "%42",
    }
    envelope = MagicMock(summary="hi", source="w", target="leader",
                         channel="direct", priority="high",
                         evidence=[], recommended_next_action="",
                         payload={}, dedupe_key="d", created_at="t",
                         requires_injection=True)

    seen_targets = []

    def fake_run(cmd, *args, **kwargs):
        if "list-panes" in cmd:
            seen_targets.append(cmd[cmd.index("-t") + 1])
            return _completed(stdout="%42\n")
        if "display-message" in cmd:
            return _completed(stdout="claude\n")
        if "paste-buffer" in cmd or "send-keys" in cmd:
            seen_targets.append(cmd[cmd.index("-t") + 1])
            return _completed()
        return _completed()

    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/tmux")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("time.sleep", lambda _x: None)

    ok, _ = backend.inject_runtime_message("demo", "leader", envelope)
    assert ok is True
    # Every -t target used by the injection path should be the pane id, not the window name.
    assert all(t == "%42" for t in seen_targets), seen_targets


def test_inject_falls_back_to_window_name_when_no_pane_id(monkeypatch):
    backend = tmux_backend.TmuxBackend()
    # No registry entry — must still try the legacy session:window target.
    envelope = MagicMock(summary="hi", source="w", target="leader",
                         channel="direct", priority="high",
                         evidence=[], recommended_next_action="",
                         payload={}, dedupe_key="d", created_at="t",
                         requires_injection=True)

    def fake_run(cmd, *args, **kwargs):
        if "list-panes" in cmd:
            return _completed(stdout="%99\n")
        if "display-message" in cmd:
            return _completed(stdout="claude\n")
        return _completed()

    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/tmux")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("time.sleep", lambda _x: None)

    ok, reason = backend.inject_runtime_message("demo", "leader", envelope)
    assert ok is True, reason
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /home/jac/repos/ClawTeam && /home/jac/.clawteam-venv/bin/python -m pytest tests/test_tmux_injection.py -v`
Expected: the 3 new tests fail because `_agents` is currently keyed by agent_name only (not `(team, agent_name)`) and stores a string, not a dict.

- [ ] **Step 4: Update `spawn` to capture and record the pane_id**

In `clawteam/spawn/tmux_backend.py`, find the block in `spawn` (around lines 130-145) where the new tmux session/window is created and the `self._agents[...]` assignment lives. Replace the existing assignment with:

```python
        # After new-session / new-window has succeeded, capture the pane_id
        # so subsequent runtime injections target by stable pane id rather
        # than window name (which can be renamed or duplicated).
        pane_probe = subprocess.run(
            ["tmux", "display-message", "-p", "-t", target, "#{pane_id}"],
            capture_output=True,
            text=True,
        )
        pane_id = pane_probe.stdout.strip() if pane_probe.returncode == 0 else ""

        self._agents[(team_name, agent_name)] = {
            "target": target,
            "pane_id": pane_id,
        }
```

If a pre-existing `self._agents[agent_name] = target` line is present, delete it (the dict is now keyed by tuple). Search the file for any other reader of `self._agents` and update it:

```bash
grep -n "self._agents" clawteam/spawn/tmux_backend.py
```

For each hit, update the access pattern:
- `list_running` (around line 266) was returning `{"name": name, "target": target, ...}` from `self._agents.items()`. Update to:
  ```python
  def list_running(self) -> list[dict[str, str]]:
      return [
          {"name": agent, "team": team, "target": rec["target"], "pane_id": rec.get("pane_id", ""), "backend": "tmux"}
          for (team, agent), rec in self._agents.items()
      ]
  ```

- [ ] **Step 5: Update `inject_runtime_message` to prefer pane_id**

Replace the body (modify what Task 1 produced):

```python
    def inject_runtime_message(self, team: str, agent_name: str, envelope) -> tuple[bool, str]:
        """Best-effort runtime injection into an existing tmux agent pane."""
        if not shutil.which("tmux"):
            return False, "tmux not installed"

        record = self._agents.get((team, agent_name)) or {}
        recorded_pane = (record.get("pane_id") or "").strip()
        fallback_target = f"{self.session_name(team)}:{agent_name}"
        target = recorded_pane or fallback_target

        probe = subprocess.run(
            ["tmux", "list-panes", "-t", target, "-F", "#{pane_id}"],
            capture_output=True,
            text=True,
        )
        if probe.returncode != 0 or not probe.stdout.strip():
            return False, f"tmux target '{target}' not found"

        if not _pane_safe_to_inject(target):
            return False, (
                f"refusing to inject into '{target}': pane is not running an "
                "agent CLI (likely a shell or sub-TUI)"
            )

        try:
            _inject_prompt_via_buffer(
                target,
                agent_name,
                _render_runtime_notification(envelope),
            )
        except Exception as exc:
            return False, f"runtime injection failed for '{target}': {exc}"

        return True, f"Injected runtime notification into {target}"
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /home/jac/repos/ClawTeam && /home/jac/.clawteam-venv/bin/python -m pytest tests/test_tmux_injection.py -v`
Expected: all 14 tests pass.

Then run the broader spawn-related suite to check nothing else broke:

Run: `cd /home/jac/repos/ClawTeam && /home/jac/.clawteam-venv/bin/python -m pytest tests/test_spawn_cli.py tests/board/ tests/test_board.py -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add clawteam/spawn/tmux_backend.py tests/test_tmux_injection.py
git commit -m "fix(spawn): target tmux injection by pane_id instead of window name

Window names are user-mutable and can be duplicated; targeting by
session:window_name silently failed when leaders renamed windows or
when two team start invocations created duplicate windows. The spawn
path now captures the pane_id (e.g. %42) at creation time, stores it
in _agents keyed by (team, agent), and inject_runtime_message uses
that pane_id whenever available, falling back to the legacy window
target only for agents spawned in earlier sessions."
```

---

## Self-review notes

- **Spec coverage**: The codex audit's Critical (E.shell-execution-in-bash-pane) is closed by Task 1. Important issues E2 (rename/duplicate window) by Task 3 and E3 (shared buffer + ignored returns) by Task 2. Out of scope for this plan: same-pair throttling weaknesses (B), watcher singleton lock (C/D), runtime_state.json locking (F), durable routing before ack (C3) — those need separate plans.
- **Backwards compatibility**: `_agents` shape changes from `dict[str, str]` to `dict[tuple[str, str], dict]`. Anyone who subclassed `TmuxBackend` reading `_agents` directly would break — but this attribute is not part of any documented public API and the rest of the codebase only uses `list_running()` (which Task 3 keeps working).
- **Why not move agents-online detection to use pane_id too?** `clawteam/board/liveness.py:tmux_windows()` queries `tmux list-windows ... -F '#{window_name}'`. After Task 3, agent windows still keep their name (we add pane_id capture, we don't rename), so the existing liveness probe keeps working. Out of scope.
- **Tmux command name semantics**: `pane_current_command` reflects the foreground process of the pane. Subshells, screen scrapers, or wrappers (e.g. `wezterm` running `claude`) will report the wrapper, not `claude` — flagged for follow-up if false negatives appear in practice. The conservative default (refuse on unknown command) is safer than permissive.
- **Threading**: `subprocess.run` with `capture_output=True` is blocking; `_run_tmux` doesn't add concurrency. This matches existing behavior in `_inject_prompt_via_buffer`.
