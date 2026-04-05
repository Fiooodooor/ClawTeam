"""Slack manifest and lightweight Web API helpers."""

from __future__ import annotations

import json
import os
import socket
import time
from typing import Any
from urllib import error, request

from clawteam.investment.models import InvestmentRuntimeBlueprint


class SlackApiError(RuntimeError):
    """Raised when a Slack API request fails."""


class SlackSocketModeError(RuntimeError):
    """Raised when the Slack Socket Mode runtime cannot connect."""


def _is_socket_timeout_error(exc: Exception) -> bool:
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return True
    return exc.__class__.__name__ == "WebSocketTimeoutException"


def _is_private_channel(channel: dict[str, Any]) -> bool:
    value = channel.get("is_private", False)
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "" or any(ch in text for ch in [":", "#", "-", "{", "}", "[", "]", "\n"]):
        return json.dumps(text, ensure_ascii=False)
    return text


def to_yaml(data: Any, indent: int = 0) -> str:
    """Render basic dict/list/scalar structures as YAML."""
    prefix = "  " * indent
    if isinstance(data, dict):
        lines: list[str] = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.append(to_yaml(value, indent + 1))
            else:
                lines.append(f"{prefix}{key}: {_yaml_scalar(value)}")
        return "\n".join(lines)
    if isinstance(data, list):
        lines = []
        for item in data:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.append(to_yaml(item, indent + 1))
            else:
                lines.append(f"{prefix}- {_yaml_scalar(item)}")
        return "\n".join(lines)
    return f"{prefix}{_yaml_scalar(data)}"


def build_metadata_schema() -> list[dict[str, Any]]:
    """Return recommended Slack message metadata event definitions."""
    return [
        {"app_id": "*", "event_type": "clawteam_case_opened"},
        {"app_id": "*", "event_type": "clawteam_case_updated"},
        {"app_id": "*", "event_type": "clawteam_escalation"},
        {"app_id": "*", "event_type": "clawteam_execution_preview"},
        {"app_id": "*", "event_type": "clawteam_execution_result"},
    ]


def build_slack_manifest(blueprint: InvestmentRuntimeBlueprint) -> dict[str, Any]:
    """Build a Slack app manifest aligned to the team blueprint."""
    channel_names = [channel.name for channel in blueprint.blueprint.channels]
    return {
        "display_information": {
            "name": f"{blueprint.team_name}-ops",
            "description": blueprint.blueprint.summary or blueprint.goal,
            "background_color": "#0B2A3B",
        },
        "features": {
            "app_home": {"home_tab_enabled": True, "messages_tab_enabled": False},
            "bot_user": {"display_name": blueprint.blueprint.firm_name or blueprint.team_name},
        },
        "oauth_config": {
            "scopes": {
                "bot": [
                    "channels:history",
                    "channels:manage",
                    "channels:read",
                    "chat:write",
                    "chat:write.customize",
                    "files:write",
                    "groups:history",
                    "groups:read",
                    "groups:write",
                    "im:history",
                    "im:write",
                    "metadata.message:read",
                    "metadata.message:write",
                    "reactions:write",
                    "users:read",
                    "users:read.email",
                ]
            }
        },
        "settings": {
            "event_subscriptions": {
                "bot_events": [
                    "app_mention",
                    "message.channels",
                    "message.groups",
                    "message.im",
                    "message_metadata_posted",
                    "message_metadata_updated",
                ],
                "metadata_subscriptions": build_metadata_schema(),
            },
            "interactivity": {"is_enabled": True},
            "socket_mode_enabled": True,
            "org_deploy_enabled": False,
            "token_rotation_enabled": False,
        },
        "metadata": {
            "channel_seed_plan": channel_names,
            "ceo_mode": blueprint.blueprint.ceo_mode,
            "execution_mode": blueprint.blueprint.execution.default_mode.value,
        },
    }


