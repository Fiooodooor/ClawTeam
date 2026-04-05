"""Tmux spawn backend - launches agents in tmux windows for visual monitoring."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
import uuid
from xml.sax.saxutils import escape

from clawteam.spawn.adapters import (
    NativeCliAdapter,
    is_claude_command,
    is_codex_command,
    is_gemini_command,
    is_kimi_command,
    is_nanobot_command,
    is_opencode_command,
    is_pi_command,
    is_qwen_command,
)
from clawteam.spawn.base import SpawnBackend
from clawteam.spawn.cli_env import build_spawn_path, resolve_clawteam_executable
from clawteam.spawn.command_validation import validate_spawn_command
from clawteam.spawn.keepalive import build_keepalive_shell_command, build_resume_command
from clawteam.spawn.runtime_notification import render_runtime_notification
from clawteam.spawn.session_capture import persist_spawned_session, prepare_session_capture
from clawteam.team.models import get_data_dir

_SHELL_ENV_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


class TmuxBackend(SpawnBackend):
    """Spawn agents in tmux windows for visual monitoring.

    Each agent gets its own tmux window in a session named ``clawteam-{team}``.
    Agents run in interactive mode so their work is visible in the tmux pane.
    """

    def __init__(self):
        # (team_name, agent_name) -> {"target": "...", "pane_id": "%N"}
        self._agents: dict[tuple[str, str], dict[str, str]] = {}
        self._adapter = NativeCliAdapter()

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
        system_prompt: str | None = None,
        is_leader: bool = False,
        keepalive: bool = False,
    ) -> str:
        if not shutil.which("tmux"):
            return "Error: tmux not installed"

        session_name = f"clawteam-{team_name}"
        clawteam_bin = resolve_clawteam_executable()
        env_vars = os.environ.copy()
        # Interactive CLIs like Codex refuse to start when TERM=dumb is inherited
        # from a non-interactive shell. tmux provides a real terminal, so we
        # normalize TERM to a sensible value before exporting it into the pane.
        if env_vars.get("TERM", "").lower() == "dumb":
            env_vars["TERM"] = "xterm-256color"
        env_vars.setdefault("CLAWTEAM_DATA_DIR", str(get_data_dir()))
        env_vars.update({
            "CLAWTEAM_AGENT_ID": agent_id,
            "CLAWTEAM_AGENT_NAME": agent_name,
            "CLAWTEAM_AGENT_TYPE": agent_type,
            "CLAWTEAM_TEAM_NAME": team_name,
            "CLAWTEAM_AGENT_LEADER": "1" if is_leader else "0",
        })
        if cwd:
            env_vars["CLAWTEAM_WORKSPACE_DIR"] = cwd
        # Inject context awareness flags
        env_vars["CLAWTEAM_CONTEXT_ENABLED"] = "1"
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

        session_capture = prepare_session_capture(
            command,
            team_name=team_name,
            agent_name=agent_name,
            cwd=cwd,
            prompt=prompt,
        )
        prepared = self._adapter.prepare_command(
            session_capture.command,
            prompt=prompt,
            cwd=cwd,
            skip_permissions=skip_permissions,
            agent_name=agent_name,
            interactive=True,
            container_env=env_vars,
        )
        normalized_command = prepared.normalized_command
        validation_command = normalized_command
        final_command = list(prepared.final_command)
        post_launch_prompt = prepared.post_launch_prompt
        if system_prompt and (is_claude_command(normalized_command) or is_pi_command(normalized_command)):
            insert_at = final_command.index("-p") if "-p" in final_command else len(final_command)
            final_command[insert_at:insert_at] = ["--append-system-prompt", system_prompt]
        resume_base = build_resume_command(normalized_command)
        resume_command: list[str] = []
        if resume_base:
            resume_prepared = self._adapter.prepare_command(
                resume_base,
                cwd=cwd,
                skip_permissions=skip_permissions,
                agent_name=agent_name,
                interactive=True,
                container_env=env_vars,
            )
            resume_command = list(resume_prepared.final_command)
            if system_prompt and (
                is_claude_command(resume_prepared.normalized_command)
                or is_pi_command(resume_prepared.normalized_command)
            ):
                insert_at = resume_command.index("-p") if "-p" in resume_command else len(resume_command)
                resume_command[insert_at:insert_at] = ["--append-system-prompt", system_prompt]

        command_error = validate_spawn_command(validation_command, path=env_vars["PATH"], cwd=cwd)
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

        wrapped_cmd = build_keepalive_shell_command(
            final_command,
            resume_command=resume_command,
            clawteam_bin=clawteam_bin if os.path.isabs(clawteam_bin) else "clawteam",
            team_name=team_name,
            agent_name=agent_name,
            keepalive=keepalive,
        )
        # Unset Claude nesting-detection env vars so spawned claude agents
        # don't refuse to start when the leader is itself a claude session.
        unset_clause = "unset CLAUDECODE CLAUDE_CODE_ENTRYPOINT CLAUDE_CODE_SESSION 2>/dev/null; "
        if cwd:
            full_cmd = f"{unset_clause}{env_source_cmd}; cd {shlex.quote(cwd)} && {wrapped_cmd}"
        else:
            full_cmd = f"{unset_clause}{env_source_cmd}; {wrapped_cmd}"

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

        # Keep leader pane alive even if the agent process exits, so it can be
        # re-activated or inspected later.
        if is_leader:
            subprocess.run(
                ["tmux", "set-option", "-t", target, "remain-on-exit", "on"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )

        # Set tmux native hooks for reliable lifecycle management
        clawteam_cmd = shlex.quote(clawteam_bin) if os.path.isabs(clawteam_bin) else "clawteam"
        _exit_hook_cmd = (
            f"{clawteam_cmd} lifecycle on-exit --team {shlex.quote(team_name)} "
            f"--agent {shlex.quote(agent_name)}"
        )
        _crash_hook_cmd = (
            f"{clawteam_cmd} lifecycle on-crash --team {shlex.quote(team_name)} "
            f"--agent {shlex.quote(agent_name)}"
        )
        subprocess.run(
            ["tmux", "set-hook", "-t", target, "pane-exited",
             f"run-shell '{_exit_hook_cmd}'"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        subprocess.run(
            ["tmux", "set-hook", "-t", target, "pane-died",
             f"run-shell '{_crash_hook_cmd}'"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

        from clawteam.config import load_config

        cfg = load_config()
        pane_ready_timeout = min(cfg.spawn_ready_timeout, max(4.0, cfg.spawn_prompt_delay + 2.0))
        if not _wait_for_tmux_pane(
            target,
            timeout_seconds=pane_ready_timeout,
            poll_interval_seconds=0.2,
        ):
            return (
                f"Error: tmux pane for '{normalized_command[0]}' did not become visible "
                f"within {pane_ready_timeout:.1f}s. Verify the CLI works standalone before "
                "using it with clawteam spawn."
            )

        _confirm_workspace_trust_if_prompted(
            target,
            normalized_command,
            timeout_seconds=cfg.spawn_ready_timeout,
        )

        if post_launch_prompt and is_codex_command(normalized_command):
            _dismiss_codex_update_prompt_if_present(
                target,
                normalized_command,
                timeout_seconds=pane_ready_timeout,
                poll_interval_seconds=0.2,
            )

        if post_launch_prompt:
            _wait_for_cli_ready(
                target,
                timeout_seconds=cfg.spawn_ready_timeout,
                fallback_delay=cfg.spawn_prompt_delay,
            )
            _inject_prompt_via_buffer(target, agent_name, post_launch_prompt)
        elif (
            prompt
            and not is_codex_command(normalized_command)
            and not is_nanobot_command(normalized_command)
            and not is_gemini_command(normalized_command)
            and not is_kimi_command(normalized_command)
            and not is_qwen_command(normalized_command)
            and not is_opencode_command(normalized_command)
        ):
            # Other interactive TUIs still need the screen to be live before we
            # inject text via tmux send-keys.
            _wait_for_tui_ready(
                target,
                timeout=cfg.spawn_ready_timeout,
                fallback_delay=cfg.spawn_prompt_delay,
            )
            subprocess.run(
                ["tmux", "send-keys", "-t", target, prompt, "Enter"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        # Capture pane id (e.g. %42) so future runtime injections target by
        # stable pane id rather than the user-renamable window name.
        pane_id = ""
        pane_id_result = subprocess.run(
            ["tmux", "display-message", "-p", "-t", target, "#{pane_id}"],
            capture_output=True, text=True,
        )
        if pane_id_result.returncode == 0:
            pane_id = pane_id_result.stdout.strip()

        self._agents[(team_name, agent_name)] = {
            "target": target,
            "pane_id": pane_id,
        }

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
            command=list(final_command),
        )
        persist_spawned_session(
            session_capture,
            team_name=team_name,
            agent_name=agent_name,
            command=list(final_command),
        )

        # Emit AfterWorkerSpawn event
        try:
            from clawteam.events.global_bus import get_event_bus
            from clawteam.events.types import AfterWorkerSpawn
            get_event_bus().emit_async(AfterWorkerSpawn(
                team_name=team_name,
                agent_name=agent_name,
                agent_id=agent_id,
                backend="tmux",
                target=target,
            ))
        except Exception:
            pass

        return f"Agent '{agent_name}' spawned in tmux ({target})"

    def list_running(self) -> list[dict[str, str]]:
        return [
            {
                "name": agent,
                "team": team,
                "target": rec.get("target", ""),
                "pane_id": rec.get("pane_id", ""),
                "backend": "tmux",
            }
            for (team, agent), rec in self._agents.items()
        ]

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
                render_runtime_notification(envelope),
            )
        except Exception as exc:
            return False, f"runtime injection failed for '{target}': {exc}"

        return True, f"Injected runtime notification into {target}"

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
    """Acknowledge startup confirmation prompts for interactive CLIs.

    Claude Code and Codex can stop at a directory trust prompt when launched in
    a fresh git worktree. Claude can also pause on a confirmation dialog when
    `--dangerously-skip-permissions` is enabled. Detect these screens before
    any prompt injection so the interactive TUI remains intact.
    """
    if not (is_claude_command(command) or is_codex_command(command) or is_gemini_command(command)):
        return False

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        pane = subprocess.run(
            ["tmux", "capture-pane", "-p", "-t", target],
            capture_output=True,
            text=True,
        )
        pane_text = pane.stdout.lower() if pane.returncode == 0 else ""
        action = _startup_prompt_action(command, pane_text)
        if action == "enter":
            subprocess.run(
                ["tmux", "send-keys", "-t", target, "Enter"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            time.sleep(0.5)
            return True
        if action == "down-enter":
            subprocess.run(
                ["tmux", "send-keys", "-t", target, "-l", "\x1b[B"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            time.sleep(0.2)
            subprocess.run(
                ["tmux", "send-keys", "-t", target, "Enter"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            time.sleep(0.5)
            return True

        time.sleep(poll_interval_seconds)

    return False


def _startup_prompt_action(command: list[str], pane_text: str) -> str | None:
    """Return the key action needed to dismiss a startup confirmation prompt."""
    if _looks_like_claude_skip_permissions_prompt(command, pane_text):
        return "down-enter"
    if _looks_like_workspace_trust_prompt(command, pane_text):
        return "enter"
    return None


def _wait_for_tmux_pane(
    target: str,
    timeout_seconds: float = 5.0,
    poll_interval_seconds: float = 0.2,
) -> bool:
    """Poll tmux until the target pane exists and is observable."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        pane = subprocess.run(
            ["tmux", "list-panes", "-t", target, "-F", "#{pane_id}"],
            capture_output=True,
            text=True,
        )
        if pane.returncode == 0 and pane.stdout.strip():
            return True
        time.sleep(poll_interval_seconds)

    return False


