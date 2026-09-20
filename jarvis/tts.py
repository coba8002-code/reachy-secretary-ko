"""Korean speech synthesis that works on the robot itself.

The robot has no system speech engine - no `say`, no espeak, nothing. Until now
the announcement clips were rendered with macOS `say` and uploaded, which meant
the Mac had to be present for the robot to learn a new sentence. That is the one
thing this assistant is not allowed to need.

So the robot carries its own voice: a Piper model running on the Pi's own CPU.
It is slower than a cloud voice - about 1.6x faster than real time on this board,
plus five seconds to load the model - but it needs no network, no key, and no
laptop. Clips are cached by content, so each sentence is paid for once.

The macOS engine stays as a fallback for development on the Mac, where the Piper
model usually is not installed.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

# 22050 Hz is what the Korean Piper voice produces. The daemon plays the file as
# given, so leave it alone rather than resampling and losing quality for nothing.
_ROOT = Path(__file__).resolve().parent.parent
VOICE_PATH = _ROOT / "voices" / "ko_KR-kss-medium" / "ko_KR-kss-medium.onnx"

# Loading the model takes ~5s on the Pi, so a process that speaks more than once
# must not pay it twice.
_voice = None
_voice_failed = False


class TTSError(RuntimeError):
    """Raised when no speech engine can render the text."""


def engine() -> str:
    """Return which engine will be used: 'piper', 'macos', or '' if none."""
    if VOICE_PATH.exists():
        return "piper"
    if shutil.which("say") and shutil.which("afconvert"):
        return "macos"
    return ""


def _piper():
    """Load the Piper voice once and keep it."""
    global _voice, _voice_failed
    if _voice is not None or _voice_failed:
        return _voice
    try:
        from piper import PiperVoice

        _voice = PiperVoice.load(str(VOICE_PATH))
    except Exception as exc:  # noqa: BLE001 - any failure means fall back
        _voice_failed = True
        raise TTSError(f"Piper 음성을 열지 못했습니다: {exc}") from exc
    return _voice


def _render_piper(text: str, out_wav: Path) -> None:
    """Render text with the on-board Piper voice."""
    voice = _piper()
    chunks = list(voice.synthesize(text))
    if not chunks:
        raise TTSError("합성 결과가 비어 있습니다.")

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_wav), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(chunks[0].sample_rate)
        wav.writeframes(b"".join(c.audio_int16_bytes for c in chunks))


def _render_macos(text: str, out_wav: Path, voice: str) -> None:
    """Render text with the macOS speech engine, for development on the Mac."""
    if not shutil.which("say") or not shutil.which("afconvert"):
        raise TTSError("macOS의 say/afconvert 를 찾을 수 없습니다.")

    with tempfile.TemporaryDirectory() as tmp:
        aiff = Path(tmp) / "speech.aiff"
        # `say` writes AIFF; the daemon wants a plain PCM wav, so convert.
        subprocess.run(["say", "-v", voice, "-o", str(aiff), text], check=True, timeout=60)
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(out_wav)],
            check=True,
            timeout=60,
        )


def synthesize(text: str, out_wav: Path, *, macos_voice: str = "Yuna") -> str:
    """Render text to a mono PCM wav. Returns the engine that was used.

    Raises:
        TTSError: if no engine could produce audio.

    """
    text = " ".join(text.split())
    if not text:
        raise TTSError("합성할 문장이 비어 있습니다.")

    which = engine()
    if which == "piper":
        _render_piper(text, out_wav)
        return "piper"
    if which == "macos":
        try:
            _render_macos(text, out_wav, macos_voice)
        except (subprocess.SubprocessError, OSError) as exc:
            raise TTSError(f"macOS 음성 합성에 실패했습니다: {exc}") from exc
        return "macos"

    raise TTSError(
        "쓸 수 있는 음성 엔진이 없습니다. 로봇에서는 scripts/install-piper.sh 를 실행해 주세요."
    )
