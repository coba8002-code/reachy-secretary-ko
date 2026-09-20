"""Is the owner at the desk?

Uses the daemon's own face tracking rather than running recognition here. The
robot is a 4 GB CM4 - it cannot afford a face-embedding model, and it does not
need one for this question. "Is a person in front of me" is all we ask; the
daemon answers it from the camera at no extra cost to us.

This tells presence, not identity. A colleague standing at the desk reads as
present. That is the right trade for deciding whether to speak out loud: if
someone is there, talking is not shouting into an empty room.

Design rule: when in doubt, say the owner is present. A notifier that silently
swallows an approval request because the camera was pointed at a wall is worse
than one that occasionally talks to nobody.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

HOST = os.getenv("REACHY_HOST", "192.168.45.147")
PORT = os.getenv("REACHY_PORT", "8000")
TIMEOUT = float(os.getenv("REACHY_PRESENCE_TIMEOUT", "3.0"))

STATE_PATH = Path.home() / ".cache" / "reachy-jarvis" / "presence.json"

# A face is missed for all sorts of innocent reasons - turning to a second
# monitor, reaching for coffee. Only call it away after a sustained absence.
AWAY_AFTER = float(os.getenv("REACHY_AWAY_AFTER", "90"))


def _get(path: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://{HOST}:{PORT}{path}", timeout=TIMEOUT) as response:
            return json.loads(response.read())
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError):
        return None


def _post(path: str) -> bool:
    try:
        request = urllib.request.Request(f"http://{HOST}:{PORT}{path}", method="POST")
        with urllib.request.urlopen(request, timeout=TIMEOUT):
            return True
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return False


def enable_tracking() -> bool:
    """Ask the daemon to start looking for faces."""
    return _post("/api/media/tracking/enable")


def face_visible() -> bool | None:
    """True/False if the daemon answered, None if we could not ask it."""
    payload = _get("/api/media/tracking/face")
    if payload is None or payload.get("status") != "ok":
        return None
    target = payload.get("face_target") or {}
    return bool(target.get("detected"))


def _read() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write(state: dict) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def observe() -> dict:
    """Take one reading and update the stored presence state.

    Returns the state: {"present": bool, "last_seen": float, "known": bool}
    where `known` is False when the camera could not be consulted at all.
    """
    state = _read()
    now = time.time()
    seen = face_visible()

    if seen is None:
        # No answer from the daemon. Do not let an unreachable camera decide
        # that nobody is home - leave the last reading and mark it unknown.
        state["known"] = False
        _write(state)
        return {"present": True, "last_seen": state.get("last_seen", now), "known": False}

    state["known"] = True
    if seen:
        state["last_seen"] = now

    last_seen = float(state.get("last_seen", 0))
    present = seen or (last_seen and (now - last_seen) < AWAY_AFTER)

    state["present"] = bool(present)
    _write(state)
    return {"present": bool(present), "last_seen": last_seen, "known": True}


def is_present() -> bool:
    """Best guess at whether the owner can hear the robot right now."""
    return observe()["present"]


def away_seconds() -> float:
    """How long since a face was last seen. 0 when someone is there."""
    state = _read()
    last_seen = float(state.get("last_seen", 0))
    if not last_seen:
        return 0.0
    return max(0.0, time.time() - last_seen)
