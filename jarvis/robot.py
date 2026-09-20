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


def is_awake() -> bool:
    """Return True when the daemon answers and its backend is ready."""
    try:
        status = json.loads(_request("GET", "/api/daemon/status"))
    except (RobotError, json.JSONDecodeError):
        return False
    return bool(status.get("backend_status", {}).get("ready"))
