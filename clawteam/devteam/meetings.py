"""Meeting lifecycle and lightweight live meeting orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from clawteam.devteam.eventstore import DevEventStore
from clawteam.devteam.models import DevActivityKind, DevMeeting, DevMeetingMessage, DevMeetingStatus


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MeetingManager:
    """Stores meetings and produces lightweight live discussion rounds."""

    def __init__(self, team_name: str):
        self.team_name = team_name
        self.events = DevEventStore(team_name)

    def start_meeting(
        self,
        *,
        title: str,
        agenda: str,
        participants: list[str],
        project_id: str = "",
        created_by: str = "CEO",
    ) -> DevMeeting:
        meeting = DevMeeting(
            team_name=self.team_name,
            project_id=project_id,
            title=title,
            agenda=agenda,
            participants=participants,
            created_by=created_by,
            status=DevMeetingStatus.live,
            started_at=_now_iso(),
            metadata={"turn_index": 0, "round": 0, "auto_generated": 0},
        )
        self.events.create_meeting(meeting)
        self.events.append_event(
            event_type="meeting.started",
            actor=created_by,
            project_id=project_id,
            meeting_id=meeting.meeting_id,
            occurred_at=meeting.started_at,
            payload=meeting.model_dump(mode="json"),
        )
        self.add_message(
            meeting_id=meeting.meeting_id,
            speaker=created_by,
            speaker_type="human",
            body=f"Meeting opened: {agenda or title}",
        )
        return meeting

    def add_message(
        self,
        *,
        meeting_id: str,
        speaker: str,
        speaker_type: str,
        body: str,
        metadata: dict[str, Any] | None = None,
    ) -> DevMeetingMessage:
        meeting = self.events.get_meeting(meeting_id)
        if meeting is None:
            raise FileNotFoundError(f"Meeting '{meeting_id}' not found")
        if meeting.status == DevMeetingStatus.concluded:
            raise ValueError(f"Meeting '{meeting_id}' is already concluded")
        message = DevMeetingMessage(
            meeting_id=meeting_id,
            team_name=self.team_name,
            project_id=meeting.project_id,
            speaker=speaker,
            speaker_type=speaker_type,
            body=body,
            metadata=metadata or {},
        )
        self.events.add_meeting_message(message)
        self.events.append_event(
            event_type="meeting.message_posted",
            actor=speaker,
            project_id=meeting.project_id,
            meeting_id=meeting_id,
            occurred_at=message.created_at,
            payload=message.model_dump(mode="json"),
        )
        return message

    def conclude_meeting(self, meeting_id: str, *, concluded_by: str = "CEO") -> DevMeeting:
        meeting = self.events.get_meeting(meeting_id)
        if meeting is None:
            raise FileNotFoundError(f"Meeting '{meeting_id}' not found")
        if meeting.status == DevMeetingStatus.concluded:
            return meeting
        meeting.status = DevMeetingStatus.concluded
        meeting.ended_at = _now_iso()
        self.events.save_meeting(meeting)
        self.events.append_event(
            event_type="meeting.concluded",
            actor=concluded_by,
            project_id=meeting.project_id,
            meeting_id=meeting_id,
            occurred_at=meeting.ended_at,
            payload=meeting.model_dump(mode="json"),
        )
        return meeting

    def list_meetings(self, *, project_id: str = "", status: str = "") -> list[DevMeeting]:
        return self.events.list_meetings(project_id=project_id, status=status)

    def list_messages(self, meeting_id: str) -> list[DevMeetingMessage]:
        return self.events.list_meeting_messages(meeting_id)

    def tick_live_meetings(self, personas: dict[str, dict[str, str]]) -> list[DevMeetingMessage]:
        emitted: list[DevMeetingMessage] = []
        for meeting in self.events.list_meetings(status=DevMeetingStatus.live.value, limit=50):
            participants = meeting.participants or ["chief-of-staff"]
            turn_index = int(meeting.metadata.get("turn_index", 0))
            round_index = int(meeting.metadata.get("round", 0))
            auto_generated = int(meeting.metadata.get("auto_generated", 0))
            if auto_generated >= max(3, len(participants)):
                continue
            agent = participants[turn_index % len(participants)]
            persona = personas.get(agent, {})
            speaker = persona.get("display_name") or agent
            role = persona.get("role") or agent
            agenda = meeting.agenda or meeting.title

            # Build conversation history from prior meeting messages
            prior_messages = self.events.list_meeting_messages(meeting.meeting_id)
            history_lines = [
                f"- {msg.speaker} ({msg.speaker_type}): {msg.body}"
                for msg in prior_messages[-8:]
            ]
            history_context = "\n".join(history_lines) if history_lines else "(첫 발언)"

            body = self._generate_meeting_response(
                agent=agent,
                speaker=speaker,
                role=role,
                agenda=agenda,
                round_index=round_index,
                history_context=history_context,
                persona=persona,
            )
            emitted.append(
                self.add_message(
                    meeting_id=meeting.meeting_id,
                    speaker=speaker,
                    speaker_type="agent",
                    body=body,
                    metadata={"auto": True, "agent": agent, "round": round_index + 1},
                )
            )
            meeting.metadata["turn_index"] = turn_index + 1
            meeting.metadata["round"] = (turn_index + 1) // max(len(participants), 1)
            meeting.metadata["auto_generated"] = auto_generated + 1
            self.events.save_meeting(meeting)
        return emitted

    def _generate_meeting_response(
        self,
        *,
        agent: str,
        speaker: str,
        role: str,
        agenda: str,
        round_index: int,
        history_context: str,
        persona: dict[str, str],
    ) -> str:
        """Generate meeting response via LLM, with template fallback."""
        from clawteam.devteam.llm import chat

        system_prompt = (
            f"너는 AI 개발회사의 '{speaker}' ({role})이다.\n\n"
            f"규칙:\n"
            f"- 한국어로 말한다. 반말 업무체로 간결하게. ('~한다', '~하겠다', '~이다')\n"
            f"- 미팅 안건에 대해 너의 역할과 전문성에 맞는 실질적 의견/분석/판단을 제시한다.\n"
            f"- 이전 발언을 그대로 반복하지 않는다. 새로운 관점이나 구체적 제안을 더한다.\n"
            f"- 2~4문장. 길게 쓰지 않는다.\n"
            f"- 마크다운 금지. 이모지 금지. 순수 텍스트만."
        )

        user_prompt = (
            f"미팅 안건: {agenda}\n"
            f"현재 라운드: {round_index + 1}\n\n"
            f"지금까지 대화:\n{history_context}\n\n"
            f"위 맥락에서 '{speaker}' ({role})로서 발언하라."
        )

        llm_text = chat(system=system_prompt, user=user_prompt, max_tokens=300)
        if llm_text:
            return llm_text

        # Fallback template
        return (
            f"[{role}] {agenda} 기준으로 현재 round {round_index + 1} 관점 제안: "
            f"다음 단계에서 필요한 핵심 행동을 정리하겠습니다."
        )


def meeting_activity_payload(meeting: DevMeeting) -> dict[str, Any]:
    return {
        "kind": DevActivityKind.meeting.value,
        "meetingId": meeting.meeting_id,
        "title": meeting.title,
        "agenda": meeting.agenda,
        "status": meeting.status.value,
        "participants": list(meeting.participants),
    }
