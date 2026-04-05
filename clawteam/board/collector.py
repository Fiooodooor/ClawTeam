"""Aggregates team/task/inbox data into plain dicts for rendering."""

from __future__ import annotations

import json
import logging
import threading
import time as _time
from collections import defaultdict
from typing import Any

from clawteam.board.liveness import agents_online
from clawteam.team.mailbox import MailboxManager
from clawteam.team.manager import TeamManager
from clawteam.team.tasks import TaskStore
from clawteam.workspace import get_workspace_manager

logger = logging.getLogger(__name__)


class BoardCollector:
    """Aggregates team/task/inbox data into plain dicts."""

    @staticmethod
    def _member_alias_index(config) -> dict[str, dict]:
        """Map known member identifiers to a canonical display payload."""
        unique_names: dict[str, list[dict]] = {}
        aliases: dict[str, dict] = {}
        for member in config.members:
            inbox_name = TeamManager.inbox_name_for(member)
            entry = {
                "memberKey": inbox_name,
                "name": member.name,
                "user": member.user,
            }
            aliases[inbox_name] = entry
            unique_names.setdefault(member.name, []).append(entry)

        # Only map bare logical names when they are unambiguous.
        for logical_name, entries in unique_names.items():
            if len(entries) == 1:
                aliases[logical_name] = entries[0]
        return aliases

    def collect_team_summary(self, team_name: str) -> dict:
        """Collect only the lightweight summary needed for overview screens."""
        config = TeamManager.get_team(team_name)
        if not config:
            raise ValueError(f"Team '{team_name}' not found")

        mailbox = MailboxManager(team_name)
        store = TaskStore(team_name)

        total_inbox = 0
        leader_name = ""
        for member in config.members:
            inbox_name = f"{member.user}_{member.name}" if member.user else member.name
            total_inbox += mailbox.peek_count(inbox_name)
            if not leader_name and member.agent_id == config.lead_agent_id:
                leader_name = member.name

        online_map = agents_online(team_name, [m.name for m in config.members])
        members_online = sum(1 for v in online_map.values() if v)

        tasks_total = len(store.list_tasks())
        return {
            "name": config.name,
            "description": config.description,
            "leader": leader_name,
            "members": len(config.members),
            "membersOnline": members_online,
            "tasks": tasks_total,
            "pendingMessages": total_inbox,
        }
    _GITHUB_CACHE_TTL = 60  # seconds

    def __init__(self) -> None:
        self._github_cache: dict[str, tuple[float, Any]] = {}  # key -> (expires_at, data)
        self._lock = threading.Lock()

    def _get_cached_github(self, cache_key: str) -> Any | None:
        with self._lock:
            entry = self._github_cache.get(cache_key)
            if entry and entry[0] > _time.monotonic():
                return entry[1]
            return None

    def _set_cached_github(self, cache_key: str, data: Any) -> None:
        with self._lock:
            self._github_cache[cache_key] = (_time.monotonic() + self._GITHUB_CACHE_TTL, data)

    def collect_team(self, team_name: str) -> dict:
        """Collect full board data for a single team.

        Returns a dict with keys: team, members, tasks, taskSummary.
        Raises ValueError if the team does not exist.
        """
        config = TeamManager.get_team(team_name)
        if not config:
            raise ValueError(f"Team '{team_name}' not found")

        mailbox = MailboxManager(team_name)
        store = TaskStore(team_name)
        member_aliases = self._member_alias_index(config)
        online_map = agents_online(team_name, [m.name for m in config.members])

        # Members with inbox counts
        members = []
        for m in config.members:
            inbox_name = f"{m.user}_{m.name}" if m.user else m.name
            entry = {
                "name": m.name,
                "agentId": m.agent_id,
                "agentType": m.agent_type,
                "joinedAt": m.joined_at,
                "memberKey": inbox_name,
                "inboxName": inbox_name,
                "inboxCount": mailbox.peek_count(inbox_name),
                "isRunning": online_map.get(m.name, False),
            }
            if m.user:
                entry["user"] = m.user
            members.append(entry)

        # Tasks grouped by status
        all_tasks = store.list_tasks()
        grouped: dict[str, list[dict]] = {
            "pending": [],
            "in_progress": [],
            "completed": [],
            "blocked": [],
            "awaiting_approval": [],
            "verified": [],
        }
        for t in all_tasks:
            td = t.model_dump(mode="json", by_alias=True, exclude_none=True)
            grouped[t.status.value].append(td)

        summary = {
            s: len(grouped[s]) for s in grouped
        }
        summary["total"] = len(all_tasks)

        # Find leader name
        leader_name = ""
        for m in config.members:
            if m.agent_id == config.lead_agent_id:
                leader_name = m.name
                break

        # Collect message history from event log (persistent, never consumed)
        all_messages = []
        try:
            events = mailbox.get_event_log(limit=200)
            for msg in events:
                payload = msg.model_dump(mode="json", by_alias=True, exclude_none=True)
                from_info = member_aliases.get(payload.get("from") or "")
                to_info = member_aliases.get(payload.get("to") or "")
                if from_info:
                    payload["fromKey"] = from_info["memberKey"]
                    payload["fromLabel"] = from_info["name"]
                elif payload.get("from"):
                    payload["fromKey"] = payload["from"]
                    payload["fromLabel"] = payload["from"]
                if to_info:
                    payload["toKey"] = to_info["memberKey"]
                    payload["toLabel"] = to_info["name"]
                elif payload.get("to"):
                    payload["toKey"] = payload["to"]
                    payload["toLabel"] = payload["to"]
                payload["isBroadcast"] = payload.get("type") == "broadcast" or not payload.get("to")
                all_messages.append(payload)
        except Exception:
            logger.debug("Failed to collect message history from event log", exc_info=True)

        # Cost summary
        cost_data = {}
        try:
            from clawteam.team.costs import CostStore
            cost_store = CostStore(team_name)
            cost_summary = cost_store.summary()
            cost_data = {
                "totalCostCents": cost_summary.total_cost_cents,
                "totalInputTokens": cost_summary.total_input_tokens,
                "totalOutputTokens": cost_summary.total_output_tokens,
                "eventCount": cost_summary.event_count,
                "byAgent": cost_summary.by_agent,
            }
        except Exception:
            logger.debug("Failed to collect cost summary", exc_info=True)

        # Conflict/overlap data
        conflict_data = {}
        try:
            from clawteam.workspace.conflicts import detect_overlaps
            overlaps = detect_overlaps(team_name)
            conflict_data = {
                "overlaps": [
                    {"file": o["file"], "agents": o["agents"], "severity": o["severity"]}
                    for o in overlaps
                ],
                "totalOverlaps": len(overlaps),
                "highSeverity": sum(1 for o in overlaps if o["severity"] == "high"),
                "mediumSeverity": sum(1 for o in overlaps if o["severity"] == "medium"),
            }
        except Exception:
            pass

        return {
            "team": {
                "name": config.name,
                "description": config.description,
                "leadAgentId": config.lead_agent_id,
                "leaderName": leader_name,
                "createdAt": config.created_at,
                "budgetCents": config.budget_cents,
                "membersOnline": sum(1 for v in online_map.values() if v),
            },
            "members": members,
            "tasks": grouped,
            "taskSummary": summary,
            "messages": all_messages,
            "cost": cost_data,
            "conflicts": conflict_data,
            "devteam": self._collect_devteam(team_name),
        }

    def collect_overview(self) -> list[dict]:
        """Collect lightweight summary for all teams.

        Only reads each team's config.json — no heavy devteam/project/
        event loading.  This makes the initial team selector instant.
        """
        teams_meta = TeamManager.discover_teams()
        return [
            {
                "name": meta["name"],
                "description": meta.get("description", ""),
                "leader": meta.get("leadAgentId", ""),
                "members": meta.get("memberCount", 0),
            }
            for meta in teams_meta
        ]

    def _collect_devteam(self, team_name: str) -> dict | None:
        try:
            from clawteam.devteam.bootstrap import load_runtime_blueprint, load_runtime_state
            from clawteam.devteam.controlplane import ControlPlaneStore
            from clawteam.devteam.eventstore import DevEventStore
            from clawteam.devteam.meetings import MeetingManager
            from clawteam.devteam.projects import ProjectManager
            from clawteam.devteam.sessions import WorkerSessionStore
            from clawteam.devteam.workflow import SprintWorkflow
        except Exception:
            logger.debug("Failed to import devteam modules", exc_info=True)
            return None

        try:
            blueprint = load_runtime_blueprint(team_name)
            state = load_runtime_state(team_name)
        except FileNotFoundError:
            return None

        default_workflow = SprintWorkflow(blueprint.blueprint.workflow_stages or None)
        control = ControlPlaneStore(team_name)
        events = DevEventStore(team_name)
        meetings = MeetingManager(team_name)
        session_store = WorkerSessionStore(team_name)
        project_manager = ProjectManager(team_name)
        projects = project_manager.list_projects()
        all_sessions = session_store.refresh_sessions()
        all_meetings = meetings.list_meetings()
        company = events.get_company_state()

        # Pre-load and index data to avoid N+1 queries inside the project loop
        all_activities = control.list_activities(limit=200)
        activities_by_project: dict[str, list] = defaultdict(list)
        for a in all_activities:
            if hasattr(a, "project_id") and a.project_id:
                activities_by_project[a.project_id].append(a)

        sessions_by_project: dict[str, list] = defaultdict(list)
        for s in all_sessions:
            if hasattr(s, "project_id") and s.project_id:
                sessions_by_project[s.project_id].append(s)

        meetings_by_project: dict[str, list] = defaultdict(list)
        for m in all_meetings:
            if hasattr(m, "project_id") and m.project_id:
                meetings_by_project[m.project_id].append(m)

        all_commands = events.list_commands(limit=50 * max(len(projects), 1))
        commands_by_project: dict[str, list] = defaultdict(list)
        for c in all_commands:
            pid = getattr(c, "project_id", None)
            if pid:
                commands_by_project[pid].append(c)

        all_artifacts = events.list_artifacts(limit=50 * max(len(projects), 1))
        artifacts_by_project: dict[str, list] = defaultdict(list)
        for ar in all_artifacts:
            pid = getattr(ar, "project_id", None)
            if pid:
                artifacts_by_project[pid].append(ar)

        project_payload = []
        stage_summary: dict[str, int] = {}
        for project in projects:
            workflow = SprintWorkflow.for_project_type(project.project_type.value) if hasattr(project, "project_type") else default_workflow
            cfg = workflow.stage_config(project.stage)
            dump = project.model_dump(mode="json")
            dump["stageOwner"] = workflow.stage_owner(project.stage)
            dump["effectiveOwner"] = project.metadata.get("manual_owner") or dump["stageOwner"]
            dump["stageParticipants"] = workflow.stage_participants(project.stage)
            dump["requiresHumanApproval"] = cfg.requires_human_approval
            dump["spawnAgent"] = cfg.spawn_agent
            dump["waitingForHuman"] = cfg.requires_human_approval and project.status.value == "open"
            dump["version"] = int(project.metadata.get("version", 0))
            dump["ledger"] = (project.metadata.get("autonomy") or {}).get("ledger", [])
            dump["sessions"] = [
                session.model_dump(mode="json")
                for session in sessions_by_project.get(project.project_id, [])
            ]
            dump["meetings"] = [
                meeting.model_dump(mode="json")
                for meeting in meetings_by_project.get(project.project_id, [])
            ]
            dump["projectActivities"] = [
                activity.model_dump(mode="json")
                for activity in activities_by_project.get(project.project_id, [])
            ]
            dump["commands"] = [
                command.model_dump(mode="json")
                for command in commands_by_project.get(project.project_id, [])
            ]
            dump["artifacts"] = [
                artifact.model_dump(mode="json")
                for artifact in artifacts_by_project.get(project.project_id, [])
            ]
            # GitHub PR info (cached in project metadata by runtime)
            gh_pr = project.metadata.get("_github_pr")
            if gh_pr:
                dump["githubPR"] = gh_pr
            project_payload.append(dump)
            stage_summary[project.stage.value] = stage_summary.get(project.stage.value, 0) + 1

        activities = [
            activity.model_dump(mode="json")
            for activity in control.list_activities(limit=120)
        ]
        event_timeline = events.list_events(limit=200)
        commands = [command.model_dump(mode="json") for command in events.list_commands(limit=120)]
        dynamic_jobs = [
            {
                **job.model_dump(mode="json"),
                "source": "dynamic",
            }
            for job in control.list_jobs(include_disabled=True)
        ]
        blueprint_jobs = [
            {
                "key": schedule.key,
                "title": schedule.description or schedule.key,
                "cadence": schedule.cadence,
                "owner": schedule.owner,
                "instruction": schedule.description,
                "channels": schedule.channels,
                "enabled": True,
                "createdBy": "template",
                "createdAt": blueprint.created_at,
                "lastRunAt": state.last_protocol_runs.get(schedule.key, ""),
                "source": "blueprint",
            }
            for schedule in blueprint.blueprint.schedules
        ]

        workspaces = []
        ws_mgr = get_workspace_manager()
        if ws_mgr is not None:
            try:
                result.append(self.collect_team_summary(name))
            except Exception:
                result.append({
                    "name": name,
                    "description": meta.get("description", ""),
                    "leader": "",
                    "members": meta.get("memberCount", 0),
                    "membersOnline": 0,
                    "tasks": 0,
                    "pendingMessages": 0,
                })
                workspaces = [
                    ws.model_dump(mode="json") for ws in ws_mgr.list_workspaces(team_name)
                ]
            except Exception:
                logger.debug("Failed to list workspaces", exc_info=True)
                workspaces = []

        opencode = dict(state.metadata.get("opencode", {}))
        if not opencode or not opencode.get("integrations"):
            # Runtime hasn't populated state yet — discover directly
            try:
                from clawteam.devteam.integrations import (
                    discover_opencode_profile,
                    load_opencode_env,
                )
                env_report = load_opencode_env()
                profile = discover_opencode_profile()
                opencode = {**profile, **env_report}
            except Exception:
                logger.debug("Failed to discover opencode profile", exc_info=True)
                opencode = {"integrations": [], "rules": [], "skillsCount": 0}

        session_payload = []
        for session in all_sessions:
            item = session.model_dump(mode="json")
            item["liveLog"] = session_store.capture_live_log(session, limit_lines=30)
            session_payload.append(item)

        meeting_payload = []
        for meeting in all_meetings:
            item = meeting.model_dump(mode="json")
            item["messages"] = [
                message.model_dump(mode="json")
                for message in meetings.list_messages(meeting.meeting_id)
            ]
            meeting_payload.append(item)

        # Build per-agent workspace snapshot from active sessions
        agent_snapshots: dict[str, dict] = {}
        for session in all_sessions:
            agent_type = session.agent_type or ""
            if not agent_type:
                continue
            snap = session.snapshot or {}
            if not snap:
                continue
            # Keep the freshest snapshot per agent type
            existing = agent_snapshots.get(agent_type)
            if existing is None or (session.last_heartbeat_at or "") > (existing.get("_hb", "")):
                agent_snapshots[agent_type] = {
                    **snap,
                    "_hb": session.last_heartbeat_at or "",
                    "sessionId": session.session_id,
                    "status": session.status.value if hasattr(session.status, "value") else str(session.status),
                    "workspace": session.workspace_path or "",
                }

        # Enrich personas with snapshot + active session info
        personas_payload = []
        for persona in blueprint.blueprint.personas:
            pd = persona.model_dump(mode="json")
            snap = agent_snapshots.get(persona.agent)
            if snap:
                clean = {k: v for k, v in snap.items() if k != "_hb"}
                pd["workspaceSnapshot"] = clean
            # Count active sessions for this agent
            agent_active = [s for s in all_sessions if s.agent_type == persona.agent and s.status.value in ("running", "starting")]
            pd["activeSessions"] = len(agent_active)
            personas_payload.append(pd)

        return {
            "template": blueprint.template,
            "goal": blueprint.goal,
            "mode": state.mode,
            "lastHeartbeatAt": state.last_heartbeat_at,
            "company": company.model_dump(mode="json"),
            "personas": personas_payload,
            "channels": [channel.model_dump(mode="json") for channel in blueprint.blueprint.channels],
            "projects": sorted(
                project_payload,
                key=lambda item: item.get("metadata", {}).get("last_activity_ts", ""),
                reverse=True,
            ),
            "stageSummary": stage_summary,
            "activities": activities,
            "eventTimeline": event_timeline,
            "commands": commands,
            "jobs": dynamic_jobs + blueprint_jobs,
            "workspaces": workspaces,
            "sessions": session_payload,
            "meetings": meeting_payload,
            "artifacts": [artifact.model_dump(mode="json") for artifact in events.list_artifacts(limit=100)],
            "opencode": opencode,
            "github": self._collect_github(projects),
            "runtimeErrors": list(state.metadata.get("runtime_errors", [])),
        }

    def _collect_github(self, projects) -> dict | None:
        """Collect GitHub integration data (PRs, Actions) for the board.

        Results are cached for ``_GITHUB_CACHE_TTL`` seconds (default 60)
        to avoid spawning ``gh`` subprocesses on every SSE tick.
        """
        cache_key = "github_actions"
        cached = self._get_cached_github(cache_key)
        if cached is not None:
            return cached

        try:
            from clawteam.devteam.github import is_gh_available, gh_auth_user, list_runs
        except Exception:
            logger.debug("Failed to import GitHub modules", exc_info=True)
            return None

        if not is_gh_available():
            return None

        user = gh_auth_user()

        # Gather repos from projects
        repos: set[str] = set()
        prs: list[dict] = []
        for p in projects:
            gh_pr = p.metadata.get("_github_pr")
            if gh_pr:
                repo = gh_pr.get("repo", "")
                if repo:
                    repos.add(repo)
                prs.append(gh_pr)

        # Fetch recent Actions runs for each repo
        actions_runs: list[dict] = []
        for repo in list(repos)[:3]:  # Limit to 3 repos to avoid slowdown
            try:
                runs = list_runs(repo, limit=5)
                for r in runs:
                    actions_runs.append({
                        "repo": repo,
                        "id": r.id,
                        "name": r.name,
                        "status": r.status,
                        "conclusion": r.conclusion,
                        "branch": r.head_branch,
                        "event": r.event,
                        "url": r.url,
                        "createdAt": r.created_at,
                    })
            except Exception:
                logger.debug("Failed to fetch GitHub Actions runs for repo %s", repo, exc_info=True)

        result = {
            "available": True,
            "user": user,
            "repos": sorted(repos),
            "prs": prs,
            "actionsRuns": actions_runs,
        }
        self._set_cached_github(cache_key, result)
        return result
