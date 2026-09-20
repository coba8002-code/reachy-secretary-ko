"""Route hard questions to Claude Opus 5 and return a speakable answer.

The realtime voice backend is tuned for latency, not for multi-step reasoning.
This tool is the escape hatch: the robot keeps the fast conversational loop and
delegates the small number of turns that actually need depth.

Every tool call already runs as its own asyncio task under the app's
BackgroundToolManager, so the seconds spent here do not block the audio loop.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _secretary_lib.claude import ClaudeError, complete  # noqa: E402

logger = logging.getLogger(__name__)

MAX_TOKENS = 8000

# The answer is spoken, not read. Everything here exists to stop Claude from
# producing text that sounds wrong out of a speaker.
SYSTEM_PROMPT = """\
당신은 책상 위 비서 로봇의 '깊은 생각' 엔진입니다. 로봇이 스스로 답하기 어려운 질문만 당신에게 넘어옵니다.

당신의 답은 화면에 표시되지 않고 **음성으로 읽힙니다.** 반드시 지키세요.

- 한국어로 답합니다. 질문이 다른 언어면 그 언어로 답합니다.
- 마크다운을 쓰지 마세요. 별표, 해시, 하이픈 목록, 표, 코드블록 전부 금지입니다. 소리로 읽으면 잡음입니다.
- 나열이 필요하면 "첫째, 둘째, 셋째"처럼 문장으로 이어서 말하세요.
- 숫자, 시각, 단위는 읽는 대로 풀어 쓰세요. "14:30"이 아니라 "오후 두 시 반", "3km"가 아니라 "삼 킬로미터".
- URL을 그대로 쓰지 마세요. 출처가 필요하면 이름만 말하세요.
- **분량은 여섯 문장 이내.** 듣는 사람은 중간에 되물을 수 있으니 한 번에 다 말할 필요 없습니다.
- 서론을 붙이지 마세요. 결론부터 말합니다.
- 모르면 모른다고 하세요. 추측을 사실처럼 말하지 마세요.

코드를 요청받으면, 코드 자체를 읽어주는 대신 접근 방법을 말로 설명하고 "자세한 코드는 화면으로 보내는 게 낫겠다"고 덧붙이세요.\
"""


def _memory_context(instance_path: Any) -> str:
    """Return the user's stored long-term facts, if the app exposes them."""
    try:
        from reachy_mini_conversation_app.memory import format_memory_for_prompt

        return format_memory_for_prompt(instance_path)
    except Exception as exc:  # the memory module is optional to this tool
        logger.debug("Could not load memory facts for ask_claude: %s", exc)
        return ""


class AskClaude(Tool):
    """Delegate a reasoning-heavy question to Claude."""

    name = "ask_claude"
    description = (
        "Ask Claude, a much stronger reasoning model, to work through something hard. "
        "Use this for multi-step judgment calls, planning, drafting text, technical or coding questions, "
        "comparing options, and summarizing long or messy information. "
        "Do NOT use it for simple facts, the time, the weather, or anything a web search answers - those are "
        "faster with the other tools. "
        "It takes several seconds, so say one short line like '잠깐 생각해볼게' before calling it. "
        "The reply is already written to be spoken: read it out close to as-is rather than rewriting it."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": (
                    "The full question, written out as a standalone question. "
                    "Claude cannot see the conversation, so do not use pronouns like '그거' or '아까 그것' - "
                    "spell out what they refer to."
                ),
            },
            "context": {
                "type": "string",
                "description": (
                    "Anything from the conversation Claude needs in order to answer: what the user already "
                    "said, decisions already made, constraints they mentioned. Leave empty if the question "
                    "stands entirely on its own."
                ),
            },
        },
        "required": ["question"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Send the question to Claude and return the spoken answer."""
        question = (kwargs.get("question") or "").strip()
        if not question:
            return {"error": "question must be a non-empty string"}

        context = (kwargs.get("context") or "").strip()
        memory = _memory_context(deps.instance_path)

        parts = []
        if memory:
            parts.append(memory)
        if context:
            parts.append(f"대화에서 지금까지 나온 내용:\n{context}")
        parts.append(question)

        logger.info("Tool call: ask_claude question=%s", question[:120])

        try:
            # Effort is held at medium rather than the default high: this is a
            # spoken turn, and a user waiting in silence feels every extra second.
            answer = await complete(
                system=SYSTEM_PROMPT,
                prompt="\n\n".join(parts),
                max_tokens=MAX_TOKENS,
                effort="medium",
            )
        except ClaudeError as exc:
            return {"error": str(exc)}

        return {"answer": answer, "model": "claude-opus-5"}
