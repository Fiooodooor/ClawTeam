"""Aggregates team/task/inbox data into plain dicts for rendering."""

from __future__ import annotations

import json

from clawteam.team.mailbox import MailboxManager
from clawteam.team.manager import TeamManager
from clawteam.team.tasks import TaskStore


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

        tasks_total = len(store.list_tasks())
        return {
            "name": config.name,
            "description": config.description,
            "leader": leader_name,
            "members": len(config.members),
            "tasks": tasks_total,
            "pendingMessages": total_inbox,
        }

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
        }
        for t in all_tasks:
            td = json.loads(t.model_dump_json(by_alias=True, exclude_none=True))
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
                payload = json.loads(msg.model_dump_json(by_alias=True, exclude_none=True))
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
            pass

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
            pass

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

        # Spawn/session registry data. This is intentionally best-effort:
        # dashboards should still render if tmux/wsh/process probing fails.
        sessions = []
        registry = {}
        try:
            from clawteam.spawn.registry import get_registry, is_agent_alive
            from clawteam.spawn.sessions import SessionStore

            registry = get_registry(team_name)
            session_store = SessionStore(team_name)
            for agent_name, info in sorted(registry.items()):
                backend = info.get("backend", "")
                target = info.get("tmux_target") or info.get("block_id") or ""
                saved_session = session_store.load(agent_name)
                session_state = saved_session.state if saved_session else {}
                try:
                    alive = is_agent_alive(team_name, agent_name)
                except Exception:
                    alive = None
                sessions.append(
                    {
                        "agentName": agent_name,
                        "backend": backend,
                        "target": target,
                        "tmuxTarget": info.get("tmux_target", ""),
                        "blockId": info.get("block_id", ""),
                        "pid": info.get("pid", 0),
                        "command": info.get("command", []),
                        "spawnedAt": info.get("spawned_at", 0),
                        "alive": alive,
                        "sessionId": saved_session.session_id if saved_session else "",
                        "sessionSavedAt": saved_session.saved_at if saved_session else "",
                        "sessionClient": session_state.get("client", ""),
                        "sessionSource": session_state.get("source", ""),
                        "sessionConfidence": session_state.get("confidence", ""),
                        "sessionCwd": session_state.get("cwd", ""),
                    }
                )
        except Exception:
            registry = {}

        for member in members:
            session_info = registry.get(member["name"])
            if session_info:
                member["session"] = {
                    "backend": session_info.get("backend", ""),
                    "target": session_info.get("tmux_target") or session_info.get("block_id") or "",
                }

        return {
            "team": {
                "name": config.name,
                "description": config.description,
                "leadAgentId": config.lead_agent_id,
                "leaderName": leader_name,
                "createdAt": config.created_at,
                "budgetCents": config.budget_cents,
            },
            "members": members,
            "tasks": grouped,
            "taskSummary": summary,
            "messages": all_messages,
            "sessions": sessions,
            "cost": cost_data,
            "conflicts": conflict_data,
        }

    def collect_overview(self) -> list[dict]:
        """Collect summary data for all teams.

        Returns a list of dicts with keys: name, description, leader,
        members, tasks, pendingMessages.
        """
        teams_meta = TeamManager.discover_teams()
        result = []
        for meta in teams_meta:
            name = meta["name"]
            try:
                result.append(self.collect_team_summary(name))
            except Exception:
                result.append({
                    "name": name,
                    "description": meta.get("description", ""),
                    "leader": "",
                    "members": meta.get("memberCount", 0),
                    "tasks": 0,
                    "pendingMessages": 0,
                })
        return result
