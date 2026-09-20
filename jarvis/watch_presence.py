#!/usr/bin/env python3
"""Notice when the owner comes back, and brief them on what they missed.

    python3 jarvis/watch_presence.py

The hook can only speak when Claude Code does something. If you step away, work
finishes, and you return to a quiet session, nothing would ever fire - the
briefing would sit in the backlog until your next prompt. This closes that gap:
it watches the desk and speaks the moment you are back.

Cheap by design: one HTTP call to the daemon every few seconds, no image
processing on this machine, nothing written but a small state file.
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import backlog  # noqa: E402
import notify  # noqa: E402
import presence  # noqa: E402

POLL_SECONDS = 5.0
# Require a few consecutive sightings before declaring a return, so one frame
# catching a passer-by does not trigger the briefing.
RETURN_HITS = 3

_running = True


def _stop(signum, frame) -> None:
    global _running
    _running = False


def run(*, verbose: bool = False) -> None:
    """Watch for the owner's return and deliver any held announcements."""
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    if not presence.enable_tracking():
        print("경고: 얼굴 추적을 켜지 못했습니다. 로봇 연결을 확인하세요.", file=sys.stderr)

    print(f"복귀 감지 시작 — {POLL_SECONDS}초 간격, Ctrl-C 로 중지\n")

    was_present = True   # assume someone is there until told otherwise
    streak = 0

    while _running:
        state = presence.observe()
        here = state["present"]

        if here and not was_present:
            streak += 1
            if streak >= RETURN_HITS:
                held = len(backlog.fresh())
                if held:
                    print(f"  [{datetime.now():%H:%M:%S}] 복귀 감지 — 밀린 알림 {held}건 보고")
                    notify._deliver_backlog()
                else:
                    print(f"  [{datetime.now():%H:%M:%S}] 복귀 감지 — 보고할 내용 없음")
                was_present = True
                streak = 0
        elif here:
            was_present, streak = True, 0
        else:
            if was_present:
                print(f"  [{datetime.now():%H:%M:%S}] 자리 비움 — 이후 알림은 쌓아둡니다")
            was_present, streak = False, 0

        if verbose:
            mark = "있음" if here else "없음"
            src = "" if state["known"] else " (카메라 응답 없음 → 있음으로 간주)"
            print(f"  [{datetime.now():%H:%M:%S}] {mark}{src} | 대기 {len(backlog.fresh())}건")

        time.sleep(POLL_SECONDS)

    print("\n중지했습니다.")


def main() -> int:
    """Start the return watcher."""
    parser = argparse.ArgumentParser(description="자리 복귀 감지 및 브리핑")
    parser.add_argument("--verbose", action="store_true", help="매 확인마다 상태 출력")
    args = parser.parse_args()
    run(verbose=args.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