def _looks_like_workspace_trust_prompt(command: list[str], pane_text: str) -> bool:
    """Return True when the tmux pane is showing a trust confirmation dialog."""
    if not pane_text:
        return False

    if is_claude_command(command):
        return ("trust this folder" in pane_text or "trust the contents" in pane_text) and (
            "enter to confirm" in pane_text or "press enter" in pane_text or "enter to continue" in pane_text
        )

    if is_codex_command(command):
        return (
            "trust the contents of this directory" in pane_text
            and "press enter to continue" in pane_text
        )

    if is_gemini_command(command):
        return "trust folder" in pane_text or "trust parent folder" in pane_text

    return False


def _looks_like_claude_skip_permissions_prompt(command: list[str], pane_text: str) -> bool:
    """Return True when Claude is waiting for the dangerous-permissions confirmation."""
    if not pane_text or not is_claude_command(command):
        return False

    has_accept_choice = "yes, i accept" in pane_text
    has_permissions_warning = (
        "dangerously-skip-permissions" in pane_text
        or "skip permissions" in pane_text
        or "permission" in pane_text
        or "approval" in pane_text
    )
    return has_accept_choice and has_permissions_warning


def _looks_like_codex_update_prompt(pane_text: str) -> bool:
    """Return True when Codex is showing the update gate before the main TUI."""
    if not pane_text:
        return False

    return (
        "update available" in pane_text
        and "press enter to continue" in pane_text
        and ("update now" in pane_text or "skip until next version" in pane_text)
    )


