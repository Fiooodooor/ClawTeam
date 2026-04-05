"""Jira REST API client for ClawTeam (stdlib only).

Provides helpers to query issues, search via JQL, transition statuses,
add comments, and create new issues using only the standard library
(``urllib.request``).  All functions gracefully handle missing credentials
and network failures.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_TIMEOUT = 15


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------

def is_jira_available() -> bool:
    """Check if Jira credentials are configured."""
    return bool(os.environ.get("JIRA_API_TOKEN") and os.environ.get("JIRA_BASE_URL"))


def _jira_base_url() -> str:
    return os.environ.get("JIRA_BASE_URL", "").rstrip("/")


def _jira_auth_header() -> str:
    """Base64 encoded email:token for Jira Cloud."""
    email = os.environ.get("JIRA_USER_EMAIL", "")
    token = os.environ.get("JIRA_API_TOKEN", "")
    creds = base64.b64encode(f"{email}:{token}".encode()).decode()
    return f"Basic {creds}"


# ---------------------------------------------------------------------------
# Low-level request helper
# ---------------------------------------------------------------------------

def _jira_request(method: str, path: str, data: dict | None = None) -> dict | list:
    """Send a request to Jira REST API."""
    url = f"{_jira_base_url()}/rest/api/3/{path.lstrip('/')}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": _jira_auth_header(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        logger.warning("Jira API %s %s -> %d: %s", method, path, exc.code, exc.reason)
        raise
    except urllib.error.URLError as exc:
        logger.warning("Jira API connection failed: %s", exc.reason)
        raise


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class JiraIssue:
    key: str
    summary: str
    status: str
    assignee: str
    issue_type: str
    priority: str
    labels: tuple[str, ...] = ()
    description: str = ""
    url: str = ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_issue(issue_key: str) -> JiraIssue:
    """Fetch a single Jira issue."""
    data = _jira_request("GET", f"issue/{issue_key}")
    fields = data.get("fields", {})
    return JiraIssue(
        key=data.get("key", issue_key),
        summary=fields.get("summary", ""),
        status=fields.get("status", {}).get("name", ""),
        assignee=(fields.get("assignee") or {}).get("displayName", "Unassigned"),
        issue_type=fields.get("issuetype", {}).get("name", ""),
        priority=(fields.get("priority") or {}).get("name", ""),
        labels=tuple(fields.get("labels", [])),
        description=_extract_text(fields.get("description")),
        url=f"{_jira_base_url()}/browse/{data.get('key', issue_key)}",
    )


def search_issues(jql: str, max_results: int = 10) -> list[JiraIssue]:
    """Search issues using JQL."""
    encoded_jql = urllib.parse.quote(jql)
    fields_param = "summary,status,assignee,issuetype,priority,labels"
    path = f"search?jql={encoded_jql}&maxResults={max_results}&fields={fields_param}"
    data = _jira_request("GET", path)
    issues: list[JiraIssue] = []
    for item in data.get("issues", []):
        fields = item.get("fields", {})
        issues.append(JiraIssue(
            key=item.get("key", ""),
            summary=fields.get("summary", ""),
            status=fields.get("status", {}).get("name", ""),
            assignee=(fields.get("assignee") or {}).get("displayName", "Unassigned"),
            issue_type=fields.get("issuetype", {}).get("name", ""),
            priority=(fields.get("priority") or {}).get("name", ""),
            labels=tuple(fields.get("labels", [])),
            url=f"{_jira_base_url()}/browse/{item.get('key', '')}",
        ))
    return issues


def transition_issue(issue_key: str, transition_name: str) -> bool:
    """Move issue to a new status via transition."""
    transitions = _jira_request("GET", f"issue/{issue_key}/transitions")
    for t in transitions.get("transitions", []):
        if t.get("name", "").lower() == transition_name.lower():
            _jira_request(
                "POST",
                f"issue/{issue_key}/transitions",
                {"transition": {"id": t["id"]}},
            )
            return True
    return False


def add_comment(issue_key: str, body: str) -> dict:
    """Add a comment to an issue (Atlassian Document Format)."""
    return _jira_request("POST", f"issue/{issue_key}/comment", {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": body}],
                },
            ],
        },
    })


def create_issue(
    project_key: str,
    summary: str,
    issue_type: str = "Task",
    description: str = "",
) -> str:
    """Create a new issue, return issue key."""
    fields: dict[str, Any] = {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"name": issue_type},
    }
    if description:
        fields["description"] = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": description}],
                },
            ],
        }
    data = _jira_request("POST", "issue", {"fields": fields})
    return data.get("key", "")


# ---------------------------------------------------------------------------
# ADF helpers
# ---------------------------------------------------------------------------

def _extract_text(adf_doc: dict | None) -> str:
    """Minimal ADF (Atlassian Document Format) -> plain text."""
    if not adf_doc or not isinstance(adf_doc, dict):
        return ""
    texts: list[str] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text":
                texts.append(node.get("text", ""))
            for child in node.get("content", []):
                _walk(child)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(adf_doc)
    return " ".join(texts)


# ---------------------------------------------------------------------------
# High-level context builder (for agent prompt injection)
# ---------------------------------------------------------------------------

def extract_jira_key(text: str) -> str | None:
    """Extract first Jira issue key (e.g. ``PROJ-123``) from text."""
    match = re.search(r"[A-Z][A-Z0-9]+-\d+", text)
    return match.group() if match else None


def fetch_jira_context_for_project(issue_key: str) -> str:
    """Fetch Jira issue context for injection into agent prompts."""
    try:
        issue = get_issue(issue_key)
        return (
            f"Jira {issue.key}: {issue.summary}\n"
            f"Status: {issue.status} | Type: {issue.issue_type} | Priority: {issue.priority}\n"
            f"Assignee: {issue.assignee}\n"
            f"Labels: {', '.join(issue.labels) or 'none'}\n"
            f"URL: {issue.url}\n"
            + (f"Description: {issue.description[:1000]}\n" if issue.description else "")
        )
    except Exception as exc:
        logger.debug("Failed to fetch Jira context for %s: %s", issue_key, exc)
        return ""
