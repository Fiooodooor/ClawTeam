"""Datadog API client for ClawTeam (stdlib only).

Provides helpers to search logs, count events, and identify error
patterns using only the standard library (``urllib.request``).
All functions gracefully handle missing credentials and network failures.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------

def is_datadog_available() -> bool:
    """Check if Datadog credentials are configured."""
    return bool(os.environ.get("DD_API_KEY") and os.environ.get("DD_APP_KEY"))


def _dd_headers() -> dict[str, str]:
    return {
        "DD-API-KEY": os.environ.get("DD_API_KEY", ""),
        "DD-APPLICATION-KEY": os.environ.get("DD_APP_KEY", ""),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _dd_site() -> str:
    return os.environ.get("DD_SITE", "datadoghq.com")


# ---------------------------------------------------------------------------
# Low-level request helper
# ---------------------------------------------------------------------------

def _dd_request(method: str, path: str, data: dict | None = None) -> dict:
    """Send a request to Datadog API."""
    url = f"https://api.{_dd_site()}/{path.lstrip('/')}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, method=method, headers=_dd_headers())
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        logger.warning("Datadog API %s %s -> %d: %s", method, path, exc.code, exc.reason)
        raise
    except urllib.error.URLError as exc:
        logger.warning("Datadog API connection failed: %s", exc.reason)
        raise


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LogEntry:
    timestamp: str
    service: str
    status: str
    message: str
    host: str = ""
    tags: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search_logs(
    query: str,
    time_from: str = "now-1h",
    time_to: str = "now",
    limit: int = 50,
) -> list[LogEntry]:
    """Search Datadog logs.

    Args:
        query: Datadog log query (e.g. ``"service:lbox-ai-agent status:error"``)
        time_from: Start time (e.g. ``"now-1h"``, ``"2024-01-01T00:00:00Z"``)
        time_to: End time
        limit: Max results (capped at 1000)
    """
    data = _dd_request("POST", "api/v2/logs/events/search", {
        "filter": {
            "query": query,
            "from": time_from,
            "to": time_to,
        },
        "sort": "-timestamp",
        "page": {"limit": min(limit, 1000)},
    })

    entries: list[LogEntry] = []
    for log in data.get("data", []):
        attrs = log.get("attributes", {})
        entries.append(LogEntry(
            timestamp=attrs.get("timestamp", ""),
            service=attrs.get("service", ""),
            status=attrs.get("status", ""),
            message=attrs.get("message", "")[:2000],
            host=attrs.get("host", ""),
            tags=tuple(attrs.get("tags", [])),
        ))
    return entries


def get_log_count(
    query: str,
    time_from: str = "now-1h",
    time_to: str = "now",
) -> int:
    """Count logs matching a query."""
    data = _dd_request("POST", "api/v2/logs/analytics/aggregate", {
        "filter": {"query": query, "from": time_from, "to": time_to},
        "compute": [{"aggregation": "count"}],
    })
    buckets = data.get("data", {}).get("buckets", [])
    if buckets:
        return buckets[0].get("computes", {}).get("c0", 0)
    return 0


def get_error_patterns(
    service: str,
    time_from: str = "now-1h",
    time_to: str = "now",
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Get top error patterns for a service."""
    data = _dd_request("POST", "api/v2/logs/analytics/aggregate", {
        "filter": {
            "query": f"service:{service} status:error",
            "from": time_from,
            "to": time_to,
        },
        "group_by": [
            {
                "facet": "@error.kind",
                "limit": limit,
                "sort": {"aggregation": "count", "order": "desc"},
            },
        ],
        "compute": [{"aggregation": "count"}],
    })
    patterns: list[dict[str, Any]] = []
    for bucket in data.get("data", {}).get("buckets", []):
        by = bucket.get("by", {})
        computes = bucket.get("computes", {})
        patterns.append({
            "error_kind": by.get("@error.kind", "unknown"),
            "count": computes.get("c0", 0),
        })
    return patterns


# ---------------------------------------------------------------------------
# High-level context builder (for agent prompt injection)
# ---------------------------------------------------------------------------

def fetch_datadog_context_for_project(
    query: str,
    service: str = "",
) -> str:
    """Fetch Datadog log context for injection into agent prompts."""
    try:
        lines: list[str] = []

        # Error count
        error_count = get_log_count(f"{query} status:error")
        total_count = get_log_count(query)
        lines.append("Datadog Log Summary (last 1h):")
        lines.append(f"Total: {total_count} | Errors: {error_count}")

        # Recent error logs
        errors = search_logs(f"{query} status:error", limit=5)
        if errors:
            lines.append(f"\nRecent Errors ({len(errors)}):")
            for log in errors:
                lines.append(f"  [{log.timestamp}] {log.service}: {log.message[:200]}")

        # Error patterns
        if service:
            patterns = get_error_patterns(service)
            if patterns:
                lines.append("\nError Patterns:")
                for p in patterns[:5]:
                    lines.append(f"  {p['error_kind']}: {p['count']}건")

        return "\n".join(lines)
    except Exception as exc:
        logger.debug("Failed to fetch Datadog context: %s", exc)
        return ""
