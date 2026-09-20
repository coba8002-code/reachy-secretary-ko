"""Create a Google Calendar event."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _secretary_lib.google_auth import GoogleAuthError, build_service  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_TZ = os.getenv("REACHY_SECRETARY_TZ", "Asia/Seoul")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")
MAX_DURATION_MIN = 24 * 60


def _tzinfo() -> dt.tzinfo:
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(DEFAULT_TZ)
    except Exception:
        logger.warning("Unknown timezone %s, falling back to UTC", DEFAULT_TZ)
        return dt.timezone.utc


def _create(
    title: str,
    date: str,
    start_time: str,
    duration_minutes: int,
    location: str | None,
) -> dict[str, Any]:
    """Blocking Calendar write. Call via asyncio.to_thread."""
    tz = _tzinfo()
    start = dt.datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    end = start + dt.timedelta(minutes=duration_minutes)

    body: dict[str, Any] = {
        "summary": title,
        "start": {"dateTime": start.isoformat(), "timeZone": DEFAULT_TZ},
        "end": {"dateTime": end.isoformat(), "timeZone": DEFAULT_TZ},
    }
    if location:
        body["location"] = location

    service = build_service("calendar", "v3")
    created = service.events().insert(calendarId="primary", body=body).execute()

    return {
        "created": True,
        "title": created.get("summary", title),
        "date": start.strftime("%Y-%m-%d"),
        "start": start.strftime("%H:%M"),
        "end": end.strftime("%H:%M"),
        "location": created.get("location"),
    }


class CalendarAddEvent(Tool):
    """Add one event to the user's calendar."""

    name = "calendar_add_event"
    description = (
        "Create one event on the user's Google Calendar. "
        "Only call this once the title, date and start time are all unambiguous - if any of them is vague "
        "('next week', 'sometime tomorrow'), ask the user one clarifying question first instead of guessing. "
        "Resolve relative dates yourself before calling: pass an absolute date. "
        "After it succeeds, read the created event back to the user in one short sentence."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "What the event is, as the user described it.",
            },
            "date": {
                "type": "string",
                "description": "Absolute calendar date in YYYY-MM-DD form. Resolve 'tomorrow' etc. yourself.",
            },
            "start_time": {
                "type": "string",
                "description": "Start time in 24-hour HH:MM form, e.g. '14:30'.",
            },
            "duration_minutes": {
                "type": "integer",
                "description": "How long the event lasts in minutes. Defaults to 60 when the user did not say.",
            },
            "location": {
                "type": "string",
                "description": "Where the event happens, if the user mentioned it.",
            },
        },
        "required": ["title", "date", "start_time"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Validate the arguments and create the event."""
        title = (kwargs.get("title") or "").strip()
        date = (kwargs.get("date") or "").strip()
        start_time = (kwargs.get("start_time") or "").strip()
        location = (kwargs.get("location") or "").strip() or None

        if not title:
            return {"error": "일정 제목이 비어 있습니다."}
        if not _DATE_RE.match(date):
            return {"error": f"날짜 형식이 잘못되었습니다: {date!r}. YYYY-MM-DD 형식이어야 합니다."}
        if not _TIME_RE.match(start_time):
            return {"error": f"시각 형식이 잘못되었습니다: {start_time!r}. HH:MM 형식이어야 합니다."}

        raw_duration = kwargs.get("duration_minutes", 60)
        try:
            duration = int(raw_duration)
        except (TypeError, ValueError):
            duration = 60
        if not 1 <= duration <= MAX_DURATION_MIN:
            duration = 60

        logger.info("Tool call: calendar_add_event %s %s %s (%dmin)", title, date, start_time, duration)
        try:
            return await asyncio.to_thread(_create, title, date, start_time, duration, location)
        except GoogleAuthError as exc:
            logger.warning("calendar_add_event auth error: %s", exc)
            return {"error": f"구글 계정이 연결되어 있지 않습니다: {exc}"}
        except ValueError as exc:
            return {"error": f"날짜나 시각을 해석하지 못했습니다: {exc}"}
        except Exception as exc:
            logger.exception("calendar_add_event failed")
            return {"error": f"일정을 만들지 못했습니다: {type(exc).__name__}: {exc}"}
