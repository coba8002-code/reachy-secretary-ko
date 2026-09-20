"""Shared Claude client for the secretary tools.

Both ask_claude (spoken answers) and gmail_draft (written email) delegate to
Claude, with very different output contracts. This module owns the transport and
the error messages; each caller supplies its own system prompt and schema.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

MODEL = "claude-opus-5"


class ClaudeError(RuntimeError):
    """Raised with a user-facing Korean message when Claude cannot answer."""


def _require_credentials() -> None:
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        raise ClaudeError("ANTHROPIC_API_KEY가 설정되어 있지 않습니다. .env 파일을 확인해 주세요.")


async def complete(
    *,
    system: str,
    prompt: str,
    max_tokens: int,
    effort: str = "medium",
    json_schema: dict[str, Any] | None = None,
) -> Any:
    """Run one Claude turn.

    Returns the response text, or the parsed object when ``json_schema`` is given.

    Raises:
        ClaudeError: on missing credentials, transport failure, refusal, or an
            empty/truncated response. The message is safe to speak to the user.

    """
    _require_credentials()

    try:
        from anthropic import AsyncAnthropic
    except ImportError as exc:
        raise ClaudeError("anthropic 패키지가 설치되어 있지 않습니다. pip install anthropic 을 실행해 주세요.") from exc

    output_config: dict[str, Any] = {"effort": effort}
    if json_schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": json_schema}

    try:
        client = AsyncAnthropic()
        async with client.beta.messages.stream(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            thinking={"type": "adaptive"},
            output_config=output_config,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            message = await stream.get_final_message()
    except Exception as exc:
        logger.exception("Claude request failed")
        raise ClaudeError(f"클로드에 연결하지 못했습니다: {type(exc).__name__}: {exc}") from exc

    # A refusal comes back as HTTP 200 with no usable text, so check first.
    if message.stop_reason == "refusal":
        raise ClaudeError("클로드가 이 요청에는 답하지 않기로 했습니다. 다르게 말씀해 주세요.")

    text = "".join(block.text for block in message.content if block.type == "text").strip()

    if not text:
        if message.stop_reason == "max_tokens":
            raise ClaudeError("답이 너무 길어져서 완성되지 못했습니다. 범위를 좁혀서 다시 요청해 주세요.")
        raise ClaudeError("클로드가 빈 답을 반환했습니다.")

    if json_schema is None:
        return text

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        # Structured outputs make this unlikely, but a truncated response can
        # still produce invalid JSON - never hand a half-parsed object onward.
        logger.warning("Claude returned unparseable JSON: %s", text[:300])
        raise ClaudeError(f"클로드의 응답 형식을 해석하지 못했습니다: {exc}") from exc
