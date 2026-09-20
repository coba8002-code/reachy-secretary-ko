"""What the robot can actually do, described so a model can choose to do it.

The official conversation app ships its own tools for moving and dancing, but
that app is not what runs here - chat.py is - so those tools do not exist in
this loop. Asking the robot to dance did nothing and it had no way to say why.
This module is that missing half: every capability declared once, with the code
that performs it right next to the words that describe it.

A tool is registered only when it can really run. A model handed a tool that
always fails will keep calling it and keep apologizing; better that it never
sees the tool and says plainly that it cannot do that yet.
"""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jarvis"))
sys.path.insert(0, str(ROOT / "external_tools"))

import robot  # noqa: E402

logger = logging.getLogger(__name__)

# Dancing back to back overloaded a head actuator during testing - stewart_5
# logged an Overload Error every second until the daemon restarted, while the
# other five motors logged none. The robot recovered, but the motor needs to
# rest between routines, and the model has no sense of that on its own.
DANCE_REST_SECONDS = 25.0
_last_dance = 0.0

# Moves whose names are not feelings. Offering "dance1" as an emotion invites the
# model to dance when it meant to look pleased.
_NOT_EMOTIONS = {"dance", "sleep", "mini-deep-sleep", "wake-mini-up", "toc-toc-toc", "electric"}


class Tool:
    """One thing the robot can do, and the words that let a model ask for it."""

    def __init__(self, name: str, description: str, parameters: dict, run: Callable[..., Any]):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.run = run

    def declaration(self) -> dict:
        """Return the function declaration to hand the model."""
        return {"name": self.name, "description": self.description, "parameters": self.parameters}


def _moves() -> tuple[list[str], list[str]]:
    """Return (dances, emotions) the robot actually has loaded."""
    try:
        every = robot.list_moves()
    except robot.RobotError as exc:
        logger.warning("Could not list moves: %s", exc)
        return [], []
    dances = sorted(m for m in every if m.startswith("dance"))
    emotions = sorted(
        m for m in every
        if not any(m.startswith(prefix) for prefix in _NOT_EMOTIONS)
    )
    return dances, emotions


def _build_movement(tools: list[Tool]) -> None:
    """Register dancing, emoting and stopping, if the robot has moves loaded."""
    dances, emotions = _moves()
    if not dances and not emotions:
        return

    if dances:
        import random

        def dance(**kwargs: Any) -> dict:
            global _last_dance
            waited = time.time() - _last_dance
            if waited < DANCE_REST_SECONDS:
                return {
                    "error": "방금 췄습니다. 모터가 식을 때까지 잠깐 쉬어야 합니다.",
                    "retry_after_seconds": round(DANCE_REST_SECONDS - waited),
                }
            pick = kwargs.get("which") or random.choice(dances)
            if pick not in dances:
                pick = random.choice(dances)
            robot.play_emotion(pick)
            _last_dance = time.time()
            return {"danced": pick, "say": "춤을 춥니다."}

        tools.append(Tool(
            name="dance",
            description=(
                "Make the robot dance. Use this whenever the user asks it to dance, to move, "
                "to show off, or says something is worth celebrating. "
                "It starts immediately and runs for a few seconds; say one short line like "
                "'춰볼게요' and do not describe the dance."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "which": {
                        "type": "string",
                        "enum": dances,
                        "description": "A specific dance, or leave it out for a random one.",
                    },
                },
            },
            run=dance,
        ))

    if emotions:
        def play_emotion(**kwargs: Any) -> dict:
            name = (kwargs.get("name") or "").strip()
            if name not in emotions:
                return {"error": f"그런 동작은 없습니다: {name}"}
            robot.play_emotion(name)
            return {"played": name}

        tools.append(Tool(
            name="play_emotion",
            description=(
                "Move the robot's body to show a feeling while you speak. "
                "Use it sparingly - roughly one turn in three or four. Moving on every sentence "
                "is distracting. Good moments: agreeing, being asked something surprising, "
                "finishing a task, not understanding. "
                "Do not mention that you are moving; just move."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "enum": emotions,
                        "description": "The move to play.",
                    },
                },
                "required": ["name"],
            },
            run=play_emotion,
        ))

    def stop_moving(**_: Any) -> dict:
        stopped = robot.stop_move()
        return {"stopped": stopped, "say": "멈췄습니다." if stopped else "움직이고 있지 않습니다."}

    tools.append(Tool(
        name="stop_moving",
        description="Stop whatever the robot is doing right now. Use it when the user says stop, 그만, or 멈춰.",
        parameters={"type": "object", "properties": {}},
        run=stop_moving,
    ))


