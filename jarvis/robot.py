"""Minimal Reachy Mini daemon client. Standard library only.

This runs inside a Claude Code hook, on every notification and every completed
turn. It must start fast and must never be the reason a hook fails, so it takes
no third-party dependencies and every call has a short timeout.
"""

from __future__ import annotations

import json
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

DEFAULT_HOST = os.getenv("REACHY_HOST", "192.168.45.147")
DEFAULT_PORT = os.getenv("REACHY_PORT", "8000")
EMOTION_DATASET = "pollen-robotics/reachy-mini-emotions-library"

# Short on purpose: a slow robot must not stall the hook.
TIMEOUT = float(os.getenv("REACHY_TIMEOUT", "3.0"))


class RobotError(RuntimeError):
    """Raised when the daemon cannot be reached or rejects a request."""


def base_url() -> str:
    """Return the daemon base URL."""
    return f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"


def _request(method: str, path: str, *, data: bytes | None = None, headers: dict[str, str] | None = None) -> bytes:
    req = urllib.request.Request(f"{base_url()}{path}", data=data, method=method)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            return response.read()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        raise RobotError(f"{method} {path}: {exc}") from exc


def volume() -> int:
    """Return the speaker volume, 0-100."""
    return int(json.loads(_request("GET", "/api/volume/current")).get("volume", 0))


def set_volume(level: int) -> int:
    """Set the speaker volume. Returns the level that was applied."""
    level = max(0, min(100, int(level)))
    _request(
        "POST",
        "/api/volume/set",
        data=json.dumps({"volume": level}).encode(),
        headers={"Content-Type": "application/json"},
    )
    return level


def play_test_sound() -> None:
    """Play the daemon's built-in test tone, so a volume change can be heard."""
    _request("POST", "/api/volume/test-sound", data=b"", headers={"Content-Type": "application/json"})


def mic_volume() -> int:
    """Return the microphone gain, 0-100."""
    return int(json.loads(_request("GET", "/api/volume/microphone/current")).get("volume", 0))


def set_mic_volume(level: int) -> int:
    """Set the microphone gain. Returns the level that was applied."""
    level = max(0, min(100, int(level)))
    _request(
        "POST",
        "/api/volume/microphone/set",
        data=json.dumps({"volume": level}).encode(),
        headers={"Content-Type": "application/json"},
    )
    return level


def list_sounds() -> list[str]:
    """Return the sound files currently on the robot."""
    payload = json.loads(_request("GET", "/api/media/sounds"))
    files = payload.get("files", [])
    return [f for f in files if isinstance(f, str)]


def upload_sound(path: Path) -> None:
    """Upload one wav to the robot's sound directory.

    The daemon stores sounds under /tmp, so they do not survive a robot reboot -
    callers are expected to re-upload when a file goes missing.
    """
    boundary = f"----reachyjarvis{uuid.uuid4().hex}"
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            path.read_bytes(),
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )

    _request(
        "POST",
        "/api/media/sounds/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )


def play_sound(filename: str) -> None:
    """Play a sound already present on the robot."""
    _request(
        "POST",
        "/api/media/play_sound",
        data=json.dumps({"file": filename}).encode(),
        headers={"Content-Type": "application/json"},
    )


def play_emotion(name: str) -> None:
    """Play one recorded emotion move."""
    dataset = urllib.parse.quote(EMOTION_DATASET, safe="")
    _request("POST", f"/api/move/play/recorded-move-dataset/{dataset}/{urllib.parse.quote(name)}")


def release_media() -> None:
    """Hand the camera and speakers back to the system for a moment."""
    _request("POST", "/api/media/release", data=b"", headers={"Content-Type": "application/json"})


def acquire_media() -> None:
    """Take the camera and speakers back."""
    _request("POST", "/api/media/acquire", data=b"", headers={"Content-Type": "application/json"})


def list_moves() -> list[str]:
    """Return every recorded move the robot can play."""
    dataset = urllib.parse.quote(EMOTION_DATASET, safe="")
    payload = json.loads(_request("GET", f"/api/move/recorded-move-datasets/list/{dataset}"))
    if isinstance(payload, list):
        return [m for m in payload if isinstance(m, str)]
    return []


def running_moves() -> list[str]:
    """Return the ids of the moves playing right now."""
    try:
        payload = json.loads(_request("GET", "/api/move/running"))
    except (RobotError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [m["uuid"] for m in payload if isinstance(m, dict) and m.get("uuid")]


def stop_move() -> int:
    """Stop every move that is playing. Returns how many were stopped.

    The daemon stops one move at a time, by id - there is no "stop everything"
    route - so a move started before this process began still gets stopped.
    """
    stopped = 0
    for uuid in running_moves():
        try:
            _request(
                "POST",
                "/api/move/stop",
                data=json.dumps({"uuid": uuid}).encode(),
                headers={"Content-Type": "application/json"},
            )
            stopped += 1
        except RobotError:
            continue
    return stopped


def is_moving() -> bool:
    """Return True while a move is still playing."""
    return bool(running_moves())


def is_awake() -> bool:
    """Return True when the daemon answers and its backend is ready."""
    try:
        status = json.loads(_request("GET", "/api/daemon/status"))
    except (RobotError, json.JSONDecodeError):
        return False
    return bool(status.get("backend_status", {}).get("ready"))
