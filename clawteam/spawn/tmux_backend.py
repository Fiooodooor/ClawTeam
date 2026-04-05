"""Tmux spawn backend - launches agents in tmux windows for visual monitoring."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
import time

from clawteam.spawn.base import SpawnBackend
from clawteam.spawn.cli_env import build_spawn_path, resolve_clawteam_executable
from clawteam.spawn.command_validation import normalize_spawn_command, validate_spawn_command


class TmuxBackend(SpawnBackend):
    """Spawn agents in tmux windows for visual monitoring.

    Each agent gets its own tmux window in a session named ``clawteam-{team}``.
    Agents run in interactive mode so their work is visible in the tmux pane.
    """

    def __init__(self):
        self._agents: dict[str, str] = {}  # agent_name -> tmux target

    def spawn(
        self,
        command: list[str],
        agent_name: str,
        agent_id: str,
        agent_type: str,
        team_name: str,
        prompt: str | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        skip_permissions: bool = False,
    ) -> str:
        if not shutil.which("tmux"):
            return "Error: tmux not installed"

        session_name = f"clawteam-{team_name}"
        clawteam_bin = resolve_clawteam_executable()
        env_vars = {
            "CLAWTEAM_AGENT_ID": agent_id,
            "CLAWTEAM_AGENT_NAME": agent_name,
            "CLAWTEAM_AGENT_TYPE": agent_type,
            "CLAWTEAM_TEAM_NAME": team_name,
            "CLAWTEAM_AGENT_LEADER": "0",
        }
        # Propagate user if set
        user = os.environ.get("CLAWTEAM_USER", "")
        if user:
            env_vars["CLAWTEAM_USER"] = user
        # Propagate transport if set
        transport = os.environ.get("CLAWTEAM_TRANSPORT", "")
        if transport:
            env_vars["CLAWTEAM_TRANSPORT"] = transport
        if cwd:
            env_vars["CLAWTEAM_WORKSPACE_DIR"] = cwd
        if env:
            # Keys mapped to the unset sentinel should be REMOVED from the
            # environment (via explicit ``unset`` in the shell preamble).
            _UNSET = "__CLAWTEAM_UNSET__"
            for k, v in env.items():
                if v == _UNSET:
                    env_vars.pop(k, None)
                else:
                    env_vars[k] = v
        env_vars["PATH"] = build_spawn_path(env_vars.get("PATH", os.environ.get("PATH")))
        if os.path.isabs(clawteam_bin):
            env_vars.setdefault("CLAWTEAM_BIN", clawteam_bin)

        normalized_command = normalize_spawn_command(command)

        command_error = validate_spawn_command(normalized_command, path=env_vars["PATH"], cwd=cwd)
        if command_error:
            return command_error

        export_str = "; ".join(f"export {k}={shlex.quote(v)}" for k, v in env_vars.items())
        # Also unset keys that the caller marked for deletion so the tmux
        # shell (which inherits the tmux server's env) doesn't leak them.
        if env:
            _UNSET = "__CLAWTEAM_UNSET__"
            unset_keys = [k for k, v in env.items() if v == _UNSET]
            if unset_keys:
                export_str += "; unset " + " ".join(unset_keys)

        # Build the command (without prompt — we'll send it via send-keys)
        final_command = list(normalized_command)
        # Default Claude agents to Opus 4.6 unless explicitly overridden
        if _is_claude_command(normalized_command) and not _command_has_model_arg(normalized_command):
            model = (
                (env or {}).get("CLAWTEAM_SPAWN_MODEL")
                or os.environ.get("CLAWTEAM_SPAWN_MODEL")
                or "claude-opus-4-6"
            )
            final_command.extend(["--model", model])
        if skip_permissions:
            if _is_claude_command(normalized_command):
                final_command.append("--dangerously-skip-permissions")
            elif _is_codex_command(normalized_command):
                final_command.append("--dangerously-bypass-approvals-and-sandbox")

        if _is_nanobot_command(normalized_command):
            if cwd and not _command_has_workspace_arg(normalized_command):
                final_command.extend(["-w", cwd])
            if prompt:
                final_command.extend(["-m", prompt])
        elif prompt and _is_codex_command(normalized_command):
            final_command.append(prompt)

        cmd_str = " ".join(shlex.quote(c) for c in final_command)
        # Append on-exit hook: runs immediately when agent process exits
        exit_cmd = shlex.quote(clawteam_bin) if os.path.isabs(clawteam_bin) else "clawteam"
        exit_hook = (
            f"{exit_cmd} lifecycle on-exit --team {shlex.quote(team_name)} "
            f"--agent {shlex.quote(agent_name)}"
        )
        # Unset Claude nesting-detection env vars so spawned claude agents
        # don't refuse to start when the leader is itself a claude session.
        unset_clause = "unset CLAUDECODE CLAUDE_CODE_ENTRYPOINT CLAUDE_CODE_SESSION 2>/dev/null; "
        if cwd:
            full_cmd = f"{unset_clause}{export_str}; cd {shlex.quote(cwd)} && {cmd_str}; {exit_hook}"
        else:
            full_cmd = f"{unset_clause}{export_str}; {cmd_str}; {exit_hook}"

        # Check if tmux session exists
        check = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        target = f"{session_name}:{agent_name}"

        if check.returncode != 0:
            launch = subprocess.run(
                ["tmux", "new-session", "-d", "-s", session_name, "-n", agent_name, full_cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        else:
            launch = subprocess.run(
                ["tmux", "new-window", "-t", session_name, "-n", agent_name, full_cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        if launch.returncode != 0:
            stderr = launch.stderr.decode() if isinstance(launch.stderr, bytes) else launch.stderr
            return f"Error: failed to launch tmux session: {(stderr or '').strip()}"

        # Detect commands that die before the session becomes observable.
        time.sleep(0.3)
        pane_check = subprocess.run(
            ["tmux", "list-panes", "-t", target, "-F", "#{pane_id}"],
            capture_output=True,
            text=True,
        )
        if pane_check.returncode != 0 or not pane_check.stdout.strip():
            return (
                f"Error: agent command '{normalized_command[0]}' exited immediately after launch. "
                "Verify the CLI works standalone before using it with clawteam spawn."
            )

        _confirm_workspace_trust_if_prompted(target, normalized_command)

        # Send the prompt as input to the interactive claude session
        # (codex prompt is passed as positional arg above, so skip here)
        if prompt and _is_claude_command(normalized_command):
            # Wait briefly for claude to start up
            time.sleep(2)
            # Write prompt to a temp file and use load-buffer + paste-buffer
            # to avoid escaping issues for multi-line prompts.
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, prefix="clawteam-prompt-"
            ) as f:
                f.write(prompt)
                tmp_path = f.name
            subprocess.run(
                ["tmux", "load-buffer", "-b", f"prompt-{agent_name}", tmp_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            subprocess.run(
                ["tmux", "paste-buffer", "-b", f"prompt-{agent_name}", "-t", target],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            # Claude interactive mode needs Enter twice after paste:
            # first to confirm the pasted text, second to submit.
            time.sleep(0.5)
            subprocess.run(
                ["tmux", "send-keys", "-t", target, "Enter"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            time.sleep(0.3)
            subprocess.run(
                ["tmux", "send-keys", "-t", target, "Enter"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            subprocess.run(
                ["tmux", "delete-buffer", "-b", f"prompt-{agent_name}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            os.unlink(tmp_path)
        elif prompt and not _is_codex_command(normalized_command) and not _is_nanobot_command(normalized_command):
            time.sleep(1)
            subprocess.run(
                ["tmux", "send-keys", "-t", target, prompt, "Enter"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self._agents[agent_name] = target

        # Capture pane PID for robust liveness checking (survives tile operations)
        pane_pid = 0
        pid_result = subprocess.run(
            ["tmux", "list-panes", "-t", target, "-F", "#{pane_pid}"],
            capture_output=True, text=True,
        )
        if pid_result.returncode == 0 and pid_result.stdout.strip():
            try:
                pane_pid = int(pid_result.stdout.strip().splitlines()[0])
            except ValueError:
                pass

        # Persist spawn info for liveness checking
        from clawteam.spawn.registry import register_agent
        register_agent(
            team_name=team_name,
            agent_name=agent_name,
            backend="tmux",
            tmux_target=target,
            pid=pane_pid,
            command=list(normalized_command),
        )

        return f"Agent '{agent_name}' spawned in tmux ({target})"

    def list_running(self) -> list[dict[str, str]]:
        return [
            {"name": name, "target": target, "backend": "tmux"}
            for name, target in self._agents.items()
        ]

    @staticmethod
    def session_name(team_name: str) -> str:
        return f"clawteam-{team_name}"

    @staticmethod
    def is_agent_idle(target: str, timeout_seconds: float = 3.0) -> bool:
        """Claude CLI가 입력 대기(idle) 상태인지 확인.

        tmux capture-pane으로 마지막 몇 줄을 읽고,
        Claude의 프롬프트 대기 패턴을 감지한다:
        - "❯" (claude code 프롬프트)
        - ">" (일반 프롬프트)
        - "⏵⏵" (bypass permissions indicator)
        - 빈 줄로 끝나면서 이전 줄에 출력이 있으면 idle

        timeout_seconds 동안 폴링해서 idle이 확인되면 True.
        """
        poll_interval = 0.3
        deadline = time.monotonic() + timeout_seconds

        while time.monotonic() < deadline:
            result = subprocess.run(
                ["tmux", "capture-pane", "-p", "-t", target],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                time.sleep(poll_interval)
                continue

            if _detect_idle_from_pane_output(result.stdout):
                return True

            time.sleep(poll_interval)

        return False

    def send_followup_prompt(
        self,
        target: str,
        prompt: str,
        agent_name: str,
    ) -> str:
        """기존 tmux 세션에 새 프롬프트를 전송.

        1. is_agent_idle(target) 확인
        2. idle이면 load-buffer/paste-buffer/Enter로 전송
        3. idle이 아니면 에러 반환

        Returns:
            성공 메시지 or "Error: ..."
        """
        if not prompt:
            return "Error: prompt is empty"

        # Early exit: tmux 세션 존재 확인
        check = subprocess.run(
            ["tmux", "list-panes", "-t", target, "-F", "#{pane_id}"],
            capture_output=True,
            text=True,
        )
        if check.returncode != 0 or not check.stdout.strip():
            return f"Error: tmux target '{target}' not found or has no panes"

        if not self.is_agent_idle(target):
            return f"Error: agent at '{target}' is not idle (still processing)"

        # load-buffer / paste-buffer / Enter 패턴으로 프롬프트 전송
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix="clawteam-followup-"
        ) as f:
            f.write(prompt)
            tmp_path = f.name

        buffer_name = f"prompt-{agent_name}"
        try:
            load = subprocess.run(
                ["tmux", "load-buffer", "-b", buffer_name, tmp_path],
                capture_output=True,
                text=True,
            )
            if load.returncode != 0:
                return f"Error: tmux load-buffer failed: {load.stderr.strip()}"

            paste = subprocess.run(
                ["tmux", "paste-buffer", "-b", buffer_name, "-t", target],
                capture_output=True,
                text=True,
            )
            if paste.returncode != 0:
                return f"Error: tmux paste-buffer failed: {paste.stderr.strip()}"

            time.sleep(0.5)
            subprocess.run(
                ["tmux", "send-keys", "-t", target, "Enter"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            time.sleep(0.3)
            subprocess.run(
                ["tmux", "send-keys", "-t", target, "Enter"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        finally:
            subprocess.run(
                ["tmux", "delete-buffer", "-b", buffer_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            os.unlink(tmp_path)

        return f"Followup prompt sent to '{agent_name}' at {target}"

    @staticmethod
    def tile_panes(team_name: str) -> str:
        """Merge all windows into one tiled view. Does NOT attach.

        Returns status message or error.
        """
        session = TmuxBackend.session_name(team_name)

        check = subprocess.run(
            ["tmux", "has-session", "-t", session],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if check.returncode != 0:
            return f"Error: tmux session '{session}' not found. No agents spawned for team '{team_name}'?"

        # Count current panes in window 0
        pane_count = subprocess.run(
            ["tmux", "list-panes", "-t", f"{session}:0"],
            capture_output=True, text=True,
        )
        num_panes = len(pane_count.stdout.strip().splitlines()) if pane_count.returncode == 0 else 0

        # Get windows
        result = subprocess.run(
            ["tmux", "list-windows", "-t", session, "-F", "#{window_index}"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return f"Error: failed to list windows: {result.stderr.strip()}"

        windows = result.stdout.strip().splitlines()

        # If already tiled (1 window, multiple panes), skip merge
        if len(windows) <= 1 and num_panes > 1:
            return f"Already tiled ({num_panes} panes) in {session}"

        if len(windows) > 1:
            first = windows[0]
            for w in windows[1:]:
                subprocess.run(
                    ["tmux", "join-pane", "-s", f"{session}:{w}", "-t", f"{session}:{first}", "-h"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
            subprocess.run(
                ["tmux", "select-layout", "-t", f"{session}:{first}", "tiled"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )

        # Recount
        pane_count = subprocess.run(
            ["tmux", "list-panes", "-t", f"{session}:0"],
            capture_output=True, text=True,
        )
        final_panes = len(pane_count.stdout.strip().splitlines()) if pane_count.returncode == 0 else 0
        return f"Tiled {final_panes} panes in {session}"

    @staticmethod
    def attach_all(team_name: str) -> str:
        """Tile all windows into panes and attach to the session."""
        result = TmuxBackend.tile_panes(team_name)
        if result.startswith("Error"):
            return result

        session = TmuxBackend.session_name(team_name)
        subprocess.run(["tmux", "attach-session", "-t", session])
        return result


def _is_claude_command(command: list[str]) -> bool:
    """Check if the command is a claude CLI invocation."""
    if not command:
        return False
    cmd = command[0].rsplit("/", 1)[-1]  # basename
    return cmd in ("claude", "claude-code")


def _is_codex_command(command: list[str]) -> bool:
    """Check if the command is a codex CLI invocation."""
    if not command:
        return False
    cmd = command[0].rsplit("/", 1)[-1]  # basename
    return cmd in ("codex", "codex-cli")


def _is_nanobot_command(command: list[str]) -> bool:
    """Check if the command is a nanobot CLI invocation."""
    if not command:
        return False
    cmd = command[0].rsplit("/", 1)[-1]
    return cmd == "nanobot"


def _command_has_workspace_arg(command: list[str]) -> bool:
    """Return True when a command already specifies a nanobot workspace."""
    return "-w" in command or "--workspace" in command


def _command_has_model_arg(command: list[str]) -> bool:
    """Return True when a command already specifies a --model flag."""
    return "--model" in command or "-m" in command


def _confirm_workspace_trust_if_prompted(
    target: str,
    command: list[str],
    timeout_seconds: float = 5.0,
    poll_interval_seconds: float = 0.2,
) -> bool:
    """Acknowledge first-run workspace trust prompts for interactive CLIs.

    Claude Code and Codex can stop at a directory trust prompt when launched in
    a fresh git worktree. Detect that specific screen before any prompt
    injection and accept it with a single Enter so the interactive TUI remains
    intact.
    """
    if not (_is_claude_command(command) or _is_codex_command(command)):
        return False

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        pane = subprocess.run(
            ["tmux", "capture-pane", "-p", "-t", target],
            capture_output=True,
            text=True,
        )
        pane_text = pane.stdout.lower() if pane.returncode == 0 else ""
        if _looks_like_workspace_trust_prompt(command, pane_text):
            subprocess.run(
                ["tmux", "send-keys", "-t", target, "Enter"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            time.sleep(0.5)
            return True

        time.sleep(poll_interval_seconds)

    return False


def _looks_like_workspace_trust_prompt(command: list[str], pane_text: str) -> bool:
    """Return True when the tmux pane is showing a trust confirmation dialog."""
    if not pane_text:
        return False

    if _is_claude_command(command):
        return "trust this folder" in pane_text and "enter to confirm" in pane_text

    if _is_codex_command(command):
        return (
            "trust the contents of this directory" in pane_text
            and "press enter to continue" in pane_text
        )

    return False


def _is_interactive_cli(command: list[str]) -> bool:
    """Check if the command is an interactive AI CLI."""
    return _is_claude_command(command) or _is_codex_command(command) or _is_nanobot_command(command)


# ---------- idle detection helpers ----------

_IDLE_PATTERNS: tuple[str, ...] = (
    "\u276f",   # ❯ (claude code prompt)
    "\u23f5\u23f5",  # ⏵⏵ (bypass permissions indicator)
)


def _detect_idle_from_pane_output(pane_output: str) -> bool:
    """tmux capture-pane 출력에서 idle 상태를 감지.

    마지막 비공백 줄 3줄을 검사하여:
    1. 알려진 프롬프트 패턴(❯, ⏵⏵)이 있으면 idle
    2. ">" 문자로 시작하는 줄이 있으면 idle
    3. 마지막 줄이 빈 줄이고 그 이전에 출력이 있으면 idle
    """
    if not pane_output:
        return False

    # trailing newline 감지를 위해 strip 전의 줄 목록 보존
    raw_lines = pane_output.split("\n")
    lines = pane_output.rstrip("\n").split("\n")

    # 전체가 빈 출력이면 idle 아님
    non_empty = [line for line in lines if line.strip()]
    if not non_empty:
        return False

    # 마지막 3줄 (비어있지 않은 줄 포함) 검사
    tail = lines[-3:] if len(lines) >= 3 else lines

    for line in tail:
        stripped = line.strip()
        # 알려진 프롬프트 패턴
        for pattern in _IDLE_PATTERNS:
            if pattern in stripped:
                return True
        # ">" 프롬프트 (단독 또는 줄 시작)
        if stripped == ">" or stripped.startswith("> "):
            return True

    # 마지막 줄이 빈 줄이고, 이전 줄에 내용이 있으면 idle
    # (tmux capture-pane은 idle 상태에서 trailing newline을 포함)
    if len(raw_lines) >= 2 and not raw_lines[-1].strip() and non_empty:
        return True

    return False