class SlackWebClient:
    """Minimal Slack Web API client using stdlib only."""

    def __init__(self, token: str | None = None, timeout: int = 30):
        self.token = token or os.environ.get("SLACK_BOT_TOKEN", "")
        self.timeout = timeout
        self._channel_cache: dict[str, dict[str, Any]] = {}
        self._channel_cache_expires_at = 0.0

    def _request(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.token:
            raise SlackApiError("SLACK_BOT_TOKEN is not configured")
        req = request.Request(
            f"https://slack.com/api/{method}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:  # pragma: no cover - network path
            detail = exc.read().decode("utf-8", errors="ignore")
            raise SlackApiError(f"Slack API HTTP error: {exc.code} {detail}") from exc
        except error.URLError as exc:  # pragma: no cover - network path
            raise SlackApiError(f"Slack API connection error: {exc}") from exc
        if not body.get("ok"):
            raise SlackApiError(body.get("error", "unknown_error"))
        return body

    def api_call(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request(method, payload or {})

    def post_message(
        self,
        channel: str,
        text: str,
        metadata: dict[str, Any] | None = None,
        thread_ts: str = "",
        username: str = "",
        icon_emoji: str = "",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"channel": channel, "text": text}
        if metadata:
            payload["metadata"] = metadata
        if thread_ts:
            payload["thread_ts"] = thread_ts
        if username:
            payload["username"] = username
        if icon_emoji:
            payload["icon_emoji"] = icon_emoji
        return self._request("chat.postMessage", payload)

    def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"channel": channel, "ts": ts, "text": text}
        if metadata:
            payload["metadata"] = metadata
        return self._request("chat.update", payload)

    def add_reaction(self, channel: str, timestamp: str, name: str) -> dict[str, Any]:
        try:
            return self._request(
                "reactions.add",
                {"channel": channel, "timestamp": timestamp, "name": name},
            )
        except SlackApiError as exc:
            if str(exc) == "already_reacted":
                return {"ok": True, "already_reacted": True}
            raise

    def list_channels(self, types: str = "public_channel,private_channel") -> list[dict[str, Any]]:
        cache_key = types
        now = time.time()
        cached = self._channel_cache.get(cache_key)
        if cached and now < self._channel_cache_expires_at:
            return [dict(channel) for channel in cached.get("channels", [])]
        channels: list[dict[str, Any]] = []
        cursor = ""
        while True:
            payload: dict[str, Any] = {"limit": 100, "types": types}
            if cursor:
                payload["cursor"] = cursor
            body = self._request("conversations.list", payload)
            channels.extend(body.get("channels", []))
            cursor = body.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                self._channel_cache[cache_key] = {
                    "channels": [dict(channel) for channel in channels]
                }
                self._channel_cache_expires_at = now + 15
                return channels

    def get_channel(self, channel_id: str) -> dict[str, Any]:
        return self._request("conversations.info", {"channel": channel_id}).get("channel", {})

    def ensure_channel(self, channel_name: str, private: bool = False) -> dict[str, Any]:
        normalized = channel_name.lstrip("#")
        for channel in self.list_channels():
            if channel.get("name") == normalized:
                if _is_private_channel(channel) != private:
                    visibility = "private" if _is_private_channel(channel) else "public"
                    required = "private" if private else "public"
                    raise SlackApiError(
                        f"channel '#{normalized}' already exists as {visibility}; expected {required}"
                    )
                channel_id = str(channel.get("id", ""))
                if channel_id:
                    self.ensure_bot_membership(channel_id)
                return channel
        method = "conversations.create"
        try:
            created = self._request(method, {"name": normalized, "is_private": private}).get(
                "channel", {}
            )
        except SlackApiError as exc:
            if private and str(exc) == "name_taken":
                raise SlackApiError(
                    f"private channel '#{normalized}' already exists but is not visible to the bot; invite the app to that channel and rerun"
                ) from exc
            raise
        channel_id = str(created.get("id", ""))
        if channel_id:
            self.ensure_bot_membership(channel_id)
        self._channel_cache_expires_at = 0.0
        return created

    def ensure_bot_membership(self, channel: str) -> None:
        try:
            self._request("conversations.join", {"channel": channel})
        except SlackApiError as exc:
            if str(exc) not in {"already_in_channel", "method_not_supported_for_channel_type"}:
                raise


class SlackSocketModeEventSource:
    """Minimal Socket Mode event reader with ack handling."""

    def __init__(
        self,
        web_client: SlackWebClient | None = None,
        app_token: str | None = None,
        socket_factory=None,
    ):
        self.web_client = web_client or SlackWebClient(token=os.environ.get("SLACK_BOT_TOKEN", ""))
        self.app_token = app_token or os.environ.get("SLACK_APP_TOKEN", "")
        self.socket_factory = socket_factory
        self._socket = None

    def read_events(self, limit: int = 10, timeout_seconds: float = 1.0) -> list[dict[str, Any]]:
        ws = self._connect(read_timeout_seconds=timeout_seconds)
        if hasattr(ws, "settimeout"):
            ws.settimeout(timeout_seconds)
        events: list[dict[str, Any]] = []
        while len(events) < limit:
            try:
                raw = ws.recv()
            except Exception as exc:
                if _is_socket_timeout_error(exc):
                    break
                self.close()
                raise SlackSocketModeError(f"Socket Mode receive failed: {exc}") from exc
            if not raw:
                self.close()
                break
            try:
                message = json.loads(raw)
            except json.JSONDecodeError as exc:
                self.close()
                raise SlackSocketModeError("Socket Mode returned invalid JSON") from exc
            envelope_id = message.get("envelope_id")
            payload = message.get("payload")
            if payload:
                events.append(self._normalize_event_payload(payload, envelope_id=envelope_id))
            if message.get("type") == "disconnect":
                self.close()
                break
        return events

    def ack(self, envelope_id: str) -> None:
        if not envelope_id or self._socket is None:
            return
        self._socket.send(json.dumps({"envelope_id": envelope_id}))

    def close(self) -> None:
        if self._socket is None:
            return
        try:
            self._socket.close()
        finally:
            self._socket = None

    def _connect(self, read_timeout_seconds: float):
        if self._socket is not None:
            return self._socket
        if not self.app_token:
            raise SlackSocketModeError("SLACK_APP_TOKEN is not configured")
        url = self._open_socket_url()
        factory = self.socket_factory or _default_socket_factory
        self._socket = factory(url, self._connect_timeout_seconds(read_timeout_seconds))
        return self._socket

    def _connect_timeout_seconds(self, read_timeout_seconds: float) -> float:
        raw = os.environ.get("CLAWTEAM_SOCKET_CONNECT_TIMEOUT_SECONDS", "10").strip()
        try:
            configured = float(raw) if raw else 10.0
        except ValueError:
            configured = 10.0
        return max(read_timeout_seconds, configured)

    def _open_socket_url(self) -> str:
        req = request.Request(
            "https://slack.com/api/apps.connections.open",
            data=json.dumps({}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.app_token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.web_client.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:  # pragma: no cover - network path
            detail = exc.read().decode("utf-8", errors="ignore")
            raise SlackSocketModeError(
                f"Slack Socket Mode HTTP error: {exc.code} {detail}"
            ) from exc
        except error.URLError as exc:  # pragma: no cover - network path
            raise SlackSocketModeError(f"Slack Socket Mode connection error: {exc}") from exc
        if not body.get("ok") or not body.get("url"):
            raise SlackSocketModeError(body.get("error", "socket_mode_open_failed"))
        return str(body["url"])

    def _normalize_event_payload(
        self,
        payload: dict[str, Any],
        envelope_id: str | None,
    ) -> dict[str, Any]:
        if payload.get("type") == "events_api" and isinstance(payload.get("event"), dict):
            event = dict(payload["event"])
            event.setdefault("event_id", payload.get("event_id", ""))
            event.setdefault("team_id", payload.get("team_id", ""))
        else:
            event = dict(payload)
        if envelope_id:
            event["__socket_envelope_id"] = envelope_id
        return event


def _default_socket_factory(url: str, timeout_seconds: float):
    try:
        import websocket
    except ImportError as exc:  # pragma: no cover - dependency path
        raise SlackSocketModeError("websocket-client is required for Socket Mode") from exc
    return websocket.create_connection(url, timeout=timeout_seconds)
