"""Thin LLM client for AI employee message generation.

Priority order:
1. Claude Code CLI subprocess (Team Plan authentication)
2. Bedrock (AWS SSO — jinwon profile)
3. Direct Anthropic API (ANTHROPIC_API_KEY)
4. Template fallback (rule-based)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model IDs
# ---------------------------------------------------------------------------

_BEDROCK_MODEL = "us.anthropic.claude-opus-4-6-v1"
_BEDROCK_FAST_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
_DIRECT_MODEL = "claude-opus-4-6"


def get_model() -> str:
    return os.environ.get("CLAWTEAM_LLM_MODEL", _BEDROCK_MODEL)


# ---------------------------------------------------------------------------
# Backend 1: Claude Code CLI (Team Plan)
# ---------------------------------------------------------------------------

def _chat_via_claude_cli(system: str, user: str, max_tokens: int) -> str:
    """Call Claude Code CLI as subprocess using Team Plan auth."""
    claude_bin = shutil.which("claude")
    # Fallback to known locations if not in PATH
    if not claude_bin:
        for candidate in [
            os.path.expanduser("~/.local/bin/claude"),
            "/usr/local/bin/claude",
        ]:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                claude_bin = candidate
                break
    if not claude_bin:
        logger.warning("claude CLI not found in PATH or known locations")
        return ""

    prompt = f"{system}\n\n---\n\n{user}"
    logger.info("Claude CLI: invoking %s", claude_bin)

    try:
        result = subprocess.run(
            [claude_bin, "-p", prompt, "--output-format", "text", "--max-turns", "1"],
            capture_output=True,
            text=True,
            timeout=60,
            env={
                **os.environ,
                # Clear Bedrock vars so CLI uses Team Plan
                "CLAUDE_CODE_USE_BEDROCK": "",
                "ANTHROPIC_API_KEY": "",
                "ANTHROPIC_MODEL": "",
            },
        )
        if result.returncode == 0 and result.stdout.strip():
            text = result.stdout.strip()
            if len(text) > max_tokens * 4:
                text = text[: max_tokens * 4]
            logger.info("Claude CLI returned %d chars", len(text))
            return text
        logger.warning(
            "Claude CLI exit=%d stdout=%d stderr=%s",
            result.returncode,
            len(result.stdout),
            (result.stderr or "")[:300],
        )
    except subprocess.TimeoutExpired:
        logger.warning("Claude CLI timed out after 60s")
    except Exception as exc:
        logger.warning("Claude CLI failed: %s", exc)

    return ""


# ---------------------------------------------------------------------------
# Backend 2: Bedrock (AWS SSO)
# ---------------------------------------------------------------------------

def _get_bedrock_client() -> Any | None:
    """Create an AnthropicBedrock client using AWS credentials.

    Tries the configured AWS_PROFILE first, then falls back to 'jinwon'
    profile (LBox AI SSO).
    """
    try:
        from anthropic import AnthropicBedrock
    except ImportError:
        return None

    region = os.environ.get("AWS_REGION", "us-east-1")
    profiles_to_try = []
    env_profile = os.environ.get("AWS_PROFILE", "")
    if env_profile:
        profiles_to_try.append(env_profile)
    if "jinwon" not in profiles_to_try:
        profiles_to_try.append("jinwon")
    profiles_to_try.append("")

    for profile in profiles_to_try:
        try:
            kwargs: dict[str, Any] = {"aws_region": region}
            if profile:
                import boto3
                session = boto3.Session(profile_name=profile)
                credentials = session.get_credentials()
                if credentials:
                    frozen = credentials.get_frozen_credentials()
                    kwargs["aws_access_key"] = frozen.access_key
                    kwargs["aws_secret_key"] = frozen.secret_key
                    if frozen.token:
                        kwargs["aws_session_token"] = frozen.token
            client = AnthropicBedrock(**kwargs)
            logger.debug("Bedrock client created with profile=%s", profile or "(default)")
            return client
        except Exception as exc:
            logger.debug("Bedrock client failed for profile=%s: %s", profile or "(default)", exc)
            continue

    return None


# ---------------------------------------------------------------------------
# Backend 3: Direct Anthropic API
# ---------------------------------------------------------------------------

def _get_direct_client() -> Any | None:
    """Create a direct Anthropic API client if ANTHROPIC_API_KEY is set."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    try:
        from anthropic import Anthropic
        return Anthropic(api_key=api_key)
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Unified chat interface
# ---------------------------------------------------------------------------

def chat(
    *,
    system: str,
    user: str,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 400,
) -> str:
    """Single-turn chat. Tries: Claude CLI → Bedrock → Direct API → empty."""
    chosen_model = model or get_model()

    # 1. Claude Code CLI (Team Plan — no API key needed)
    text = _chat_via_claude_cli(system, user, max_tokens)
    if text:
        return text

    # 2. Bedrock (AWS SSO)
    client = _get_bedrock_client()
    if client is not None:
        try:
            response = client.messages.create(
                model=chosen_model,
                system=system,
                messages=[{"role": "user", "content": user}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = (response.content[0].text if response.content else "").strip()
            if text:
                return text
        except Exception as exc:
            logger.warning("Bedrock call failed (model=%s): %s", chosen_model, exc)

    # 3. Direct Anthropic API
    direct = _get_direct_client()
    if direct is not None:
        direct_model = _DIRECT_MODEL if ("us." in chosen_model or "bedrock" in chosen_model.lower()) else chosen_model
        try:
            response = direct.messages.create(
                model=direct_model,
                system=system,
                messages=[{"role": "user", "content": user}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = (response.content[0].text if response.content else "").strip()
            if text:
                return text
        except Exception as exc:
            logger.warning("Direct API call failed (model=%s): %s", direct_model, exc)

    logger.warning("All LLM backends unavailable — falling back to template")
    return ""
