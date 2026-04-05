"""E2E testing infrastructure for ClawTeam.

Manages local server processes, executes HTTP queries, and captures logs
for end-to-end integration testing.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import threading
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Server Process Manager
# ---------------------------------------------------------------------------

@dataclass
class ServerProcess:
    """Tracks a managed server process."""
    name: str
    command: list[str]
    port: int
    pid: int = 0
    status: str = "stopped"   # stopped, starting, running, failed
    cwd: str = ""
    env: dict[str, str] = field(default_factory=dict)
    _process: subprocess.Popen | None = field(default=None, repr=False)
    _log_lines: list[str] = field(default_factory=list, repr=False)
    _log_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    started_at: float = 0.0


class ServerManager:
    """Manages local server processes for E2E testing."""

    _MAX_LOG_LINES = 500

    def __init__(self) -> None:
        self._servers: dict[str, ServerProcess] = {}

    def register(
        self,
        name: str,
        command: list[str],
        port: int,
        cwd: str = "",
        env: dict[str, str] | None = None,
    ) -> ServerProcess:
        """Register a server configuration."""
        server = ServerProcess(
            name=name,
            command=command,
            port=port,
            cwd=cwd or os.getcwd(),
            env=env or {},
        )
        self._servers[name] = server
        return server

    def start(self, name: str, timeout: float = 30.0) -> ServerProcess:
        """Start a registered server and wait for it to accept connections."""
        server = self._servers.get(name)
        if not server:
            raise ValueError(f"Unknown server: {name}")
        if server.status == "running":
            return server

        server.status = "starting"
        spawn_env = {**os.environ, **server.env}

        try:
            proc = subprocess.Popen(
                server.command,
                cwd=server.cwd,
                env=spawn_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            server._process = proc
            server.pid = proc.pid
            server.started_at = time.monotonic()

            # Start log capture thread
            thread = threading.Thread(
                target=self._capture_logs,
                args=(server,),
                daemon=True,
            )
            thread.start()

            # Wait for health check
            if self._wait_for_ready(server, timeout):
                server.status = "running"
                logger.info("Server %s started on port %d (pid=%d)", name, server.port, server.pid)
            else:
                server.status = "failed"
                logger.warning("Server %s failed to become ready within %.0fs", name, timeout)
                self.stop(name)

        except Exception as exc:
            server.status = "failed"
            logger.error("Failed to start server %s: %s", name, exc)

        return server

    def stop(self, name: str, timeout: float = 10.0) -> None:
        """Stop a running server gracefully."""
        server = self._servers.get(name)
        if not server or not server._process:
            return

        try:
            server._process.send_signal(signal.SIGTERM)
            server._process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            server._process.kill()
            server._process.wait(timeout=5)
        except ProcessLookupError:
            pass
        finally:
            server.status = "stopped"
            server.pid = 0
            server._process = None
            logger.info("Server %s stopped", name)

    def stop_all(self) -> None:
        """Stop all running servers."""
        for name in list(self._servers):
            if self._servers[name].status == "running":
                self.stop(name)

    def status(self, name: str) -> dict[str, Any]:
        """Get server status."""
        server = self._servers.get(name)
        if not server:
            return {"name": name, "status": "unknown"}
        return {
            "name": server.name,
            "status": server.status,
            "port": server.port,
            "pid": server.pid,
            "uptime": time.monotonic() - server.started_at if server.status == "running" else 0,
            "log_lines": len(server._log_lines),
        }

    def list_servers(self) -> list[dict[str, Any]]:
        """List all registered servers with status."""
        return [self.status(name) for name in self._servers]

    def get_logs(self, name: str, last_n: int = 50) -> list[str]:
        """Get recent log lines from a server."""
        server = self._servers.get(name)
        if not server:
            return []
        with server._log_lock:
            return list(server._log_lines[-last_n:])

    def _capture_logs(self, server: ServerProcess) -> None:
        """Background thread: capture stdout/stderr."""
        proc = server._process
        if not proc or not proc.stdout:
            return
        for line in proc.stdout:
            with server._log_lock:
                server._log_lines.append(line.rstrip("\n"))
                if len(server._log_lines) > self._MAX_LOG_LINES:
                    server._log_lines = server._log_lines[-self._MAX_LOG_LINES:]

    def _wait_for_ready(self, server: ServerProcess, timeout: float) -> bool:
        """Poll health endpoint until server responds."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                req = urllib.request.Request(f"http://localhost:{server.port}/", method="GET")
                with urllib.request.urlopen(req, timeout=2):
                    return True
            except Exception:
                pass
            # Check if process died
            if server._process and server._process.poll() is not None:
                return False
            time.sleep(1.0)
        return False


