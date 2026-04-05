"""GitHub integration via ``gh`` CLI.

Provides helpers to query PRs, Actions runs, repo info, and diffs
using the locally authenticated ``gh`` CLI tool. All functions are
subprocess-based and gracefully return empty results when ``gh`` is
unavailable or the repo is inaccessible.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# gh CLI detection
# ---------------------------------------------------------------------------

def _find_gh() -> str | None:
    """Return path to ``gh`` binary, or *None* if not found."""
    found = shutil.which("gh")
    if found:
        return found
    import os
    for candidate in ["/opt/homebrew/bin/gh", "/usr/local/bin/gh"]:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def is_gh_available() -> bool:
    """Return *True* if ``gh`` CLI is installed and authenticated."""
    gh = _find_gh()
    if not gh:
        return False
    try:
        result = subprocess.run(
            [gh, "auth", "status"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def gh_auth_user() -> str:
    """Return the authenticated GitHub username, or empty string."""
    gh = _find_gh()
    if not gh:
        return ""
    try:
        result = subprocess.run(
            [gh, "api", "user", "--jq", ".login"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Raw gh execution helper
# ---------------------------------------------------------------------------

def _run_gh(args: list[str], *, timeout: int = 30) -> str:
    """Run ``gh`` with *args* and return stdout. Empty string on failure."""
    gh = _find_gh()
    if not gh:
        return ""
    try:
        result = subprocess.run(
            [gh] + args,
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            logger.debug("gh %s exit=%d stderr=%s", " ".join(args[:4]), result.returncode, result.stderr[:200])
            return ""
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        logger.warning("gh %s timed out after %ds", " ".join(args[:4]), timeout)
        return ""
    except Exception as exc:
        logger.debug("gh error: %s", exc)
        return ""


def _run_gh_json(args: list[str], *, timeout: int = 30) -> Any:
    """Run ``gh`` and parse stdout as JSON. Returns *None* on failure."""
    raw = _run_gh(args, timeout=timeout)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# PR helpers
# ---------------------------------------------------------------------------

@dataclass
class PRInfo:
    """Lightweight pull request summary."""
    number: int = 0
    title: str = ""
    state: str = ""
    author: str = ""
    url: str = ""
    head_branch: str = ""
    base_branch: str = ""
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0
    mergeable: str = ""
    review_decision: str = ""
    labels: list[str] = field(default_factory=list)
    checks_status: str = ""  # "success", "failure", "pending", ""
    checks: list[dict[str, str]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


def get_pr(repo: str, pr_number: int) -> PRInfo | None:
    """Fetch PR details for *repo* (e.g. ``owner/repo``) and *pr_number*."""
    data = _run_gh_json([
        "pr", "view", str(pr_number),
        "--repo", repo,
        "--json", "number,title,state,author,url,headRefName,baseRefName,"
                  "additions,deletions,changedFiles,mergeable,reviewDecision,"
                  "labels,createdAt,updatedAt,statusCheckRollup",
    ])
    if not data:
        return None

    checks_raw = data.get("statusCheckRollup") or []
    checks = []
    overall = ""
    for c in checks_raw:
        name = c.get("name") or c.get("context") or "?"
        conclusion = (c.get("conclusion") or c.get("state") or "pending").lower()
        checks.append({"name": name, "status": conclusion})
        if conclusion in ("failure", "error"):
            overall = "failure"
        elif conclusion == "success" and overall != "failure":
            overall = "success"
        elif conclusion in ("pending", "in_progress", "queued") and overall not in ("failure",):
            overall = "pending"

    labels = [lb.get("name", "") for lb in (data.get("labels") or [])]

    return PRInfo(
        number=data.get("number", pr_number),
        title=data.get("title", ""),
        state=data.get("state", ""),
        author=(data.get("author") or {}).get("login", ""),
        url=data.get("url", ""),
        head_branch=data.get("headRefName", ""),
        base_branch=data.get("baseRefName", ""),
        additions=data.get("additions", 0),
        deletions=data.get("deletions", 0),
        changed_files=data.get("changedFiles", 0),
        mergeable=data.get("mergeable", ""),
        review_decision=data.get("reviewDecision", ""),
        labels=labels,
        checks_status=overall,
        checks=checks,
        created_at=data.get("createdAt", ""),
        updated_at=data.get("updatedAt", ""),
    )


def get_pr_diff(repo: str, pr_number: int, *, max_chars: int = 8000) -> str:
    """Fetch the unified diff for a PR, truncated to *max_chars*."""
    diff = _run_gh(["pr", "diff", str(pr_number), "--repo", repo], timeout=30)
    if len(diff) > max_chars:
        return diff[:max_chars] + f"\n\n... (truncated, {len(diff)} total chars)"
    return diff


def get_pr_files(repo: str, pr_number: int) -> list[dict[str, str]]:
    """Return list of changed files with path, status, additions, deletions."""
    data = _run_gh_json([
        "api", f"repos/{repo}/pulls/{pr_number}/files",
        "--paginate", "--jq",
        '[.[] | {filename, status, additions, deletions, changes}]',
    ])
    if isinstance(data, list):
        return data
    return []


def list_prs(repo: str, *, state: str = "open", limit: int = 10) -> list[dict]:
    """List PRs for a repo."""
    data = _run_gh_json([
        "pr", "list", "--repo", repo,
        "--state", state, "--limit", str(limit),
        "--json", "number,title,state,author,headRefName,baseRefName,"
                  "createdAt,updatedAt,url,labels,reviewDecision",
    ])
    return data if isinstance(data, list) else []


# ---------------------------------------------------------------------------
# GitHub Actions helpers
# ---------------------------------------------------------------------------

@dataclass
class ActionsRun:
    """Summary of a GitHub Actions workflow run."""
    id: int = 0
    name: str = ""
    status: str = ""
    conclusion: str = ""
    head_branch: str = ""
    event: str = ""
    url: str = ""
    created_at: str = ""
    updated_at: str = ""
    run_number: int = 0
    jobs: list[dict[str, str]] = field(default_factory=list)


def list_runs(
    repo: str,
    *,
    branch: str = "",
    limit: int = 10,
    workflow: str = "",
) -> list[ActionsRun]:
    """List recent workflow runs."""
    args = [
        "run", "list", "--repo", repo,
        "--limit", str(limit),
        "--json", "databaseId,name,status,conclusion,headBranch,"
                  "event,url,createdAt,updatedAt,number",
    ]
    if branch:
        args.extend(["--branch", branch])
    if workflow:
        args.extend(["--workflow", workflow])

    data = _run_gh_json(args)
    if not isinstance(data, list):
        return []

    runs = []
    for r in data:
        runs.append(ActionsRun(
            id=r.get("databaseId", 0),
            name=r.get("name", ""),
            status=r.get("status", ""),
            conclusion=r.get("conclusion", ""),
            head_branch=r.get("headBranch", ""),
            event=r.get("event", ""),
            url=r.get("url", ""),
            created_at=r.get("createdAt", ""),
            updated_at=r.get("updatedAt", ""),
            run_number=r.get("number", 0),
        ))
    return runs


def get_run_jobs(repo: str, run_id: int) -> list[dict]:
    """Get jobs for a specific run."""
    data = _run_gh_json([
        "run", "view", str(run_id),
        "--repo", repo,
        "--json", "jobs",
    ])
    if isinstance(data, dict):
        return data.get("jobs", [])
    return []


def get_failed_run_logs(repo: str, run_id: int, *, max_chars: int = 4000) -> str:
    """Get logs for a failed run, focusing on error output."""
    raw = _run_gh(["run", "view", str(run_id), "--repo", repo, "--log-failed"], timeout=30)
    if len(raw) > max_chars:
        return raw[-max_chars:]  # Keep tail (most relevant errors)
    return raw


# ---------------------------------------------------------------------------
# Repo helpers
# ---------------------------------------------------------------------------

def get_repo_info(repo: str) -> dict:
    """Get basic repo info (name, description, default branch, visibility)."""
    data = _run_gh_json([
        "repo", "view", repo,
        "--json", "name,owner,description,defaultBranchRef,isPrivate,"
                  "url,stargazerCount,forkCount,languages",
    ])
    return data if isinstance(data, dict) else {}


def list_workflows(repo: str) -> list[dict]:
    """List configured GitHub Actions workflows."""
    data = _run_gh_json([
        "workflow", "list", "--repo", repo,
        "--json", "id,name,state",
    ])
    return data if isinstance(data, list) else []


# ---------------------------------------------------------------------------
# PR number extraction from project title/description
# ---------------------------------------------------------------------------

_PR_PATTERNS = [
    re.compile(r"#(\d+)"),
    re.compile(r"PR[- ]?(\d+)", re.IGNORECASE),
    re.compile(r"pull/(\d+)"),
    re.compile(r"[A-Z]+-(\d+)"),  # Jira-style: LBOXAI-3229 → 3229
]


def extract_pr_number(text: str) -> int | None:
    """Try to extract a PR number from a project title or description."""
    for pattern in _PR_PATTERNS:
        m = pattern.search(text)
        if m:
            return int(m.group(1))
    return None


def extract_repo_from_text(text: str) -> str | None:
    """Try to extract ``owner/repo`` from text (GitHub URLs or mentions)."""
    # github.com/owner/repo
    m = re.search(r"github\.com/([^/\s]+/[^/\s]+)", text)
    if m:
        return m.group(1).rstrip("/").split("/pull")[0].split("/issues")[0]
    # owner/repo pattern — greedy on allowed chars (letters, digits, -, _, .)
    # Use a non-word-boundary end to handle Korean/Unicode adjacent chars
    m = re.search(r"(?:^|[\s(])([a-zA-Z0-9_-]+/[a-zA-Z0-9_.\-]+[a-zA-Z0-9])", text)
    if m:
        candidate = m.group(1)
        # Filter out obvious non-repos (date patterns, file paths)
        if "/" in candidate and not candidate.startswith("http") and ".." not in candidate:
            return candidate
    return None


# ---------------------------------------------------------------------------
# Aggregate: fetch full PR context for a project
# ---------------------------------------------------------------------------

def fetch_pr_context_for_project(
    repo: str,
    pr_number: int,
    *,
    include_diff: bool = True,
    max_diff_chars: int = 6000,
) -> dict[str, Any]:
    """Fetch comprehensive PR context to inject into agent prompts.

    Returns a dict suitable for serialization to JSON:
    - ``pr``: PRInfo as dict
    - ``files``: changed file list
    - ``diff``: truncated unified diff (if include_diff)
    - ``actions``: recent Actions runs for the PR branch
    """
    pr = get_pr(repo, pr_number)
    if pr is None:
        return {"error": f"Could not fetch PR #{pr_number} from {repo}"}

    result: dict[str, Any] = {
        "pr": {
            "number": pr.number,
            "title": pr.title,
            "state": pr.state,
            "author": pr.author,
            "url": pr.url,
            "headBranch": pr.head_branch,
            "baseBranch": pr.base_branch,
            "additions": pr.additions,
            "deletions": pr.deletions,
            "changedFiles": pr.changed_files,
            "mergeable": pr.mergeable,
            "reviewDecision": pr.review_decision,
            "labels": pr.labels,
            "checksStatus": pr.checks_status,
            "checks": pr.checks,
            "createdAt": pr.created_at,
            "updatedAt": pr.updated_at,
        },
        "files": get_pr_files(repo, pr_number),
    }

    if include_diff:
        result["diff"] = get_pr_diff(repo, pr_number, max_chars=max_diff_chars)

    # Actions runs on the PR branch
    runs = list_runs(repo, branch=pr.head_branch, limit=5)
    result["actions"] = [
        {
            "id": r.id,
            "name": r.name,
            "status": r.status,
            "conclusion": r.conclusion,
            "event": r.event,
            "url": r.url,
            "createdAt": r.created_at,
        }
        for r in runs
    ]

    return result
