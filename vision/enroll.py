#!/usr/bin/env python3
"""Register people so the robot can tell them apart.

Two ways to enroll:

    # from photo files - best for people who are not here
    python3 vision/enroll.py --name 김민수 --photos ~/photos/minsu/*.jpg

    # from the robot camera - best for yourself, right now
    python3 vision/enroll.py --name 나 --camera 5

Three to five shots per person is the sweet spot: enough variation in angle and
lighting to survive a real room, few enough that one bad frame cannot dominate.

Only embeddings are stored - 512 numbers per shot. No photos are kept, and
nothing leaves this machine.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import camera  # noqa: E402
import faces  # noqa: E402


def from_camera(name: str, shots: int, delay: float) -> int:
    """Capture frames from the robot and enroll the largest face in each."""
    import cv2
    import numpy as np

    print(f"로봇을 바라봐 주세요. {shots}장을 {delay}초 간격으로 찍습니다.\n")
    accepted = 0

    for i in range(1, shots + 1):
        print(f"  [{i}/{shots}] 3초 뒤 촬영...", flush=True)
        time.sleep(delay)

        try:
            frame = camera.capture_bgr()
        except camera.CameraError as exc:
            print(f"      실패: {exc}")
            continue

        found = faces.analyzer().get(frame)
        if not found:
            print("      얼굴을 찾지 못했습니다. 조명과 거리를 확인해 주세요.")
            continue

        face = max(found, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        width = int(face.bbox[2] - face.bbox[0])
        if width < faces.MIN_FACE_WIDTH:
            print(f"      얼굴이 너무 작습니다 ({width}px). 조금 더 가까이 와 주세요.")
            continue

        store = faces._load()
        store.setdefault(name, []).append(np.asarray(face.normed_embedding, dtype=np.float32).tolist())
        faces._save(store)
        accepted += 1
        print(f"      등록됨 (얼굴 {width}px)")

        # Ask for a different angle so the next shot adds information.
        if i < shots:
            print("      고개를 살짝 돌려 주세요.")

    return accepted


def main() -> int:
    """Enroll one person from photos or from the robot camera."""
    parser = argparse.ArgumentParser(description="얼굴 등록")
    parser.add_argument("--name", help="등록할 사람의 이름")
    parser.add_argument("--photos", nargs="*", type=Path, default=[], help="사진 파일들")
    parser.add_argument("--camera", type=int, metavar="N", help="로봇 카메라로 N장 촬영")
    parser.add_argument("--delay", type=float, default=3.0, help="촬영 간격(초)")
    parser.add_argument("--list", action="store_true", help="등록된 사람 목록")
    parser.add_argument("--forget", metavar="NAME", help="등록 해제")
    args = parser.parse_args()

    if args.list:
        people = faces.roster()
        if not people:
            print("등록된 사람이 없습니다.")
        for name, count in people:
            print(f"  {name}  ({count}장)")
        return 0

    if args.forget:
        print("삭제했습니다." if faces.forget(args.forget) else "등록되어 있지 않습니다.")
        return 0

    if not args.name:
        parser.error("--name 이 필요합니다")

    if args.camera:
        if not camera.is_available():
            print("로봇 카메라에 연결할 수 없습니다. testbench 앱이 실행 중인지 확인하세요.", file=sys.stderr)
            return 1
        count = from_camera(args.name, args.camera, args.delay)
        print(f"\n{args.name}: {count}장 등록 완료.")
        return 0 if count else 1

    if not args.photos:
        parser.error("--photos 또는 --camera 중 하나가 필요합니다")

    missing = [p for p in args.photos if not p.exists()]
    if missing:
        print(f"파일을 찾을 수 없습니다: {', '.join(str(p) for p in missing)}", file=sys.stderr)
        return 1

    total, skipped = faces.enroll(args.name, list(args.photos))
    print(f"{args.name}: 총 {total}장 등록됨.")
    if skipped:
        print(f"  얼굴을 찾지 못해 건너뜀: {', '.join(skipped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