# ---------------------------------------------------------------------------
# HTTP Query Executor
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HttpResponse:
    """Captured HTTP response."""
    status_code: int
    headers: dict[str, str]
    body: str
    elapsed_ms: float
    error: str = ""


def execute_http(
    method: str,
    url: str,
    body: dict | str | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> HttpResponse:
    """Execute an HTTP request and capture the response."""
    start = time.monotonic()
    req_headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        req_headers.update(headers)

    if isinstance(body, dict):
        data = json.dumps(body).encode("utf-8")
    elif isinstance(body, str):
        data = body.encode("utf-8")
    else:
        data = None

    req = urllib.request.Request(url, data=data, method=method.upper(), headers=req_headers)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = (time.monotonic() - start) * 1000
            resp_body = resp.read().decode("utf-8", errors="replace")
            resp_headers = dict(resp.headers)
            return HttpResponse(
                status_code=resp.status,
                headers=resp_headers,
                body=resp_body,
                elapsed_ms=round(elapsed, 1),
            )
    except urllib.error.HTTPError as exc:
        elapsed = (time.monotonic() - start) * 1000
        error_body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return HttpResponse(
            status_code=exc.code,
            headers=dict(exc.headers) if exc.headers else {},
            body=error_body,
            elapsed_ms=round(elapsed, 1),
            error=str(exc.reason),
        )
    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        return HttpResponse(
            status_code=0,
            headers={},
            body="",
            elapsed_ms=round(elapsed, 1),
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# Test Scenario Runner
# ---------------------------------------------------------------------------

@dataclass
class TestStep:
    """A single step in an E2E test scenario."""
    name: str
    method: str
    url: str
    body: dict | None = None
    headers: dict[str, str] | None = None
    expect_status: int = 200
    expect_body_contains: str = ""
    server_log_contains: str = ""
    server_name: str = ""


@dataclass
class StepResult:
    """Result of a single test step."""
    step_name: str
    passed: bool
    response: HttpResponse | None = None
    failure_reason: str = ""
    matched_logs: list[str] = field(default_factory=list)


class TestRunner:
    """Runs E2E test scenarios against managed servers."""

    def __init__(self, server_manager: ServerManager) -> None:
        self._manager = server_manager

    def run_scenario(self, steps: list[TestStep]) -> list[StepResult]:
        """Execute a sequence of test steps."""
        results = []
        for step in steps:
            result = self._run_step(step)
            results.append(result)
            if not result.passed:
                logger.warning("Step '%s' failed: %s", step.name, result.failure_reason)
                # Continue with remaining steps (don't abort)
        return results

    def _run_step(self, step: TestStep) -> StepResult:
        """Execute a single test step."""
        response = execute_http(
            method=step.method,
            url=step.url,
            body=step.body,
            headers=step.headers,
        )

        # Check status code
        if response.status_code != step.expect_status:
            return StepResult(
                step_name=step.name,
                passed=False,
                response=response,
                failure_reason=f"Expected status {step.expect_status}, got {response.status_code}",
            )

        # Check response body
        if step.expect_body_contains and step.expect_body_contains not in response.body:
            return StepResult(
                step_name=step.name,
                passed=False,
                response=response,
                failure_reason=f"Response body does not contain '{step.expect_body_contains}'",
            )

        # Check server logs
        matched_logs = []
        if step.server_log_contains and step.server_name:
            logs = self._manager.get_logs(step.server_name, last_n=100)
            matched_logs = [line for line in logs if step.server_log_contains in line]
            if not matched_logs:
                return StepResult(
                    step_name=step.name,
                    passed=False,
                    response=response,
                    failure_reason=f"Server logs do not contain '{step.server_log_contains}'",
                )

        return StepResult(
            step_name=step.name,
            passed=True,
            response=response,
            matched_logs=matched_logs,
        )


def format_results(results: list[StepResult]) -> str:
    """Format test results as a human-readable report."""
    lines = ["E2E Test Results", "=" * 40]
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    lines.append(f"Passed: {passed}/{total}")
    lines.append("")

    for r in results:
        icon = "PASS" if r.passed else "FAIL"
        lines.append(f"[{icon}] {r.step_name}")
        if r.response:
            lines.append(f"  Status: {r.response.status_code} ({r.response.elapsed_ms}ms)")
        if r.failure_reason:
            lines.append(f"  Reason: {r.failure_reason}")
        if r.matched_logs:
            lines.append(f"  Matched logs: {len(r.matched_logs)} lines")

    return "\n".join(lines)
