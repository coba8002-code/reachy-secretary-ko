"""Borrow the camera from the daemon, take one photo, give it straight back.

The daemon owns the camera continuously - it is what makes the robot follow your
face - and the sensor cannot be opened twice. There is no still-capture route on
the daemon either, so the only way to get a picture is to ask it to let go for a
moment.

That moment costs the robot its face tracking *and* its speakers, so the window
is kept as small as possible and the camera is always handed back, including
when the capture fails. A robot that goes deaf because a photo went wrong is a
worse outcome than no photo.

DO NOT WIRE THIS INTO THE CONVERSATION YET. Measured on 2026-09-21: the photo
comes out fine - 147 KB, 2.2 seconds - but taking it kills the daemon. Even
after /api/media/release the daemon keeps its own libcamera handle open, and
picamera2 taking the sensor from under it brings the process down with no
traceback, which is what a native crash looks like. systemd restarts it in about
ten seconds and the robot comes back healthy, but ten seconds of a dead robot is
not a price a conversation can pay for one photo.

The way out is probably to read a frame from the video the daemon is already
streaming over WebRTC, instead of competing for the device. Left here because
the capture path itself works and the finding is worth keeping.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jarvis"))

import robot  # noqa: E402

logger = logging.getLogger(__name__)

GRAB = ROOT / "vision" / "grab.py"

# picamera2 lives in the system Python: it is an apt package tied to the system
# libcamera build, and the project virtualenv cannot see it.
SYSTEM_PYTHON = "/usr/bin/python3"

# Starting libcamera and settling exposure takes a few seconds on this board.
CAPTURE_TIMEOUT = 25.0


class EyesError(RuntimeError):
    """Raised with a user-facing Korean message when a photo cannot be taken."""


def available() -> bool:
    """Return True when a photo could be taken right now."""
    if not GRAB.exists() or not Path(SYSTEM_PYTHON).exists():
        return False
    try:
        subprocess.run(
            [SYSTEM_PYTHON, "-c", "import picamera2"],
            check=True, timeout=30, capture_output=True,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return True


def capture() -> bytes:
    """Take one photo and return it as JPEG bytes.

    Raises:
        EyesError: if the camera could not be borrowed or produced no image.

    """
    try:
        robot.release_media()
    except robot.RobotError as exc:
        raise EyesError(f"카메라를 넘겨받지 못했습니다: {exc}") from exc

    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "frame.jpg"
            try:
                result = subprocess.run(
                    [SYSTEM_PYTHON, str(GRAB), str(out)],
                    timeout=CAPTURE_TIMEOUT, capture_output=True, text=True,
                )
            except subprocess.TimeoutExpired as exc:
                raise EyesError("카메라가 응답하지 않습니다.") from exc
            except OSError as exc:
                raise EyesError(f"카메라를 실행하지 못했습니다: {exc}") from exc

            if result.returncode != 0 or not out.exists():
                detail = (result.stderr or "").strip().splitlines()
                reason = detail[-1] if detail else f"종료코드 {result.returncode}"
                logger.warning("Capture failed: %s", reason)
                raise EyesError(f"사진을 찍지 못했습니다: {reason}")

            return out.read_bytes()
    finally:
        # Always, even on failure. The speakers come back with the camera.
        try:
            robot.acquire_media()
        except robot.RobotError as exc:
            logger.error("Could not hand the camera back: %s", exc)
