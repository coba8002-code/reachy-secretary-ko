"""Announcements that were not spoken because nobody was there to hear them.

The point of holding them is not to save them forever - it is to be able to say
one sentence when you sit back down instead of nothing at all. Three separate
"작업이 끝났습니다" replayed in a row would be worse than silence; one
"자리 비우신 동안 세 건 있었습니다" is what a person would say.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

STORE = Path.home() / ".cache" / "reachy-jarvis" / "backlog.json"

# Beyond this, an announcement is stale - you do not want to be told about an
# approval request from four hours ago as if it just happened.
MAX_AGE_SECONDS = float(60 * 60 * 2)
MAX_ITEMS = 30

# How each kind is counted in the spoken summary.
LABELS = {
    "permission": "승인 요청",
    "done": "작업 완료",
    "truncated": "중간에 끊긴 답",
    "idle": "대기 알림",
}


def _read() -> list[dict]:
    try:
        items = json.loads(STORE.read_text(encoding="utf-8"))
        return items if isinstance(items, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write(items: list[dict]) -> None:
    try:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        STORE.write_text(json.dumps(items[-MAX_ITEMS:], ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def add(key: str, *, agent: str = "", task: str = "") -> None:
    """Hold one announcement until someone is around."""
    items = _read()
    items.append({"key": key, "agent": agent, "task": task, "at": time.time()})
    _write(items)


def fresh() -> list[dict]:
    """Return held announcements that are still worth mentioning."""
    cutoff = time.time() - MAX_AGE_SECONDS
    return [i for i in _read() if float(i.get("at", 0)) >= cutoff]


def clear() -> None:
    """Drop everything held."""
    _write([])


def summary() -> str:
    """One spoken sentence covering what was missed, or empty if nothing was."""
    items = fresh()
    if not items:
        return ""

    counts: dict[str, int] = {}
    for item in items:
        key = item.get("key", "")
        counts[key] = counts.get(key, 0) + 1

    # Approvals first: they are the ones that were actually blocking something.
    order = ["permission", "truncated", "done", "idle"]
    parts = [f"{LABELS[k]} {counts[k]}건" for k in order if counts.get(k)]
    if not parts:
        return ""

    total = sum(counts.values())
    head = f"자리 비우신 동안 {total}건 있었습니다."
    body = ", ".join(parts) + "."

    # If an approval is still waiting, that is the thing worth naming.
    pending = [i for i in items if i.get("key") == "permission" and i.get("task")]
    if pending:
        return f"{head} {body} 승인 대기 중인 작업은 {pending[-1]['task']} 입니다."
    return f"{head} {body}"
