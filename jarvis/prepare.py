#!/usr/bin/env python3
"""Generate the Korean announcement clips and upload them to the robot.

Run this once after installing, and again whenever phrases.py changes:

    python3 jarvis/prepare.py

Why pre-generate: the hook runs while the user is waiting. Synthesizing speech
and uploading it on every notification would add seconds to something that
should be instant. Here we pay that cost once; the hook then only has to say
"play this file".

The daemon keeps sounds under /tmp, so they are lost when the robot reboots.
notify.py detects that and re-runs this automatically.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import phrases  # noqa: E402
import robot  # noqa: E402

DEFAULT_VOICE = "Yuna"


def macos_voices() -> list[str]:
    """Return the Korean voices macOS has installed."""
    if not shutil.which("say"):
        return []
    try:
        out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=15).stdout
    except (subprocess.SubprocessError, OSError):
        return []
    return [line.split()[0] for line in out.splitlines() if "ko_KR" in line]


def synthesize(text: str, out_wav: Path, voice: str) -> None:
    """Render one line to a 16 kHz mono wav using the macOS speech engine.

    Raises:
        RuntimeError: if `say` or `afconvert` is unavailable or fails.

    """
    if not shutil.which("say") or not shutil.which("afconvert"):
        raise RuntimeError("이 스크립트는 macOS의 say/afconvert 를 사용합니다.")

    with tempfile.TemporaryDirectory() as tmp:
        aiff = Path(tmp) / "speech.aiff"
        # `say` writes AIFF; the daemon wants a plain PCM wav, so convert.
        subprocess.run(["say", "-v", voice, "-o", str(aiff), text], check=True, timeout=60)
        subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(out_wav)],
            check=True,
            timeout=60,
        )


def build_and_upload(voice: str, cache: Path, *, verbose: bool = True) -> int:
    """Render every phrase variant and upload it. Returns the number uploaded."""
    cache.mkdir(parents=True, exist_ok=True)
    uploaded = 0

    for key in phrases.keys():
        for index, text in enumerate(phrases.variants(key)):
            name = phrases.filename(key, index)
            wav = cache / name

            if not wav.exists():
                synthesize(text, wav, voice)

            robot.upload_sound(wav)
            uploaded += 1
            if verbose:
                print(f"  {name:28} {text}")

    return uploaded


def main() -> int:
    """Render and upload every announcement clip."""
    parser = argparse.ArgumentParser(description="Reachy Jarvis 음성 준비")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help=f"macOS 한국어 음성 (기본: {DEFAULT_VOICE})")
    parser.add_argument("--list-voices", action="store_true", help="사용 가능한 한국어 음성 출력")
    parser.add_argument("--rebuild", action="store_true", help="캐시를 지우고 다시 합성")
    args = parser.parse_args()

    voices = macos_voices()
    if args.list_voices:
        print("사용 가능한 한국어 음성:")
        for v in voices:
            print("  -", v)
        return 0

    if voices and args.voice not in voices:
        print(f"'{args.voice}' 음성이 없습니다. 사용 가능: {', '.join(voices) or '(없음)'}", file=sys.stderr)
        return 1

    cache = Path.home() / ".cache" / "reachy-jarvis" / "sounds"
    if args.rebuild and cache.exists():
        shutil.rmtree(cache)

    print(f"로봇: {robot.base_url()}")
    if not robot.is_awake():
        print("로봇에 연결할 수 없습니다. 전원과 네트워크를 확인해 주세요.", file=sys.stderr)
        return 1

    print(f"음성: {args.voice}\n")
    try:
        count = build_and_upload(args.voice, cache)
    except (RuntimeError, subprocess.SubprocessError, robot.RobotError) as exc:
        print(f"\n실패: {exc}", file=sys.stderr)
        return 1

    print(f"\n{count}개 업로드 완료.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
