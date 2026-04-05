"""Helpers for reusing OpenCode environment/config assets safely."""

from __future__ import annotations

import os
from pathlib import Path


def _unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def candidate_env_paths(workspace_dir: str | None = None) -> list[Path]:
    paths: list[Path] = []

    explicit = os.environ.get("CLAWTEAM_OPENCODE_ENV_FILE", "").strip()
    if explicit:
        paths.append(Path(explicit).expanduser())

    home = Path.home()
    paths.extend(
        [
            home / ".config" / "opencode" / ".env",
            home / ".opencode" / ".env",
        ]
    )

    if workspace_dir:
        cwd = Path(workspace_dir).resolve()
        for parent in [cwd, *cwd.parents]:
            paths.append(parent / ".opencode.env")
            paths.append(parent / ".env.opencode")
            paths.append(parent / "opencode-config" / ".env")

    return [path for path in _unique_paths(paths) if path.exists()]


def load_opencode_env(
    workspace_dir: str | None = None,
    *,
    override: bool = False,
) -> dict[str, object]:
    loaded_files: list[str] = []
    loaded_keys: list[str] = []

    for path in candidate_env_paths(workspace_dir):
        file_loaded = False
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not key:
                continue
            if not override and os.environ.get(key):
                continue
            os.environ[key] = value
            loaded_keys.append(key)
            file_loaded = True
        if file_loaded:
            loaded_files.append(str(path))

    return {
        "loadedFiles": loaded_files,
        "loadedKeyCount": len(loaded_keys),
        "loadedKeys": sorted(set(loaded_keys)),
    }


def discover_opencode_profile(workspace_dir: str | None = None) -> dict[str, object]:
    cwd = Path(workspace_dir).resolve() if workspace_dir else Path.cwd().resolve()
    skill_roots: list[Path] = [Path.home() / ".config" / "opencode" / "skills"]
    rules_paths: list[Path] = [Path.home() / ".config" / "opencode" / "AGENTS.md"]

    for parent in [cwd, *cwd.parents]:
        skill_roots.append(parent / "opencode-config" / "skills")
        rules_paths.append(parent / "opencode-config" / "AGENTS.md")
        rules_paths.append(parent / "AGENTS.md")

    skill_root = next((path for path in _unique_paths(skill_roots) if path.exists()), None)
    rules = [str(path) for path in _unique_paths(rules_paths) if path.exists()]
    skills_count = 0
    if skill_root and skill_root.exists():
        skills_count = len(list(skill_root.glob("*/SKILL.md")))

    # GitHub detection via gh CLI (no env var needed — uses gh auth)
    gh_configured = False
    gh_user = ""
    try:
        from clawteam.devteam.github import is_gh_available, gh_auth_user
        gh_configured = is_gh_available()
        if gh_configured:
            gh_user = gh_auth_user()
    except Exception:
        pass

    # Jira detection via dedicated client
    jira_configured = False
    try:
        from clawteam.devteam.jira import is_jira_available
        jira_configured = is_jira_available()
    except Exception:
        jira_configured = bool(os.environ.get("JIRA_API_TOKEN"))

    # Datadog detection via dedicated client
    dd_configured = False
    try:
        from clawteam.devteam.datadog import is_datadog_available
        dd_configured = is_datadog_available()
    except Exception:
        dd_configured = bool(
            os.environ.get("DD_API_KEY") and os.environ.get("DD_APP_KEY")
        )

    integrations = [
        {"name": "GitHub", "configured": gh_configured, "user": gh_user},
        {"name": "Jira", "configured": jira_configured},
        {"name": "Datadog", "configured": dd_configured},
        {"name": "Langfuse", "configured": bool(os.environ.get("LANGFUSE_BASE_URL") and ((os.environ.get("LANGFUSE_DEV_PUBLIC_KEY") and os.environ.get("LANGFUSE_DEV_SECRET_KEY")) or (os.environ.get("LANGFUSE_PRD_PUBLIC_KEY") and os.environ.get("LANGFUSE_PRD_SECRET_KEY"))))},
        {"name": "Slack MCP", "configured": bool(os.environ.get("SLACK_MCP_CLIENT_ID") and os.environ.get("SLACK_MCP_CLIENT_SECRET"))},
        {"name": "Slack Bot", "configured": bool(os.environ.get("SLACK_BOT_TOKEN"))},
        {"name": "OpenAI", "configured": bool(os.environ.get("OPENAI_API_KEY"))},
        {"name": "Obsidian", "configured": bool(os.environ.get("OBSIDIAN_VAULT_PATH") or os.environ.get("OBSIDIAN_BASE_PATH"))},
    ]

    return {
        "envFiles": [str(path) for path in candidate_env_paths(workspace_dir)],
        "rules": rules,
        "skillsRoot": str(skill_root) if skill_root else "",
        "skillsCount": skills_count,
        "integrations": integrations,
    }
