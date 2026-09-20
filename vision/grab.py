#!/usr/bin/env python3
"""Take one photo with the robot's camera and write it to a file.

    python3 vision/grab.py /tmp/frame.jpg

This runs under the *system* Python, not the project's virtualenv, because
picamera2 is an apt package wired to the system libcamera build and does not
install cleanly anywhere else. Keeping it in its own process also keeps the
camera stack out of the conversation loop's memory, which matters on a board
with four gigabytes.

The daemon holds the camera while it is tracking faces, so the caller has to
hand it over first - see assistant/eyes.py, which owns that dance.
"""

from __future__ import annotations

import sys
from pathlib import Path

# 1280x720 is the camera's default mode and plenty for describing a room. Larger
# frames cost capture time and upload bytes without telling the model more.
WIDTH = 1280
HEIGHT = 720


def main() -> int:
    """Capture one frame to the path given on the command line."""
    if len(sys.argv) < 2:
        print("usage: grab.py <out.jpg>", file=sys.stderr)
        return 2
    out = Path(sys.argv[1])

    try:
        from picamera2 import Picamera2
    except ImportError as exc:
        print(f"picamera2 가 없습니다: {exc}", file=sys.stderr)
        return 1

    camera = Picamera2()
    try:
        camera.configure(camera.create_still_configuration(main={"size": (WIDTH, HEIGHT)}))
        camera.start()
        # The first frames come out before auto exposure and white balance have
        # settled, so the picture would be dark or green. Let it look first.
        camera.capture_file(str(out), format="jpeg", wait=True)
    finally:
        try:
            camera.stop()
        finally:
            camera.close()

    if not out.exists() or out.stat().st_size == 0:
        print("빈 파일이 만들어졌습니다.", file=sys.stderr)
        return 1
    print(out.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
