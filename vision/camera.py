"""Pull frames from the Reachy Mini camera over HTTP.

The robot's daemon exposes face *detection* but not recognition, and the Pi is
too slow to run recognition without stealing CPU from the conversation. So the
frames come to the Mac and the thinking happens here.

Two sources, tried in order:
  testbench app  /api/camera/capture on :8042 - returns a base64 JPEG
  daemon         /api/media/... - no still-capture route, so unused for now
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request

import numpy as np

HOST = os.getenv("REACHY_HOST", "192.168.45.147")
TESTBENCH_PORT = os.getenv("REACHY_TESTBENCH_PORT", "8042")
TIMEOUT = float(os.getenv("REACHY_CAMERA_TIMEOUT", "10"))


class CameraError(RuntimeError):
    """Raised when a frame cannot be captured."""


def capture_jpeg() -> bytes:
    """Return one JPEG frame from the robot camera.

    Raises:
        CameraError: if the capture endpoint is unreachable or returns no image.

    """
    url = f"http://{HOST}:{TESTBENCH_PORT}/api/camera/capture"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as exc:
        raise CameraError(
            f"카메라 프레임을 받지 못했습니다 ({exc}). 로봇에서 testbench 앱이 실행 중인지 확인하세요."
        ) from exc

    encoded = payload.get("image")
    if not encoded:
        raise CameraError("응답에 이미지가 없습니다.")

    try:
        return base64.b64decode(encoded)
    except (ValueError, TypeError) as exc:
        raise CameraError(f"이미지를 디코딩하지 못했습니다: {exc}") from exc


def capture_bgr() -> np.ndarray:
    """Return one frame as an OpenCV BGR array."""
    import cv2

    data = np.frombuffer(capture_jpeg(), dtype=np.uint8)
    frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if frame is None:
        raise CameraError("JPEG 디코딩에 실패했습니다.")
    return frame


def is_available() -> bool:
    """Return True when a frame can be captured right now."""
    try:
        capture_jpeg()
    except CameraError:
        return False
    return True
