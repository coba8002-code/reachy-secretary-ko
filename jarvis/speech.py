"""On-demand Korean speech for announcements whose text is not known in advance.

The fixed phrases in phrases.py are pre-rendered at install time. Task names are
not - they come from whatever the user typed - so those clips are synthesized the
first time they are needed and cached by content hash afterwards. Repeating the
same task name costs one HTTP call, same as a fixed phrase.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import robot

CACHE_DIR = Path.home() / ".cache" / "reachy-jarvis" / "sounds"
VOICE = os.getenv("REACHY_JARVIS_VOICE", "Yuna")


def cache_name(text: str) -> str:
    """Return the wav filename used for a piece of text."""
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    return f"jarvis_dyn_{digest}.wav"


def synthesize(text: str, out_wav: Path) -> bool:
    """Render text to a 16 kHz mono wav. Returns False if the tools are missing."""
    if not shutil.which("say") or not shutil.which("afconvert"):
        return False

    try:
        with tempfile.TemporaryDirectory() as tmp:
            aiff = Path(tmp) / "s.aiff"
            subprocess.run(
                ["say", "-v", VOICE, "-o", str(aiff), text],
                check=True,
                timeout=30,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            out_wav.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(out_wav)],
                check=True,
                timeout=30,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except (subprocess.SubprocessError, OSError):
        return False
    return out_wav.exists()


def say(text: str) -> bool:
    """Speak arbitrary text on the robot, synthesizing and caching as needed."""
    text = " ".join(text.split())
    if not text:
        return False

    name = cache_name(text)
    local = CACHE_DIR / name

    try:
        present = name in robot.list_sounds()
    except robot.RobotError:
        return False

    if not present:
        if not local.exists() and not synthesize(text, local):
            return False
        try:
            robot.upload_sound(local)
        except robot.RobotError:
            return False

    try:
        robot.play_sound(name)
    except robot.RobotError:
        return False
    return True