def _build_volume(tools: list[Tool]) -> None:
    """Register speaker volume control."""
    STEP = 15
    LEVELS = {"mute": 0, "quiet": 30, "normal": 65, "loud": 85, "max": 100}

    def set_volume(**kwargs: Any) -> dict:
        action = kwargs.get("action") or "get"
        try:
            current = robot.volume()
        except robot.RobotError:
            return {"error": "볼륨을 읽지 못했습니다."}

        if action == "get":
            return {"volume": current, "say": f"지금 볼륨은 {current} 입니다."}

        if action == "set":
            named = kwargs.get("named")
            if named in LEVELS:
                target = LEVELS[named]
            elif kwargs.get("level") is not None:
                target = int(kwargs["level"])
            else:
                return {"error": "어느 정도로 맞출지 알려주세요."}
        else:
            target = current + int(kwargs.get("steps") or -1) * STEP

        try:
            applied = robot.set_volume(target)
        except robot.RobotError:
            return {"error": "볼륨을 바꾸지 못했습니다."}
        return {"volume": applied, "previous": current}

    tools.append(Tool(
        name="set_volume",
        description=(
            "Change how loud the robot speaks, or report it. "
            "Use 'change' for vague requests like '좀 줄여줘' and 'set' only when a number is named."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["get", "set", "change"], "description": "무엇을 할지."},
                "level": {"type": "integer", "description": "'set' 에서 정확한 숫자, 0 에서 100."},
                "named": {
                    "type": "string",
                    "enum": list(LEVELS),
                    "description": "숫자 대신 mute/quiet/normal/loud/max.",
                },
                "steps": {"type": "integer", "description": "'change' 에서 단계 수. 줄이려면 음수. 보통 -1."},
            },
            "required": ["action"],
        },
        run=set_volume,
    ))


def _build_deep_think(tools: list[Tool]) -> None:
    """Register the slow, careful thinking path."""
    try:
        from _secretary_lib.reason import ReasonError, complete
    except ImportError as exc:
        logger.warning("deep_think unavailable: %s", exc)
        return

    import asyncio

    SYSTEM = (
        "당신은 비서 로봇의 '깊은 생각' 엔진입니다. 답은 음성으로 읽힙니다. "
        "마크다운을 쓰지 마세요. 여섯 문장 이내로, 결론부터 말하세요. "
        "숫자와 시각은 읽는 대로 풀어 쓰세요. 모르면 모른다고 하세요."
    )

    def deep_think(**kwargs: Any) -> dict:
        question = (kwargs.get("question") or "").strip()
        if not question:
            return {"error": "무엇을 생각할지 알려주세요."}
        context = (kwargs.get("context") or "").strip()
        prompt = f"대화에서 나온 내용:\n{context}\n\n{question}" if context else question
        try:
            answer = asyncio.run(complete(system=SYSTEM, prompt=prompt, max_tokens=4000))
        except ReasonError as exc:
            return {"error": str(exc)}
        return {"answer": answer}

    tools.append(Tool(
        name="deep_think",
        description=(
            "Hand something hard to a stronger model: multi-step judgement, planning, drafting, "
            "technical questions, comparing options. Not for simple facts. "
            "It takes several seconds, so say '잠깐 생각해볼게' before calling it, and read the "
            "answer out close to as-is."
        ),
        parameters={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": (
                        "The full question as a standalone sentence. It cannot see this "
                        "conversation, so spell out what '그거' refers to."
                    ),
                },
                "context": {"type": "string", "description": "필요한 배경. 질문이 홀로 서면 비워두세요."},
            },
            "required": ["question"],
        },
        run=deep_think,
    ))


def build() -> list[Tool]:
    """Return every tool that can actually run right now."""
    tools: list[Tool] = []
    _build_movement(tools)
    _build_volume(tools)
    _build_deep_think(tools)
    return tools
