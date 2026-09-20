"""Let the user change the robot's volume by saying so.

This is the one setting people want to change without walking to a browser. If
the robot is too loud at night, "소리 좀 줄여줘" has to work; sending them to an
admin panel for it would be absurd.

Relative changes are handled here rather than in the model: "좀 줄여줘" means the
same thing every time, and a number the model invents would not be repeatable.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "jarvis"))
import robot  # noqa: E402

logger = logging.getLogger(__name__)

# One step of "조금". Large enough to hear, small enough that two steps are not
# a jump from comfortable to silent.
STEP = 15

# Named levels, so "최대로" and "작게" land somewhere predictable.
LEVELS = {"mute": 0, "quiet": 30, "normal": 65, "loud": 85, "max": 100}


def _describe(level: int) -> str:
    """Say a volume out loud the way a person would."""
    if level == 0:
        return "소리를 껐습니다."
    if level <= 30:
        return f"작게 줄였습니다. {level} 입니다."
    if level >= 95:
        return f"최대로 올렸습니다. {level} 입니다."
    return f"{level} 으로 맞췄습니다."


class SetVolume(Tool):
    """Change how loud the robot speaks."""

    name = "set_volume"
    description = (
        "Change the robot's speaker volume, or report what it is now. "
        "Use this whenever the user says the robot is too loud or too quiet, asks to turn it up or down, "
        "asks to mute it, or asks how loud it is. "
        "Prefer 'change' for vague requests like '좀 줄여줘' and 'level' only when they name a number. "
        "Answer with the short sentence this returns - do not add a number the tool did not give you."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["get", "set", "change"],
                "description": (
                    "'get' to report the current volume, 'set' for an exact level or a named level, "
                    "'change' to nudge it up or down from where it is."
                ),
            },
            "level": {
                "type": "integer",
                "description": "For 'set' with an exact number: 0 to 100.",
            },
            "named": {
                "type": "string",
                "enum": list(LEVELS),
                "description": (
                    "For 'set' without a number: 'mute' 껐으면, 'quiet' 작게, 'normal' 보통, "
                    "'loud' 크게, 'max' 최대로."
                ),
            },
            "steps": {
                "type": "integer",
                "description": (
                    "For 'change': how many steps, negative to lower. '좀 줄여줘' is -1, "
                    "'많이 줄여줘' is -2, '조금만 올려줘' is 1."
                ),
            },
        },
        "required": ["action"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Read or change the speaker volume."""
        action = (kwargs.get("action") or "").strip()

        try:
            current = robot.volume()
        except robot.RobotError as exc:
            logger.warning("Could not read volume: %s", exc)
            return {"error": "볼륨을 읽지 못했습니다."}

        if action == "get":
            return {"volume": current, "say": f"지금 볼륨은 {current} 입니다."}

        if action == "set":
            named = (kwargs.get("named") or "").strip()
            if named in LEVELS:
                target = LEVELS[named]
            elif kwargs.get("level") is not None:
                target = int(kwargs["level"])
            else:
                return {"error": "어느 정도로 맞출지 알려주세요."}
        elif action == "change":
            steps = int(kwargs.get("steps") or -1)
            target = current + steps * STEP
        else:
            return {"error": f"알 수 없는 동작입니다: {action}"}

        try:
            applied = robot.set_volume(target)
        except robot.RobotError as exc:
            logger.warning("Could not set volume: %s", exc)
            return {"error": "볼륨을 바꾸지 못했습니다."}

        logger.info("Tool call: set_volume %s -> %s", current, applied)
        return {"volume": applied, "previous": current, "say": _describe(applied)}
