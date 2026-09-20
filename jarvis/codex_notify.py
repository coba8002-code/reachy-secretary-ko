#!/usr/bin/env python3
"""Codex CLI adapter: announce Codex turns on Reachy Mini.

Wire it up in ~/.codex/config.toml:

    notify = ["python3", "/Users/<you>/reachy-secretary-ko/jarvis/codex_notify.py"]

Codex documents `notify` as "a command invoked for notifications; receives a
JSON payload", but does not publish the payload's field names. Rather than hard
code a schema that may not match, this reads whatever arrives - from argv or
stdin - and looks for the task text under any of the plausible keys. If it finds
none, it still announces, just without naming the task.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import notify  # noqa: E402

AGENT = "코덱스"

# Ordered by how well each would serve as a spoken task name.
TASK_KEYS = (
    "input-messages",
    "input_messages",
    "prompt",
    "user-message",
    "user_message",
    "turn-title",
    "title",
    "last-assistant-message",
    "last_assistant_message",
    "message",
    "messages",
)

# Payload "type" values that mean Codex is blocked on a human.
BLOCKING_HINTS = ("approval", "permission", "confirm", "request")


def _payload() -> dict:
    """Read the JSON payload from argv or stdin, whichever carries it."""
    for arg in sys.argv[1:]:
        arg = arg.strip()
        if arg.startswith("{"):
            try:
                return json.loads(arg)
            except json.JSONDecodeError:
                continue
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _task(payload: dict) -> str:
    """Pull something worth saying out of an undocumented payload."""
    for key in TASK_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, str) and first.strip():
                return first
            if isinstance(first, dict):
                for inner in ("content", "text", "message"):
                    text = first.get(inner)
                    if isinstance(text, str) and text.strip():
                        return text
    return ""


def main() -> int:
    """Announce one Codex notification."""
    try:
        payload = _payload()
        kind = str(payload.get("type", "")).lower()
        event = "permission" if any(h in kind for h in BLOCKING_HINTS) else "done"

        sys.argv = [sys.argv[0], "--agent", AGENT, "--event", event, "--task", _task(payload)]
        notify.main()
    except Exception:
        # Same contract as the Claude hook: never fail the caller.
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
