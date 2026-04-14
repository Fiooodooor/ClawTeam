from __future__ import annotations

import io
from pathlib import Path

import pytest

from clawteam.board.collector import BoardCollector
from clawteam.board.server import BoardHandler, _fetch_proxy_content, _normalize_proxy_target
from clawteam.team.mailbox import MailboxManager
from clawteam.team.manager import TeamManager


def test_collect_overview_does_not_call_collect_team(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))
    TeamManager.create_team(
        name="demo",
        leader_name="leader",
        leader_id="leader001",
        description="demo team",
    )

    def fail_collect_team(self, team_name: str):
        raise AssertionError("collect_team should not be called for overview")

    monkeypatch.setattr(BoardCollector, "collect_team", fail_collect_team)

    teams = BoardCollector().collect_overview()

    assert teams == [
        {
            "name": "demo",
            "description": "demo team",
            "leader": "leader",
            "members": 1,
            "tasks": 0,
            "pendingMessages": 0,
        }
    ]


def test_collect_overview_sums_inbox_counts_for_all_members(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))
    TeamManager.create_team(
        name="demo",
        leader_name="leader",
        leader_id="leader001",
        description="demo team",
    )
    TeamManager.add_member("demo", "worker", "worker001")
    MailboxManager("demo").send(from_agent="leader", to="worker", content="hello")

    def fail_collect_team(self, team_name: str):
        raise AssertionError("collect_team should not be called for overview")

    monkeypatch.setattr(BoardCollector, "collect_team", fail_collect_team)

    teams = BoardCollector().collect_overview()

    assert teams == [
        {
            "name": "demo",
            "description": "demo team",
            "leader": "leader",
            "members": 2,
            "tasks": 0,
            "pendingMessages": 1,
        }
    ]


def test_team_snapshot_cache_reuses_value_within_ttl():
    from clawteam.board.server import TeamSnapshotCache

    calls = {"count": 0}

    def loader():
        calls["count"] += 1
        return {"version": calls["count"]}

    cache = TeamSnapshotCache(ttl_seconds=60.0)

    first = cache.get("demo", loader)
    second = cache.get("demo", loader)

    assert first == {"version": 1}
    assert second == {"version": 1}
    assert calls["count"] == 1


def test_team_snapshot_cache_expires_after_ttl(monkeypatch):
    from clawteam.board.server import TeamSnapshotCache

    now = {"value": 100.0}
    monkeypatch.setattr("clawteam.board.server.time.monotonic", lambda: now["value"])

    calls = {"count": 0}

    def loader():
        calls["count"] += 1
        return {"version": calls["count"]}

    cache = TeamSnapshotCache(ttl_seconds=5.0)

    first = cache.get("demo", loader)
    now["value"] += 10.0
    second = cache.get("demo", loader)

    assert first == {"version": 1}
    assert second == {"version": 2}
    assert calls["count"] == 2


def test_collect_team_preserves_conflicts_field(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))
    TeamManager.create_team(
        name="demo",
        leader_name="leader",
        leader_id="leader001",
        description="demo team",
    )

    data = BoardCollector().collect_team("demo")

    assert "conflicts" in data


def test_collect_team_exposes_member_inbox_identity(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))
    TeamManager.create_team(
        name="demo",
        leader_name="leader",
        leader_id="leader001",
        description="demo team",
    )
    TeamManager.add_member("demo", "worker", "worker001", user="alice")

    data = BoardCollector().collect_team("demo")

    worker = next(member for member in data["members"] if member["name"] == "worker")
    assert worker["memberKey"] == "alice_worker"
    assert worker["inboxName"] == "alice_worker"


def test_collect_team_normalizes_message_participants(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))
    TeamManager.create_team(
        name="demo",
        leader_name="leader",
        leader_id="leader001",
        description="demo team",
    )
    TeamManager.add_member("demo", "worker", "worker001", user="alice")
    mailbox = MailboxManager("demo")
    mailbox.send(from_agent="leader", to="worker", content="hello")
    mailbox.broadcast(from_agent="leader", content="broadcast")

    data = BoardCollector().collect_team("demo")

    direct = next(msg for msg in data["messages"] if msg.get("content") == "hello")
    assert direct["fromKey"] == "leader"
    assert direct["fromLabel"] == "leader"
    assert direct["toKey"] == "alice_worker"
    assert direct["toLabel"] == "worker"
    assert direct["isBroadcast"] is False

    broadcast = next(
        msg
        for msg in data["messages"]
        if msg.get("content") == "broadcast" and msg.get("to") == "alice_worker"
    )
    assert broadcast["fromKey"] == "leader"
    assert broadcast["toKey"] == "alice_worker"
    assert broadcast["toLabel"] == "worker"
    assert broadcast["isBroadcast"] is True


def test_collect_overview_preserves_broken_team_fallback(monkeypatch):
    def fake_discover():
        return [
            {
                "name": "good",
                "description": "good team",
                "memberCount": 1,
            },
            {
                "name": "broken",
                "description": "broken team",
                "memberCount": 7,
            },
        ]

    def fake_summary(self, team_name: str):
        if team_name == "broken":
            raise ValueError("boom")
        return {
            "name": "good",
            "description": "good team",
            "leader": "lead",
            "members": 1,
            "tasks": 3,
            "pendingMessages": 2,
        }

    monkeypatch.setattr(TeamManager, "discover_teams", staticmethod(fake_discover))
    monkeypatch.setattr(BoardCollector, "collect_team_summary", fake_summary)

    overview = BoardCollector().collect_overview()

    assert overview == [
        {
            "name": "good",
            "description": "good team",
            "leader": "lead",
            "members": 1,
            "tasks": 3,
            "pendingMessages": 2,
        },
        {
            "name": "broken",
            "description": "broken team",
            "leader": "",
            "members": 7,
            "tasks": 0,
            "pendingMessages": 0,
        },
    ]


