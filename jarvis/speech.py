"""On-demand Korean speech for announcements whose text is not known in advance.

The fixed phrases in phrases.py are pre-rendered at install time. Task names are
not - they come from whatever the user typed - so those clips are synthesized the
first time they are needed and cached by content hash afterwards. Repeating the
same task name costs one HTTP call, same as a fixed phrase.

Synthesis itself lives in tts.py, which uses the robot's own Piper voice.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import robot
import tts

CACHE_DIR = Path.home() / ".cache" / "reachy-jarvis" / "sounds"
VOICE = os.getenv("REACHY_JARVIS_VOICE", "Yuna")


def cache_name(text: str) -> str:
    """Return the wav filename used for a piece of text."""
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    return f"jarvis_dyn_{digest}.wav"


def synthesize(text: str, out_wav: Path) -> bool:
    """Render text to a wav. Returns False if no speech engine is available."""
    try:
        tts.synthesize(text, out_wav, macos_voice=VOICE)
    except tts.TTSError:
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
