#!/usr/bin/env python3
"""Claude Code hook: let Reachy Mini announce what the session is doing.

Two ways in:

  hook mode  - Claude Code pipes a JSON event on stdin (see settings.snippet.json)
  CLI mode   - any other tool calls it directly:

      python3 notify.py --agent 코덱스 --event done --task "리팩터링"

Announcements name the agent and the task, so when two tools are working at once
you know which one finished and what it was doing.

Two rules govern everything here:

1. Never break the session. Any failure - robot off, network down, missing
   file - exits 0 silently. A notifier is not worth interrupting work for.
2. Never nag. Announcing every finished turn would make the robot chatter
   constantly and you would stop hearing it. Short turns stay silent.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import phrases  # noqa: E402
import robot  # noqa: E402
import speech  # noqa: E402

STATE_DIR = Path.home() / ".cache" / "reachy-jarvis"
STATE_FILE = STATE_DIR / "state.json"
SOUND_CACHE = STATE_DIR / "sounds"

MIN_ANNOUNCE_SECONDS = float(os.getenv("REACHY_JARVIS_MIN_SECONDS", "45"))
COOLDOWN_SECONDS = float(os.getenv("REACHY_JARVIS_COOLDOWN", "8"))
# Long task names are unlistenable. Say enough to identify it, then stop.
MAX_TASK_CHARS = int(os.getenv("REACHY_JARVIS_MAX_TASK", "40"))
# How long to let the gesture (and its own audio) run before speaking.
EMOTE_LEAD_SECONDS = float(os.getenv("REACHY_JARVIS_EMOTE_LEAD", "1.2"))

BLOCKING_NOTIFICATIONS = {"permission_prompt", "elicitation_dialog"}
DEFAULT_AGENT = "클로드"


def _read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(state: dict) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # a notifier that cannot cache is still a working notifier


def shorten(text: str) -> str:
    """Reduce a prompt to something worth hearing out loud."""
    first = " ".join(text.strip().splitlines()[0].split()) if text.strip() else ""
    if len(first) <= MAX_TASK_CHARS:
        return first
    cut = first[:MAX_TASK_CHARS]
    # Prefer breaking at a space so we do not slice a word in half.
    space = cut.rfind(" ")
    return (cut[:space] if space > MAX_TASK_CHARS // 2 else cut).rstrip()


def _ensure_uploaded(filename: str) -> bool:
    """Make sure a pre-rendered clip exists on the robot, restoring it if not.

    The daemon stores sounds in /tmp, so a robot reboot wipes them.
    """
    try:
        if filename in robot.list_sounds():
            return True
    except robot.RobotError:
        return False

    local = SOUND_CACHE / filename
    if local.exists():
        try:
            robot.upload_sound(local)
            return True
        except robot.RobotError:
            return False

    try:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve().parent / "prepare.py")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        pass
    return False


def _emote(key: str) -> bool:
    """Play a matching gesture. Decoration - failure must not matter."""
    try:
        robot.play_emotion(random.choice(phrases.emotions(key)))
    except (robot.RobotError, IndexError):
        return False
    return True


def announce(key: str, *, agent: str = "", task: str = "") -> None:
    """Speak one announcement, naming the agent and task when we know them.

    Order matters. The recorded emotion moves carry their own audio, and
    starting one takes the speaker away from whatever is playing - tested, and
    it truncates the sentence mid-word. So the gesture goes first and the words
    follow, which also reads better: the robot moves to catch your eye, then
    tells you what happened.
    """
    # No gesture means the robot is unreachable; do not sit out the lead time.
    if _emote(key):
        time.sleep(EMOTE_LEAD_SECONDS)

    if agent or task:
        lead = {"done": f"{agent}가 끝냈습니다", "permission": f"{agent}가 승인을 기다립니다"}.get(key)
        if lead:
            spoken = f"{lead}. {task}." if task else f"{lead}."
            if speech.say(spoken):
                return
        # Fall through to the fixed clip if synthesis or upload failed.

    variants = phrases.variants(key)
    if not variants:
        return
    index = random.randrange(len(variants))
    filename = phrases.filename(key, index)
    if not _ensure_uploaded(filename):
        return
    try:
        robot.play_sound(filename)
    except robot.RobotError:
        return


def _cooled_down(state: dict, now: float) -> bool:
    return now - float(state.get("last_spoken", 0)) >= COOLDOWN_SECONDS


def _mark_spoken(state: dict, now: float) -> None:
    state["last_spoken"] = now
    _write_state(state)


def handle_event(event: dict, agent: str = DEFAULT_AGENT) -> None:
    """Route one Claude Code hook event to an announcement, or to silence."""
    name = event.get("hook_event_name")
    session = str(event.get("session_id", "default"))
    now = time.time()
    state = _read_state()

    if name == "UserPromptSubmit":
        # Remember what this turn is about so Stop can name it later.
        turns = state.setdefault("turns", {})
        turns[session] = {"at": now, "task": shorten(str(event.get("prompt", "")))}
        _write_state(state)
        return

    turn = state.get("turns", {}).get(session) or {}
    task = turn.get("task", "")

    if name == "Notification":
        kind = event.get("notification_type", "")
        if kind in BLOCKING_NOTIFICATIONS:
            key = "permission"
        elif kind == "idle_prompt":
            key = "idle"
        else:
            return  # auth messages and the like are not worth speaking
        if not _cooled_down(state, now):
            return
        announce(key, agent=agent, task=task if key == "permission" else "")
        _mark_spoken(state, now)
        return

    if name == "Stop":
        started = float(turn.get("at", 0))
        # With no recorded start (hook not registered, or first turn) fall back
        # to announcing - better one extra sentence than silent failure.
        elapsed = now - started if started else MIN_ANNOUNCE_SECONDS

        if elapsed < MIN_ANNOUNCE_SECONDS or not _cooled_down(state, now):
            return

        if event.get("stop_reason") == "max_tokens":
            announce("truncated")
        else:
            announce("done", agent=agent, task=task)

        _mark_spoken(state, now)
        state.setdefault("turns", {}).pop(session, None)
        _write_state(state)


def main() -> int:
    """Read a hook payload from stdin, or take an announcement from argv."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--agent", default=DEFAULT_AGENT)
    parser.add_argument("--event", choices=phrases.keys())
    parser.add_argument("--task", default="")
    args, _ = parser.parse_known_args()

    try:
        if args.event:
            state = _read_state()
            now = time.time()
            if _cooled_down(state, now):
                announce(args.event, agent=args.agent, task=shorten(args.task))
                _mark_spoken(state, now)
            return 0

        raw = sys.stdin.read()
        handle_event(json.loads(raw) if raw.strip() else {}, agent=args.agent)
    except Exception:
        # Deliberately broad: this process must never fail a hook.
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
