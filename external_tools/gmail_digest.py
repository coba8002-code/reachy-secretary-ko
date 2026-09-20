"""Summarize recent Gmail messages. Read-only by design."""

from __future__ import annotations

import asyncio
import logging
import sys
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _secretary_lib.google_auth import GoogleAuthError, build_service  # noqa: E402

logger = logging.getLogger(__name__)

MAX_MESSAGES = 25
DEFAULT_MESSAGES = 12

# Gmail's own tab classification. Mail carrying these is almost never what the
# user means by "did anything important come in".
_BULK_LABELS = {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_UPDATES", "CATEGORY_FORUMS"}

_SCOPE_QUERIES = {
    "unread": "is:unread in:inbox",
    "today": "newer_than:1d in:inbox",
    "important": "is:important is:unread in:inbox",
}


def _header(payload: dict[str, Any], name: str) -> str | None:
    """Pull one header value out of a metadata-format message payload."""
    for item in payload.get("headers", []):
        if item.get("name", "").lower() == name.lower():
            return item.get("value")
    return None


def _clean_sender(raw: str | None) -> str:
    """Reduce 'Jane Doe <jane@x.com>' to 'Jane Doe' - the address is noise aloud."""
    if not raw:
        return "(보낸사람 없음)"
    name = raw.split("<")[0].strip().strip('"')
    return name or raw.strip()


def _sender_address(raw: str | None) -> str | None:
    """Pull the bare address out of a From header, for gmail_draft to reply to."""
    if not raw:
        return None
    _, address = parseaddr(raw)
    return address or None


def _fetch(scope: str, limit: int) -> dict[str, Any]:
    """Blocking Gmail read. Call via asyncio.to_thread."""
    service = build_service("gmail", "v1")
    query = _SCOPE_QUERIES.get(scope, _SCOPE_QUERIES["unread"])

    listing = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=limit)
        .execute()
    )
    ids = [item["id"] for item in listing.get("messages", [])]

    personal: list[dict[str, Any]] = []
    bulk_count = 0

    for message_id in ids:
        message = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            )
            .execute()
        )

        labels = set(message.get("labelIds", []))
        if labels & _BULK_LABELS:
            bulk_count += 1
            continue

        payload = message.get("payload", {})
        raw_from = _header(payload, "From")
        personal.append(
            {
                "from": _clean_sender(raw_from),
                "from_address": _sender_address(raw_from),
                "subject": _header(payload, "Subject") or "(제목 없음)",
                "snippet": message.get("snippet", "")[:200],
                "message_id": message.get("id"),
                "thread_id": message.get("threadId"),
            }
        )

    return {
        "scope": scope,
        "personal_count": len(personal),
        "bulk_count": bulk_count,
        "messages": personal,
        "note": "Read-only digest. This assistant cannot send, reply to, or delete mail.",
    }


class GmailDigest(Tool):
    """Read a short digest of recent inbox mail."""

    name = "gmail_digest"
    description = (
        "Read a digest of the user's recent Gmail. Use this when they ask what mail arrived, "
        "whether anything important came in, or to catch up on the inbox. "
        "Promotional and notification mail is counted separately as 'bulk_count' - mention it as one "
        "throwaway clause, never read those out. Summarize each personal message as sender plus what "
        "they want, in one clause each. "
        "Never read 'from_address', 'message_id' or 'thread_id' aloud - they exist so you can pass "
        "'message_id' to gmail_draft when the user asks you to reply to one of these. "
        "This tool only reads mail; it cannot send or delete anything."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "enum": ["unread", "today", "important"],
                "description": (
                    "'unread' for everything unread in the inbox, 'today' for the last 24 hours, "
                    "'important' for unread mail Gmail flagged as important."
                ),
            },
            "limit": {
                "type": "integer",
                "description": f"How many messages to scan, 1-{MAX_MESSAGES}. Defaults to {DEFAULT_MESSAGES}.",
            },
        },
        "required": ["scope"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Return the digest for the requested scope."""
        scope = kwargs.get("scope", "unread")
        if scope not in _SCOPE_QUERIES:
            scope = "unread"

        try:
            limit = int(kwargs.get("limit", DEFAULT_MESSAGES))
        except (TypeError, ValueError):
            limit = DEFAULT_MESSAGES
        limit = max(1, min(limit, MAX_MESSAGES))

        logger.info("Tool call: gmail_digest scope=%s limit=%d", scope, limit)
        try:
            return await asyncio.to_thread(_fetch, scope, limit)
        except GoogleAuthError as exc:
            logger.warning("gmail_digest auth error: %s", exc)
            return {"error": f"구글 계정이 연결되어 있지 않습니다: {exc}"}
        except Exception as exc:
            logger.exception("gmail_digest failed")
            return {"error": f"메일을 읽지 못했습니다: {type(exc).__name__}: {exc}"}
