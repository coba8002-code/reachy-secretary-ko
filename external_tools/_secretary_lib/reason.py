"""The engine behind the tools that have to think before answering.

Two tools need more than the conversational model can give: the one that answers
hard questions, and the one that writes email prose. Both used to call Claude
directly, which meant that without a Claude key they did not degrade - they
simply failed, and with them the mail and calendar tools that share this module.

Which model does the thinking is a setting now, not a constant. It follows the
"깊은 판단" role from the admin panel, so moving from Gemini to Claude is a
dropdown rather than a deployment.

Callers stay synchronous-looking: everything here is awaited, and the blocking
HTTP work runs off the event loop so the audio side of the robot keeps running.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "assistant"))

import config  # noqa: E402
import llm  # noqa: E402

logger = logging.getLogger(__name__)

ROLE = "reason"


class ReasonError(RuntimeError):
    """Raised with a user-facing Korean message when the thinking step fails."""


def provider_label() -> str:
    """Return the human name of whatever is doing the thinking right now."""
    provider = config.provider_for_role(ROLE)
    return str(config.PROVIDERS.get(provider, {}).get("label", provider))


def _collect(system: str, prompt: str, schema: dict[str, Any] | None) -> str:
    """Run one turn and return the whole answer. Blocking - call in a thread."""
    return "".join(
        llm.stream_tokens(
            [{"role": "user", "content": prompt}],
            system=system,
            role=ROLE,
            schema=schema,
        )
    ).strip()


async def complete(
    *,
    system: str,
    prompt: str,
    max_tokens: int,
    effort: str = "medium",
    json_schema: dict[str, Any] | None = None,
) -> Any:
    """Run one turn on whichever model holds the judgement role.

    Returns the response text, or the parsed object when ``json_schema`` is given.

    Raises:
        ReasonError: on missing credentials, transport failure, or an empty or
            unparseable response. The message is safe to speak to the user.

    """
    provider = config.provider_for_role(ROLE)

    # Claude is kept on its own client: it is the only one here that supports
    # adaptive thinking and server-side fallback, and dropping to the plain
    # streaming path would quietly give up both.
    if provider == "anthropic":
        from _secretary_lib.claude import ClaudeError, complete as claude_complete

        try:
            return await claude_complete(
                system=system, prompt=prompt, max_tokens=max_tokens,
                effort=effort, json_schema=json_schema,
            )
        except ClaudeError as exc:
            raise ReasonError(str(exc)) from exc

    label = provider_label()
    try:
        text = await asyncio.to_thread(_collect, system, prompt, json_schema)
    except llm.LLMError as exc:
        logger.warning("Reasoning request failed on %s: %s", provider, exc)
        raise ReasonError(f"{label}에 연결하지 못했습니다: {exc}") from exc
    except Exception as exc:
        logger.exception("Reasoning request failed on %s", provider)
        raise ReasonError(f"{label} 호출에 실패했습니다: {type(exc).__name__}: {exc}") from exc

    if not text:
        raise ReasonError(f"{label}가 빈 답을 반환했습니다.")

    if json_schema is None:
        return text

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        # The providers are asked for structured output, so this means the answer
        # was cut off. Never hand a half-parsed object to the caller.
        logger.warning("%s returned unparseable JSON: %s", provider, text[:300])
        raise ReasonError(f"{label}의 응답 형식을 해석하지 못했습니다: {exc}") from exc
