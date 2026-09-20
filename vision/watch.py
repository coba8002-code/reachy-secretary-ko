#!/usr/bin/env python3
"""Watch the room: know who is here, and say something when a stranger is not.

    python3 vision/watch.py --owner 나

What it does with each frame:

  owner present   -> stay quiet, note that you are at the desk
  owner absent    -> a face that matches nobody is an intruder; push to phone
  guest present   -> someone known but not the owner; note it, stay quiet

Nothing is recorded. Frames are decoded, measured and discarded; only the
current presence state is written to disk, so other parts of the assistant can
ask "is he at his desk?" without running their own camera loop.

Announcements are deliberately conservative. A watcher that cries stranger at
a badly lit shoulder gets switched off within a day, so a face has to be seen
CONSECUTIVE_HITS times in a row before it counts.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import camera  # noqa: E402
import faces  # noqa: E402
import push  # noqa: E402

STATE_PATH = Path(
    os.getenv("REACHY_PRESENCE_STATE", Path.home() / ".local" / "share" / "reachy-secretary" / "presence.json")
)

POLL_SECONDS = float(os.getenv("REACHY_WATCH_INTERVAL", "3"))
# One frame is never enough: a turned head or a shadow reads as a stranger.
CONSECUTIVE_HITS = int(os.getenv("REACHY_WATCH_HITS", "3"))
# Do not re-alert about the same visitor every few seconds.
ALERT_COOLDOWN = float(os.getenv("REACHY_WATCH_COOLDOWN", "300"))
# How long without seeing the owner before counting them as away.
AWAY_AFTER = float(os.getenv("REACHY_AWAY_AFTER", "60"))

_running = True


def _stop(signum, frame) -> None:
    global _running
    _running = False


def _write_state(**fields) -> None:
    """Publish the current presence state for the rest of the assistant."""
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(fields, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def read_state() -> dict:
    """Return the last published presence state."""
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _alert_stranger(count: int, snapshot: bytes | None) -> None:
    """Tell the owner that someone they do not know is in the room."""
    now = datetime.now().strftime("%H시 %M분")
    who = "낯선 사람" if count == 1 else f"낯선 사람 {count}명"
    push.send(
        "Reachy - 낯선 사람",
        f"{now}, 방에 {who}이 보입니다.",
        priority="high",
    )
    if snapshot:
        push.send("Reachy - 방금 본 장면", "", image=snapshot)


def watch(owner: str, *, verbose: bool = False) -> None:
    """Run the watch loop until interrupted."""
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    print(f"감시 시작 - 주인: {owner} | {POLL_SECONDS}초 간격 | Ctrl-C 로 중지\n")

    owner_last_seen = 0.0
    last_alert = 0.0
    stranger_streak = 0

    while _running:
        loop_started = time.time()

        try:
            jpeg = camera.capture_jpeg()
            import cv2
            import numpy as np

            frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
            detections = faces.identify(frame) if frame is not None else []
        except camera.CameraError as exc:
            if verbose:
                print(f"  카메라 오류: {exc}")
            time.sleep(POLL_SECONDS)
            continue

        names = [d.name for d in detections]
        owner_here = owner in names
        known_guests = sorted({n for n in names if n and n != owner})
        strangers = sum(1 for d in detections if not d.is_known)

        now = time.time()
        if owner_here:
            owner_last_seen = now
        away_for = now - owner_last_seen if owner_last_seen else float("inf")
        owner_away = away_for > AWAY_AFTER

        _write_state(
            owner=owner,
            owner_present=owner_here,
            owner_away=owner_away,
            guests=known_guests,
            strangers=strangers,
            updated_at=now,
        )

        if verbose:
            state = "주인 있음" if owner_here else ("자리 비움" if owner_away else "확인 중")
            extra = f" | 손님 {known_guests}" if known_guests else ""
            extra += f" | 낯선 사람 {strangers}" if strangers else ""
            print(f"  [{datetime.now():%H:%M:%S}] {state}{extra}")

        # Only an unexplained face while the owner is away is worth a push.
        if owner_away and strangers:
            stranger_streak += 1
            if stranger_streak >= CONSECUTIVE_HITS and (now - last_alert) > ALERT_COOLDOWN:
                print(f"  [{datetime.now():%H:%M:%S}] 낯선 사람 {strangers}명 - 알림 전송")
                _alert_stranger(strangers, jpeg)
                last_alert = now
                stranger_streak = 0
        else:
            stranger_streak = 0

        elapsed = time.time() - loop_started
        time.sleep(max(0.0, POLL_SECONDS - elapsed))

    print("\n감시를 중지했습니다.")


def main() -> int:
    """Start the room watcher."""
    parser = argparse.ArgumentParser(description="방 감시 및 존재 인식")
    parser.add_argument("--owner", required=True, help="주인으로 등록된 이름")
    parser.add_argument("--verbose", action="store_true", help="매 프레임 상태 출력")
    args = parser.parse_args()

    enrolled = dict(faces.roster())
    if args.owner not in enrolled:
        print(f"'{args.owner}' 가 등록되어 있지 않습니다. 먼저 enroll.py 로 등록하세요.", file=sys.stderr)
        print(f"등록된 사람: {list(enrolled) or '없음'}", file=sys.stderr)
        return 1

    if not push.topic():
        push.setup_topic()
    print(f"푸시 구독 주소: https://ntfy.sh/{push.topic()}\n")

    watch(args.owner, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
