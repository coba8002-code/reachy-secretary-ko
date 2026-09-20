#!/usr/bin/env python3
"""Generate the Korean announcement clips and upload them to the robot.

Run this once after installing, and again whenever phrases.py changes:

    python3 jarvis/prepare.py

Why pre-generate: the hook runs while the user is waiting. Synthesizing speech
and uploading it on every notification would add seconds to something that
should be instant - on the robot's own CPU a sentence takes a second or two to
render. Here we pay that cost once; the hook then only has to say "play this
file".

The daemon keeps sounds under /tmp, so they are lost when the robot reboots.
notify.py detects that and re-runs this automatically.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import phrases  # noqa: E402
import robot  # noqa: E402
import tts  # noqa: E402

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
    """Render one line to a mono PCM wav.

    Raises:
        RuntimeError: if no speech engine is available.

    """
    tts.synthesize(text, out_wav, macos_voice=voice)


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

    using = tts.engine()
    if args.list_voices:
        print(f"현재 엔진: {using or '(없음)'}")
        if using == "piper":
            print(f"  로봇 자체 음성: {tts.VOICE_PATH.name}")
            return 0
        print("사용 가능한 한국어 음성:")
        for v in macos_voices():
            print("  -", v)
        return 0

    voices = [] if using == "piper" else macos_voices()
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

    print(f"음성: {tts.VOICE_PATH.name if using == 'piper' else args.voice}  (엔진: {using or '없음'})\n")
    try:
        count = build_and_upload(args.voice, cache)
    except (RuntimeError, subprocess.SubprocessError, robot.RobotError) as exc:
        print(f"\n실패: {exc}", file=sys.stderr)
        return 1

    print(f"\n{count}개 업로드 완료.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