def test_serve_team_reads_fresh_snapshot_without_cache(monkeypatch):
    calls = {"count": 0}
    served = {}

    class FakeCache:
        def get(self, team_name, loader):
            raise AssertionError("team cache should not be used for /api/team")

    handler = object.__new__(BoardHandler)
    handler.collector = type(
        "Collector",
        (),
        {
            "collect_team": staticmethod(
                lambda team_name: calls.__setitem__("count", calls["count"] + 1)
                or {"team": {"name": team_name}}
            )
        },
    )()
    handler.team_cache = FakeCache()
    handler._serve_json = lambda data: served.setdefault("data", data)

    handler._serve_team("demo")

    assert calls["count"] == 1
    assert served["data"] == {"team": {"name": "demo"}}


def test_serve_sse_uses_shared_team_snapshot_cache(monkeypatch):
    calls = {"count": 0}

    class FakeCache:
        def get(self, team_name, loader):
            calls["count"] += 1
            return loader()

    handler = object.__new__(BoardHandler)
    handler.collector = type(
        "Collector",
        (),
        {"collect_team": staticmethod(lambda team_name: {"team": {"name": team_name}})},
    )()
    handler.team_cache = FakeCache()
    handler.interval = 0.0
    handler.wfile = io.BytesIO()
    handler.send_response = lambda code: None
    handler.send_header = lambda name, value: None
    handler.end_headers = lambda: None
    monkeypatch.setattr(
        handler.wfile,
        "flush",
        lambda: (_ for _ in ()).throw(BrokenPipeError()),
    )

    handler._serve_sse("demo")

    assert calls["count"] == 1


def test_proxy_rejects_non_github_targets():
    with pytest.raises(ValueError, match="GitHub-hosted"):
        _normalize_proxy_target("https://example.com/secret")


def test_proxy_rejects_localhost_targets():
    with pytest.raises(ValueError, match="not allowed"):
        _normalize_proxy_target("https://127.0.0.1/admin")


def test_proxy_fetches_allowed_github_content(monkeypatch):
    seen = {}

    class FakeResponse:
        def __init__(self, url: str, payload: bytes):
            self._url = url
            self._payload = payload

        def geturl(self):
            return self._url

        def read(self):
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeOpener:
        def open(self, req, timeout=10):
            seen["url"] = req.full_url
            return FakeResponse(req.full_url, b"ok")

    monkeypatch.setattr("clawteam.board.server.urllib.request.build_opener", lambda *_: FakeOpener())

    assert _fetch_proxy_content("https://raw.githubusercontent.com/org/repo/main/README.md") == b"ok"
    assert seen["url"] == "https://raw.githubusercontent.com/org/repo/main/README.md"


def test_board_ui_escapes_attacker_controlled_fields():
    html = Path("clawteam/board/static/index.html").read_text(encoding="utf-8")

    assert "escapeHtml(m.name)" in html
    assert "escapeHtml(m.agentType || 'Agent')" in html
    assert "escapeHtml(m.fromLabel || m.from || 'SYS')" in html
    assert "escapeHtml(m.toLabel || m.to || 'ALL')" in html
    assert "escapeHtml(t.owner || 'Unassigned')" in html
    assert "t.blockedBy.map(v => escapeHtml(v)).join(', ')" in html
    assert "option.textContent =" in html


def test_patch_task_updates_status(monkeypatch, tmp_path: Path):
    import json as _json
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))
    from clawteam.team.models import TaskStatus
    TeamManager.create_team(
        name="ptest", leader_name="leader", leader_id="l001", description="test",
    )
    from clawteam.team.tasks import TaskStore
    store = TaskStore("ptest")
    task = store.create(subject="Drag me")

    from clawteam.board.server import BoardHandler
    from unittest.mock import MagicMock
    handler = MagicMock(spec=BoardHandler)
    handler.path = f"/api/team/ptest/task/{task.id}"

    body = _json.dumps({"status": "in_progress"}).encode()
    handler.headers = {"Content-Length": str(len(body))}
    handler.rfile = io.BytesIO(body)

    responses = []
    def mock_serve_json(data):
        responses.append(data)
    handler._serve_json = mock_serve_json
    handler.send_error = MagicMock()

    BoardHandler.do_PATCH(handler)

    assert len(responses) == 1
    assert responses[0]["status"] == "ok"
    assert responses[0]["task_id"] == task.id

    updated = store.get(task.id)
    assert updated.status == TaskStatus.in_progress


def test_collect_team_groups_all_six_statuses(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))
    from clawteam.team.models import TaskStatus
    TeamManager.create_team(
        name="six", leader_name="leader", leader_id="l001", description="test",
    )
    from clawteam.team.tasks import TaskStore
    store = TaskStore("six")
    store.create(subject="t1")
    store.create(subject="t2")
    t3 = store.create(subject="t3")
    store.update(t3.id, status=TaskStatus.awaiting_approval, force=True)
    t4 = store.create(subject="t4")
    store.update(t4.id, status=TaskStatus.completed, force=True)
    t5 = store.create(subject="t5")
    store.update(t5.id, status=TaskStatus.verified, force=True)

    data = BoardCollector().collect_team("six")
    assert "awaiting_approval" in data["tasks"]
    assert "verified" in data["tasks"]
    assert len(data["tasks"]["awaiting_approval"]) == 1
    assert len(data["tasks"]["verified"]) == 1
    assert "awaiting_approval" in data["taskSummary"]
    assert "verified" in data["taskSummary"]
