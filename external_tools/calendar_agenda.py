"""Read upcoming Google Calendar events."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import os
import sys
from pathlib import Path
from typing import Any

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _secretary_lib.google_auth import GoogleAuthError, build_service  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_TZ = os.getenv("REACHY_SECRETARY_TZ", "Asia/Seoul")
MAX_EVENTS = 20


def _tzinfo() -> dt.tzinfo:
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(DEFAULT_TZ)
    except Exception:
        logger.warning("Unknown timezone %s, falling back to UTC", DEFAULT_TZ)
        return dt.timezone.utc


def _window(span: str) -> tuple[dt.datetime, dt.datetime]:
    """Return the (start, end) datetimes for a named span, in local time."""
    tz = _tzinfo()
    now = dt.datetime.now(tz)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if span == "tomorrow":
        start = midnight + dt.timedelta(days=1)
        return start, start + dt.timedelta(days=1)
    if span == "week":
        return now, midnight + dt.timedelta(days=8)
    # "today" spans from right now to end of day: past events are not useful
    # to read aloud, but an event happening right now still is.
    return now, midnight + dt.timedelta(days=1)


def _format_event(event: dict[str, Any], tz: dt.tzinfo) -> dict[str, Any]:
    """Reduce a Calendar API event to the few fields worth speaking."""
    start = event.get("start", {})
    end = event.get("end", {})

    if "date" in start:
        return {
            "title": event.get("summary", "(제목 없음)"),
            "all_day": True,
            "date": start["date"],
            "location": event.get("location"),
        }

    start_dt = dt.datetime.fromisoformat(start["dateTime"]).astimezone(tz)
    end_dt = dt.datetime.fromisoformat(end["dateTime"]).astimezone(tz) if "dateTime" in end else None

    return {
        "title": event.get("summary", "(제목 없음)"),
        "all_day": False,
        "date": start_dt.strftime("%Y-%m-%d"),
        "start": start_dt.strftime("%H:%M"),
        "end": end_dt.strftime("%H:%M") if end_dt else None,
        "location": event.get("location"),
    }


def _fetch(span: str) -> dict[str, Any]:
    """Blocking Calendar read. Call via asyncio.to_thread."""
    tz = _tzinfo()
    start, end = _window(span)

    service = build_service("calendar", "v3")
    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=MAX_EVENTS,
        )
        .execute()
    )

    events = [_format_event(item, tz) for item in result.get("items", [])]
    return {
        "span": span,
        "timezone": DEFAULT_TZ,
        "now": dt.datetime.now(tz).strftime("%Y-%m-%d %H:%M"),
        "count": len(events),
        "events": events,
    }


class CalendarAgenda(Tool):
    """Read the user's upcoming calendar events."""

    name = "calendar_agenda"
    description = (
        "Read the user's Google Calendar. Use this whenever the user asks what is on their schedule, "
        "whether they are free, or what is coming up - never answer from memory. "
        "Returns structured events; phrase them conversationally and skip empty fields."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "span": {
                "type": "string",
                "enum": ["today", "tomorrow", "week"],
                "description": (
                    "Which window to read. 'today' covers from now until midnight, "
                    "'tomorrow' the whole next day, 'week' the next seven days."
                ),
            },
        },
        "required": ["span"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Return the events in the requested window."""
        span = kwargs.get("span", "today")
        if span not in ("today", "tomorrow", "week"):
            span = "today"

        logger.info("Tool call: calendar_agenda span=%s", span)
        try:
            # The Google client is synchronous; keep it off the event loop so the
            # conversation stays responsive while the request is in flight.
            return await asyncio.to_thread(_fetch, span)
        except GoogleAuthError as exc:
            logger.warning("calendar_agenda auth error: %s", exc)
            return {"error": f"구글 계정이 연결되어 있지 않습니다: {exc}"}
        except Exception as exc:
            logger.exception("calendar_agenda failed")
            return {"error": f"캘린더를 읽지 못했습니다: {type(exc).__name__}: {exc}"}
