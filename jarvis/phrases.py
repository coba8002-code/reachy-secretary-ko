"""What the robot says, and how it moves while saying it.

Each entry has several wordings. A robot that says the exact same sentence every
time stops being informative and starts being wallpaper - you tune it out. The
variants keep it worth listening to.

Keep every line short. This is spoken from across a room, usually while the user
is looking at something else.
"""

from __future__ import annotations

# key -> (spoken lines, emotion moves to pick from)
CATALOG: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    # Claude is blocked waiting for the user to approve something. This is the
    # one that actually matters - the session is stopped until they come back.
    "permission": (
        (
            "승인이 필요합니다.",
            "확인 한 번 부탁드려요.",
            "허락이 필요한 작업이 있어요.",
            "잠깐 봐주셔야 할 게 있습니다.",
        ),
        ("inquiring1", "inquiring2", "attentive1"),
    ),
    # Claude is waiting for input but not blocked on a permission decision.
    "idle": (
        (
            "기다리고 있습니다.",
            "다음 지시를 기다리는 중이에요.",
        ),
        ("attentive2", "thoughtful1"),
    ),
    # A long turn finished. Short turns are deliberately silent.
    "done": (
        (
            "작업이 끝났습니다.",
            "다 됐습니다.",
            "완료했어요.",
            "끝냈습니다. 확인해 주세요.",
        ),
        ("success1", "success2", "proud1", "cheerful1"),
    ),
    # The response hit the token ceiling, so it is cut off mid-thought.
    "truncated": (
        (
            "답이 너무 길어져서 중간에 끊겼어요.",
            "분량 제한에 걸렸습니다. 다시 물어봐 주세요.",
        ),
        ("oops1", "confused1"),
    ),
}


def keys() -> list[str]:
    """Return every phrase key."""
    return list(CATALOG)


def variants(key: str) -> tuple[str, ...]:
    """Return the spoken lines for one key."""
    return CATALOG[key][0]


def emotions(key: str) -> tuple[str, ...]:
    """Return the candidate emotion moves for one key."""
    return CATALOG[key][1]


def filename(key: str, index: int) -> str:
    """Return the wav filename used on the robot for one variant."""
    return f"jarvis_{key}_{index}.wav"


def all_filenames() -> list[str]:
    """Return every wav filename this catalog expects on the robot."""
    return [filename(key, i) for key in CATALOG for i in range(len(variants(key)))]
