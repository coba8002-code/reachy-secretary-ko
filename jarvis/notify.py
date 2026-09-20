#!/usr/bin/env python3
"""Claude Code hook: let Reachy Mini announce what the session is doing.

Registered on three events (see settings.snippet.json):

  UserPromptSubmit  records when the turn started, and says nothing
  Notification      announces that Claude is blocked waiting for you
  Stop              announces completion, but only for turns long enough
                    that you probably walked away

Two rules govern everything here:

1. Never break the session. Any failure - robot off, network down, missing
   file - exits 0 silently. A notifier is not worth interrupting work for.
2. Never nag. Announcing every finished turn would make the robot chatter
   constantly and you would stop hearing it. Short turns stay silent.
"""

from __future__ import annotations

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

STATE_DIR = Path.home() / ".cache" / "reachy-jarvis"
STATE_FILE = STATE_DIR / "state.json"
SOUND_CACHE = STATE_DIR / "sounds"

# A turn shorter than this almost certainly finished while you were watching.
MIN_ANNOUNCE_SECONDS = float(os.getenv("REACHY_JARVIS_MIN_SECONDS", "45"))
# Never speak twice within this window, whatever fires.
COOLDOWN_SECONDS = float(os.getenv("REACHY_JARVIS_COOLDOWN", "8"))

# Notification types that mean "Claude is stuck until a human acts".
BLOCKING_NOTIFICATIONS = {"permission_prompt", "elicitation_dialog"}


def _read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(state: dict) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass  # a notifier that cannot cache is still a working notifier


def _ensure_uploaded(filename: str) -> bool:
    """Make sure one clip exists on the robot, re-uploading if it vanished.

    The daemon stores sounds in /tmp, so a robot reboot wipes them. Rather than
    make the user remember to re-run prepare.py, notice and fix it here.
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

    # Nothing cached locally either - regenerate everything in the background
    # so the next announcement works, and stay quiet for this one.
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


def announce(key: str) -> None:
    """Speak one variant of a phrase and play a matching emotion."""
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

    # The gesture is decoration - a failure here must not matter.
    try:
        robot.play_emotion(random.choice(phrases.emotions(key)))
    except (robot.RobotError, IndexError):
        pass


def _cooled_down(state: dict, now: float) -> bool:
    return now - float(state.get("last_spoken", 0)) >= COOLDOWN_SECONDS


def handle(event: dict) -> None:
    """Route one hook event to an announcement, or to silence."""
    name = event.get("hook_event_name")
    session = str(event.get("session_id", "default"))
    now = time.time()
    state = _read_state()

    if name == "UserPromptSubmit":
        state.setdefault("turns", {})[session] = now
        _write_state(state)
        return

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
        announce(key)
        state["last_spoken"] = now
        _write_state(state)
        return

    if name == "Stop":
        started = float(state.get("turns", {}).get(session, 0))
        # With no recorded start (hook not registered, or first turn) fall back
        # to announcing - better one extra sentence than silent failure.
        elapsed = now - started if started else MIN_ANNOUNCE_SECONDS

        if elapsed < MIN_ANNOUNCE_SECONDS or not _cooled_down(state, now):
            return

        key = "truncated" if event.get("stop_reason") == "max_tokens" else "done"
        announce(key)
        state["last_spoken"] = now
        state.setdefault("turns", {}).pop(session, None)
        _write_state(state)


def main() -> int:
    """Read the hook payload and announce, swallowing every failure."""
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
        handle(event)
    except Exception:
        # Deliberately broad: this process must never fail a hook.
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
