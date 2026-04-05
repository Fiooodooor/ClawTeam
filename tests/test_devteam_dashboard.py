from __future__ import annotations

from pathlib import Path
from time import sleep
from types import SimpleNamespace

import pytest

from clawteam.board.collector import BoardCollector
from clawteam.cli.commands import app
from clawteam.devteam.bootstrap import bootstrap_devteam
from clawteam.devteam.control import DevTeamControlService
from clawteam.devteam.models import DevMeetingStatus, DevSessionStatus, DevTeamBlueprint
from clawteam.devteam.runtime import DevTeamOperatingRuntime
from clawteam.devteam.sessions import WorkerSessionStore
from clawteam.devteam.supervisor import CompanySupervisor
from clawteam.team.manager import TeamManager
from clawteam.templates import load_template
from typer.testing import CliRunner


def _bootstrap(team_name: str):
    template = load_template("dev-company")
    blueprint = DevTeamBlueprint.model_validate(template.devteam)
    return bootstrap_devteam(
        template_name="dev-company",
        team_name=team_name,
        goal="Build a custom command center",
        leader=template.leader.name,
        members=[agent.name for agent in template.agents],
        blueprint=blueprint,
    )


def test_devteam_bootstrap_registers_team_members(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    _bootstrap("acme-dev")

    team = TeamManager.get_team("acme-dev")
    assert team is not None
    assert team.members[0].name == "chief-of-staff"
    assert {member.name for member in team.members} >= {
        "chief-of-staff",
        "cto",
        "lead-engineer",
        "qa-lead",
    }


def test_control_service_request_appears_in_board(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    _bootstrap("acme-dev")

    service = DevTeamControlService("acme-dev", workspace_dir=str(tmp_path))
    project = service.submit_request(
        title="Build CEO dashboard",
        description="Custom UI에서 CoS가 일을 triage하고 stage를 감독하게 해줘",
        project_type="feature",
    )

    board = BoardCollector().collect_team("acme-dev")
    assert board["devteam"] is not None
    assert board["devteam"]["projects"][0]["project_id"] == project.project_id
    assert board["devteam"]["activities"][0]["kind"] == "ceo_request"
    assert board["taskSummary"]["total"] >= 1


def test_control_service_jobs_and_notes_are_persisted(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    _bootstrap("acme-dev")

    service = DevTeamControlService("acme-dev", workspace_dir=str(tmp_path))
    project = service.submit_request(
        title="Investigate Datadog alerts",
        description="hourly log review 자동화 필요",
        project_type="spike",
    )
    service.add_job(
        title="hourly datadog sweep",
        cadence="every 1h",
        owner="chief-of-staff",
        instruction="Datadog 에러 로그를 조회해서 요약 보고",
        channels=["dev-ops"],
    )
    service.add_note(
        title="CEO joined the meeting",
        body="이 작업은 일단 운영 리스크 위주로 보고받자.",
        kind="meeting",
        project_id=project.project_id,
        participants=["chief-of-staff", "sre"],
    )

    board = BoardCollector().collect_team("acme-dev")
    kinds = [item["kind"] for item in board["devteam"]["activities"]]
    job_titles = [item["title"] for item in board["devteam"]["jobs"]]

    assert "meeting" in kinds
    assert "hourly datadog sweep" in job_titles


class _DummyEventSource:
    def read_events(self, limit=25, timeout_seconds=0.1):
        return []

    def close(self):
        return None


class _DummySpawnBackend:
    def __init__(self):
        self.calls = []

    def spawn(self, **kwargs):
        self.calls.append(kwargs)
        return "ok"


class _NoSlackClient:
    token = ""


def test_runtime_can_advance_in_ui_only_mode(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    _bootstrap("acme-dev")
    service = DevTeamControlService("acme-dev", workspace_dir=str(tmp_path))
    service.submit_request(
        title="UI-only workflow",
        description="Slack 없이도 autonomy가 대화를 남겨야 한다",
        project_type="feature",
    )

    runtime = DevTeamOperatingRuntime(
        team_name="acme-dev",
        spawn_backend=_DummySpawnBackend(),
        workspace_dir=str(tmp_path),
    )
    try:
        result = runtime.run_once()
    finally:
        runtime.close()

    board = BoardCollector().collect_team("acme-dev")
    kinds = [item["kind"] for item in board["devteam"]["activities"]]

    assert result["mode"] == "ui_only_online"
    assert "agent_message" in kinds


def test_devteam_cli_request_and_activity_commands(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))
    _bootstrap("acme-dev")

    runner = CliRunner()
    request = runner.invoke(
        app,
        [
            "devteam",
            "request",
            "acme-dev",
            "--title",
            "Ship command center",
            "--description",
            "CEO request from CLI",
            "--requested-by",
            "Founder",
        ],
        env={"CLAWTEAM_DATA_DIR": str(tmp_path)},
    )

    assert request.exit_code == 0
    assert "Request submitted" in request.output

    listing = runner.invoke(
        app,
        ["--json", "devteam", "activity-list", "acme-dev"],
        env={"CLAWTEAM_DATA_DIR": str(tmp_path)},
    )

    assert listing.exit_code == 0
    assert "ceo_request" in listing.output
    assert "Ship command center" in listing.output


def test_devteam_cli_job_and_note_commands(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))
    _bootstrap("acme-dev")

    runner = CliRunner()
    add_job = runner.invoke(
        app,
        [
            "devteam",
            "add-job",
            "acme-dev",
            "--title",
            "hourly dd sweep",
            "--cadence",
            "every 1h",
            "--owner",
            "chief-of-staff",
            "--instruction",
            "Review Datadog errors and summarize",
            "--channel",
            "dev-ops",
        ],
        env={"CLAWTEAM_DATA_DIR": str(tmp_path)},
    )
    assert add_job.exit_code == 0
    assert "Recurring job added" in add_job.output

    add_note = runner.invoke(
        app,
        [
            "devteam",
            "add-note",
            "acme-dev",
            "--title",
            "CEO joined meeting",
            "--body",
            "Need a restart-safe audit trail.",
            "--kind",
            "meeting",
            "--participant",
            "chief-of-staff",
            "--participant",
            "cto",
        ],
        env={"CLAWTEAM_DATA_DIR": str(tmp_path)},
    )
    assert add_note.exit_code == 0
    assert "Activity recorded" in add_note.output

    jobs = runner.invoke(
        app,
        ["--json", "devteam", "job-list", "acme-dev"],
        env={"CLAWTEAM_DATA_DIR": str(tmp_path)},
    )
    assert jobs.exit_code == 0
    assert "hourly dd sweep" in jobs.output

    activities = runner.invoke(
        app,
        ["--json", "devteam", "activity-list", "acme-dev"],
        env={"CLAWTEAM_DATA_DIR": str(tmp_path)},
    )
    assert activities.exit_code == 0
    assert "meeting" in activities.output
    assert "CEO joined meeting" in activities.output


def test_operator_commands_meetings_and_artifacts_are_collected(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    _bootstrap("acme-dev")

    service = DevTeamControlService("acme-dev", workspace_dir=str(tmp_path))
    project = service.submit_request(
        title="Interactive command center",
        description="Operator intervention flow를 Phase 1~5까지 검증",
        project_type="feature",
    )
    service.pause_project(project_id=project.project_id, requested_by="Founder")
    service.resume_project(project_id=project.project_id, requested_by="Founder")
    service.reroute_project(project_id=project.project_id, stage="plan", requested_by="Founder")
    service.reassign_project(project_id=project.project_id, owner="cto", requested_by="Founder")
    service.inject_instruction(
        project_id=project.project_id,
        instruction="회의 전에 리스크와 UI scope를 먼저 정리해줘.",
        requested_by="Founder",
    )
    meeting = service.start_meeting(
        title="Phase 5 live meeting",
        agenda="승인/중단/재지시 UX와 audit trail 합의",
        participants=["chief-of-staff", "cto", "lead-engineer"],
        project_id=project.project_id,
        created_by="Founder",
    )
    service.post_meeting_message(
        meeting_id=meeting.meeting_id,
        body="CEO: live interventions must be restart-safe.",
        author="Founder",
    )
    concluded = service.conclude_meeting(meeting_id=meeting.meeting_id, concluded_by="Founder")

    board = BoardCollector().collect_team("acme-dev")
    devteam = board["devteam"]
    project_view = next(item for item in devteam["projects"] if item["project_id"] == project.project_id)
    command_types = [item["command_type"] for item in devteam["commands"]]
    artifact_kinds = [item["kind"] for item in devteam["artifacts"]]

    assert project_view["status"] == "open"
    assert project_view["stage"] == "plan"
    assert project_view["version"] >= 4
    assert "cto" in project_view["assigned_agents"]
    assert project_view["metadata"]["manual_owner"] == "cto"
    assert "project.pause" in command_types
    assert "project.resume" in command_types
    assert "project.reroute_stage" in command_types
    assert "project.reassign_owner" in command_types
    assert "agent.inject_instruction" in command_types
    assert "meeting.start" in command_types
    assert "meeting.inject_message" in command_types
    assert "meeting.end" in command_types
    assert any(item["meeting_id"] == meeting.meeting_id for item in devteam["meetings"])
    assert concluded.status == DevMeetingStatus.concluded
    assert "meeting_transcript" in artifact_kinds
    assert sum(1 for item in devteam["eventTimeline"] if item["eventType"] == "meeting.started" and item["meetingId"] == meeting.meeting_id) == 1
    assert sum(1 for item in devteam["eventTimeline"] if item["eventType"] == "meeting.concluded" and item["meetingId"] == meeting.meeting_id) == 1


def test_concluded_meeting_rejects_new_messages(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    _bootstrap("acme-dev")

    service = DevTeamControlService("acme-dev", workspace_dir=str(tmp_path))
    meeting = service.start_meeting(
        title="Closeable meeting",
        agenda="end-state validation",
        participants=["chief-of-staff", "cto"],
        created_by="Founder",
    )
    service.conclude_meeting(meeting_id=meeting.meeting_id, concluded_by="Founder")

    with pytest.raises(ValueError):
        service.post_meeting_message(
            meeting_id=meeting.meeting_id,
            body="Should be rejected",
            author="Founder",
        )


class _SupervisorRuntime:
    def __init__(self, **_: object):
        self.state = SimpleNamespace(metadata={})

    def run_once(self):
        return {"mode": "ui_only_online"}

    def close(self):
        return None


def test_supervisor_and_worker_sessions_are_visible_on_board(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    _bootstrap("acme-dev")

    service = DevTeamControlService("acme-dev", workspace_dir=str(tmp_path))
    project = service.submit_request(
        title="Session visibility",
        description="worker session / company heartbeat가 board에 보여야 함",
        project_type="feature",
    )
    sessions = WorkerSessionStore("acme-dev")
    session = sessions.start_session(
        agent_name="lead-engineer-proj",
        agent_id="lead-engineer-proj",
        agent_type="lead-engineer",
        project_id=project.project_id,
        stage=project.stage.value,
        workspace_path=str(tmp_path),
        details={"source": "test"},
    )
    sessions.complete(session.session_id, status=DevSessionStatus.completed, exit_code=0)

    supervisor = CompanySupervisor(
        "acme-dev",
        workspace_dir=str(tmp_path),
        runtime_factory=_SupervisorRuntime,
        poll_interval_seconds=0.01,
    )
    supervisor.start()
    sleep(0.05)
    status = supervisor.stop()

    board = BoardCollector().collect_team("acme-dev")
    devteam = board["devteam"]

    assert status.status.value == "stopped"
    assert devteam["company"]["status"] == "stopped"
    assert any(item["eventType"] == "company.started" for item in devteam["eventTimeline"])
    assert any(item["eventType"] == "company.stopped" for item in devteam["eventTimeline"])
    assert any(item["session_id"] == session.session_id for item in devteam["sessions"])
    project_view = next(item for item in devteam["projects"] if item["project_id"] == project.project_id)
    assert any(item["session_id"] == session.session_id for item in project_view["sessions"])