def _dismiss_codex_update_prompt_if_present(
    target: str,
    command: list[str],
    timeout_seconds: float = 5.0,
    poll_interval_seconds: float = 0.2,
) -> bool:
    """Dismiss the Codex update gate if it is blocking the interactive UI."""
    if not is_codex_command(command):
        return False

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        pane = subprocess.run(
            ["tmux", "capture-pane", "-p", "-t", target],
            capture_output=True,
            text=True,
        )
        pane_text = pane.stdout.lower() if pane.returncode == 0 else ""
        if _looks_like_codex_update_prompt(pane_text):
            subprocess.run(
                ["tmux", "send-keys", "-t", target, "Enter"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            time.sleep(0.5)
            return True

        if pane_text and "openai codex" in pane_text:
            return False

        time.sleep(poll_interval_seconds)

    return False


def _wait_for_cli_ready(
    target: str,
    timeout_seconds: float = 30.0,
    fallback_delay: float = 2.0,
    poll_interval: float = 1.0,
) -> bool:
    """Poll tmux pane until an interactive CLI shows an input prompt.

    Uses two complementary heuristics:

    1. **Prompt indicators** — common prompt characters (``❯``, ``>``,
       ``›``) or well-known hint lines in the last few visible lines.
    2. **Content stabilization** — if the pane output has stopped changing
       for two consecutive polls and contains visible text, the CLI has
       likely finished initialisation and is waiting for input.

    Returns True when ready, False on timeout (caller should still
    attempt injection as a best-effort).
    """
    deadline = time.monotonic() + timeout_seconds
    last_content = ""
    stable_count = 0

    while time.monotonic() < deadline:
        pane = subprocess.run(
            ["tmux", "capture-pane", "-p", "-t", target],
            capture_output=True,
            text=True,
        )
        if pane.returncode != 0:
            time.sleep(poll_interval)
            continue

        text = pane.stdout
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        tail = lines[-10:] if len(lines) >= 10 else lines

        for line in tail:
            if line.startswith(("❯", ">", "›")):
                return True
            if "Try " in line and "write a test" in line:
                return True

        if text == last_content and lines:
            stable_count += 1
            if stable_count >= 2:
                return True
        else:
            stable_count = 0
            last_content = text

        time.sleep(poll_interval)
    time.sleep(fallback_delay)
    return False


def _wait_for_tui_ready(
    target: str,
    timeout: float = 30.0,
    fallback_delay: float = 2.0,
    poll_interval: float = 0.5,
) -> None:
    """Poll the tmux pane until the TUI appears ready, then return.

    This is used for interactive CLIs that still rely on tmux send-keys prompt
    injection. When readiness is not detected before ``timeout``, we keep the
    previous fallback behaviour and sleep for ``fallback_delay`` seconds.
    """

    ready_hints = ("╭", "╔", "┌", "│", "║", "✓", ">", "❯", "›")
    time.sleep(0.5)

    deadline = time.time() + timeout
    while time.time() < deadline:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", target, "-p"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and any(hint in result.stdout for hint in ready_hints):
            return
        time.sleep(poll_interval)

    time.sleep(fallback_delay)


# Foreground commands a pane may be running where it is *safe* to paste a
# notification block. Anything not on this list — bash, zsh, fish, less,
# vim, fzf, tmux itself, etc. — would interpret the paste as terminal input
# (potentially executing $() / backticks). Refuse injection in those cases.
_INJECT_SAFE_COMMANDS = frozenset({
    "claude",
    "codex",
    "gemini",
    "kimi",
    "qwen",
    "opencode",
    "nanobot",
    "openclaw",
    "pi",
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
        try:
            _run_tmux(["delete-buffer", "-b", buf_name])
        except RuntimeError:
            pass
    finally:
        os.unlink(tmp_path)
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
