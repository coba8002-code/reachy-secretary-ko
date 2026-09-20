#!/usr/bin/env python3
"""A conversation with the robot, typed in instead of spoken.

    ./.venv/bin/python assistant/chat.py

The microphone on this unit is dead - a hardware fault, reported to Pollen - so
the one thing missing from a real conversation is the ear. Everything after the
ear is here and runs on the robot: the persona from profiles/, the model the
admin panel assigned to the chat role, and the robot's own Korean voice out of
its own speaker. When the mic comes back, only the input line changes.

Replies are spoken sentence by sentence as they arrive, rather than waiting for
the whole answer. On this board synthesis runs faster than playback, so the
robot starts talking about a second and a half after you hit enter and does not
stop to think again mid-answer.
"""

from __future__ import annotations

import sys
import time
import wave
from typing import Any
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "assistant"))
sys.path.insert(0, str(ROOT / "jarvis"))

import config  # noqa: E402
import llm  # noqa: E402
import robot  # noqa: E402
import speech  # noqa: E402
import tools as toolkit  # noqa: E402

PROFILE = ROOT / "profiles" / "secretary_ko" / "profile.md"

# Long enough that the robot does not forget what was just said, short enough
# that a session does not slowly turn into a bill.
MAX_TURNS = 20

# A tool can lead to another tool - look, then speak about what you saw - but a
# model that keeps calling tools without ever answering has gone wrong, and the
# user is sitting in silence while it does.
MAX_TOOL_ROUNDS = 4


def persona() -> str:
    """Return the spoken-style instructions from the profile, without its front matter."""
    try:
        text = PROFILE.read_text(encoding="utf-8")
    except OSError:
        return "당신은 한국어로 말하는 비서 로봇입니다. 짧고 자연스럽게 말하세요."
    parts = text.split("+++")
    return (parts[2] if len(parts) > 2 else text).strip()


def speak(line: str) -> None:
    """Say one sentence on the robot and wait for it to finish.

    The daemon's play call returns immediately, so without waiting here every
    sentence would cut off the one before it.
    """
    line = line.strip()
    if not line:
        return
    if not speech.say(line):
        print(f"    (말하지 못했습니다: {line})")
        return

    wav = speech.CACHE_DIR / speech.cache_name(line)
    try:
        with wave.open(str(wav), "rb") as f:
            seconds = f.getnframes() / f.getframerate()
    except (OSError, wave.Error):
        seconds = 0.35 * len(line)
    time.sleep(seconds + 0.15)


def _call_part(call: dict) -> dict:
    """Rebuild the model's own functionCall part, signature and all."""
    part: dict = {"functionCall": {"name": call["name"], "args": call["args"]}}
    if call.get("signature"):
        part["thoughtSignature"] = call["signature"]
    return part


def respond(
    history: list[dict], system: str, declarations: list[dict],
    registry: dict[str, Any], started: float,
) -> list[str]:
    """Run one turn, calling tools as the model asks, and speak what comes back.

    Returns the sentences that were spoken, for the history.
    """
    spoken: list[str] = []
    buffer = ""

    for _round in range(MAX_TOOL_ROUNDS):
        calls: list[dict] = []
        said_this_round: list[str] = []

        for event in llm.stream_events(history, system=system, role="chat", tools=declarations or None):
            if "tool_call" in event:
                calls.append(event["tool_call"])
                continue

            # Speak by sentence so the robot starts talking before the answer ends.
            buffer += event.get("text", "")
            while True:
                sentence, buffer = llm.take_sentence(buffer)
                if not sentence:
                    break
                if sentence:
                    if not spoken:
                        print(f"[{time.time() - started:.1f}초] ", end="", flush=True)
                    print(sentence, end=" ", flush=True)
                    spoken.append(sentence)
                    said_this_round.append(sentence)
                    speak(sentence)

        if not calls:
            break

        # Whatever it said before reaching for a tool still has to be heard.
        if buffer.strip():
            sentence = buffer.strip()
            buffer = ""
            if not spoken:
                print(f"[{time.time() - started:.1f}초] ", end="", flush=True)
            print(sentence, end=" ", flush=True)
            spoken.append(sentence)
            said_this_round.append(sentence)
            speak(sentence)

        history.append({
            "role": "assistant",
            "parts": (
                ([{"text": " ".join(said_this_round)}] if said_this_round else [])
                + [_call_part(c) for c in calls]
            ),
        })

        responses = []
        for call in calls:
            tool = registry.get(call["name"])
            print(f"\n    [{call['name']}] ", end="", flush=True)
            if tool is None:
                result = {"error": f"그런 기능은 없습니다: {call['name']}"}
            else:
                try:
                    result = tool.run(**call["args"])
                except Exception as exc:  # noqa: BLE001 - a broken tool must not end the turn
                    result = {"error": f"{type(exc).__name__}: {exc}"}
            print(str(result)[:90], flush=True)
            responses.append({"functionResponse": {"name": call["name"], "response": result}})

        history.append({"role": "user", "parts": responses})
        print("    ", end="", flush=True)

    if buffer.strip():
        sentence = buffer.strip()
        print(sentence, end=" ", flush=True)
        spoken.append(sentence)
        speak(sentence)

    return spoken


def main() -> int:
    """Run the conversation loop until the user quits."""
    provider = config.provider_for_role("chat")
    label = config.PROVIDERS.get(provider, {}).get("label", provider)
    print(f"대화 상대  : {label} / {config.model_for(provider)}")
    print(f"목소리     : {'로봇 자체 (Piper)' if speech.tts.engine() == 'piper' else speech.tts.engine()}")

    try:
        awake = robot.is_awake()
    except robot.RobotError:
        awake = False
    print(f"로봇       : {'연결됨' if awake else '연결 안 됨 - 소리가 나지 않습니다'}")
    # Built once: listing the robot's moves is a round trip, and the set does not
    # change while a conversation is running.
    available = toolkit.build()
    registry = {t.name: t for t in available}
    declarations = [t.declaration() for t in available]

    print(f"할 수 있는 것: {', '.join(registry) or '(없음)'}")
    print("\n무엇이든 말씀하세요. 끝내려면 그냥 엔터, 또는 '그만'.\n")

    system = persona()
    history: list[dict] = []

    while True:
        try:
            said = input("당신 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not said or said in ("그만", "종료", "quit", "exit"):
            break

        history.append({"role": "user", "content": said})
        history = history[-MAX_TURNS * 2 :]

        print("로봇 > ", end="", flush=True)
        started = time.time()
        try:
            spoken = respond(history, system, declarations, registry, started)
        except llm.LLMError as exc:
            print(f"\n    실패: {exc}")
            history.pop()
            continue
        print()

        if spoken:
            history.append({"role": "assistant", "content": " ".join(spoken)})

    print("대화를 마칩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
