"""Create a Gmail draft, with the body written by the judgement model. Never sends it.

The draft lands in the user's Drafts folder and stays there. Sending is a
deliberate human action taken in a mail client - a spoken sentence is too thin a
gate for something irreversible. This module calls only the Gmail draft-create
endpoint, never the send or delete endpoints.

Why a second model writes the body: the realtime voice backend is tuned for short
spoken turns, and relaying a paragraph of prose verbatim through a tool argument
is exactly what it is worst at. The robot passes a one-line brief instead, and
the prose is composed here by whichever model holds the "깊은 판단" role.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import sys
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _secretary_lib.reason import ReasonError, complete  # noqa: E402
from _secretary_lib.google_auth import GoogleAuthError, build_service  # noqa: E402

logger = logging.getLogger(__name__)

MAX_RECIPIENTS = 10
MAX_BODY_CHARS = 20000
MAX_QUOTED_CHARS = 4000
COMPOSE_MAX_TOKENS = 4000
_ADDRESS_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

COMPOSE_SYSTEM = """\
당신은 개인 비서가 사용자를 대신해 보낼 이메일의 초안을 씁니다.
당신이 쓴 글은 사용자가 검토한 뒤 **사용자 본인 이름으로** 나갑니다.

- 사용자가 쓰는 언어로 씁니다. 지시가 한국어면 한국어로 씁니다.
- **말투는 받는 사람에 맞춥니다.** 답장이라면 원본 메일의 격식을 그대로 따라가세요.
  원본이 "안녕하세요, ~드립니다"면 같은 높이로, 편한 사이면 편하게 씁니다.
- 마크다운을 쓰지 마세요. 별표, 해시, 하이픈 목록 금지입니다. 실제 줄바꿈만 씁니다.
- **짧게.** 용건이 분명한 메일은 세 문단을 넘기지 않습니다.
- **없는 사실을 만들지 마세요.** 지시에 없는 날짜, 금액, 약속, 첨부파일을 지어내면 안 됩니다.
  꼭 필요한 정보가 비어 있으면 `[확인 필요]`처럼 눈에 띄는 표시를 남기세요.
  사용자가 초안을 검토할 때 그 자리를 채울 수 있어야 합니다.
- 서명을 붙이지 마세요. 사용자가 직접 요청한 경우에만 넣습니다.
- 사용자를 대신해 새로운 약속을 하지 마세요. 지시받은 내용만 전합니다.

제목 규칙:
- 새 메일이면 내용에 맞는 제목을 짓습니다. 짧고 구체적으로.
- 답장이면 제목은 빈 문자열로 두세요. 원본 제목이 자동으로 사용됩니다.\
"""

COMPOSE_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {
            "type": "string",
            "description": "Subject line for a new email, or an empty string when this is a reply.",
        },
        "body": {
            "type": "string",
            "description": "The full plain-text email body, with real line breaks and no markdown.",
        },
    },
    "required": ["subject", "body"],
    "additionalProperties": False,
}


def _valid_addresses(values: Any) -> tuple[list[str], list[str]]:
    """Split incoming recipients into valid addresses and rejects."""
    if isinstance(values, str):
        values = [part for part in re.split(r"[,;]", values)]
    if not isinstance(values, list):
        return [], []

    good: list[str] = []
    bad: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        _, address = parseaddr(value.strip())
        if address and _ADDRESS_RE.match(address):
            good.append(address)
        elif value.strip():
            bad.append(value.strip())
    return good[:MAX_RECIPIENTS], bad


def _header(payload: dict[str, Any], name: str) -> str | None:
    """Pull one header value out of a message payload."""
    for item in payload.get("headers", []):
        if item.get("name", "").lower() == name.lower():
            return item.get("value")
    return None


def _plain_text(payload: dict[str, Any]) -> str:
    """Walk a MIME tree and return the first text/plain part, decoded."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data")
        if data:
            try:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            except (ValueError, TypeError):
                return ""

    for part in payload.get("parts", []):
        text = _plain_text(part)
        if text:
            return text
    return ""


def _fetch_original(message_id: str) -> dict[str, Any]:
    """Blocking read of the message being replied to, body included."""
    service = build_service("gmail", "v1")
    original = service.users().messages().get(userId="me", id=message_id, format="full").execute()

    payload = original.get("payload", {})
    text = _plain_text(payload) or original.get("snippet", "")

    return {
        "thread_id": original.get("threadId"),
        "rfc_message_id": _header(payload, "Message-ID"),
        "subject": _header(payload, "Subject"),
        "from": _header(payload, "From"),
        "references": _header(payload, "References"),
        "text": text[:MAX_QUOTED_CHARS],
    }


async def _compose(brief: str, target: dict[str, Any] | None, to: list[str]) -> dict[str, str]:
    """Ask the judgement model to write the subject and body.

    Raises:
        ReasonError: if it cannot produce a usable draft.

    """
    parts: list[str] = []

    if target:
        parts.append(
            "다음 메일에 대한 답장을 씁니다.\n"
            f"보낸사람: {target.get('from') or '(알 수 없음)'}\n"
            f"제목: {target.get('subject') or '(제목 없음)'}\n"
            f"본문:\n{target.get('text') or '(본문 없음)'}"
        )
    else:
        parts.append(f"받는 사람: {', '.join(to) if to else '(미정)'}\n이 사람에게 보낼 새 메일을 씁니다.")

    parts.append(f"사용자의 지시:\n{brief}")

    result = await complete(
        system=COMPOSE_SYSTEM,
        prompt="\n\n".join(parts),
        max_tokens=COMPOSE_MAX_TOKENS,
        effort="medium",
        json_schema=COMPOSE_SCHEMA,
    )

    if not isinstance(result, dict):
        raise ReasonError("작성 모델이 예상과 다른 형식을 반환했습니다.")

    body = str(result.get("body", "")).strip()
    if not body:
        raise ReasonError("작성 모델이 빈 본문을 반환했습니다.")

    return {"subject": str(result.get("subject", "")).strip(), "body": body}


def _save_draft(
    to: list[str],
    subject: str,
    body: str,
    cc: list[str],
    target: dict[str, Any] | None,
) -> dict[str, Any]:
    """Blocking Gmail draft creation. Call via asyncio.to_thread."""
    if not subject:
        subject = "(제목 없음)"
    if target and not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    message = EmailMessage()
    message["To"] = ", ".join(to)
    if cc:
        message["Cc"] = ", ".join(cc)
    message["Subject"] = subject
    message.set_content(body)

    # Threading headers are what make Gmail show the draft inside the original
    # conversation rather than as a new one. References keeps the whole chain.
    if target and target.get("rfc_message_id"):
        rfc_id = target["rfc_message_id"]
        message["In-Reply-To"] = rfc_id
        existing = target.get("references")
        message["References"] = f"{existing} {rfc_id}".strip() if existing else rfc_id

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    draft_body: dict[str, Any] = {"message": {"raw": raw}}
    if target and target.get("thread_id"):
        draft_body["message"]["threadId"] = target["thread_id"]

    service = build_service("gmail", "v1")
    created = service.users().drafts().create(userId="me", body=draft_body).execute()

    return {
        "created": True,
        "draft_id": created.get("id"),
        "to": to,
        "cc": cc,
        "subject": subject,
        "body": body,
        "is_reply": bool(target),
        "note": "Saved to Drafts. It has NOT been sent - the user must send it themselves.",
    }


class GmailDraft(Tool):
    """Write a Gmail draft for the user to review and send."""

    name = "gmail_draft"
    description = (
        "Write an email and save it as a draft in the user's Gmail. "
        "Use this when they ask you to write, reply to, or prepare an email. "
        "Normally pass 'brief' - one line saying what the email needs to say, in the user's own words. "
        "A stronger writing model composes the actual prose, so do NOT write the email yourself and do NOT "
        "ask the user to dictate it. Only use 'body' when the user explicitly dictated the exact wording "
        "they want sent. "
        "To reply to something from gmail_digest, pass that message's 'message_id' as 'reply_to_message_id' "
        "and leave 'to' and 'subject' empty - they come from the original, and the reply is written with the "
        "original in view. "
        "If the user names a person but you have no address for them, ask for it rather than guessing. "
        "It takes several seconds, so say one short line like '초안 써볼게' first. "
        "IMPORTANT: this only saves a draft - you cannot send mail. Afterwards tell the user in one sentence "
        "who it is to and roughly what it says, and that it is waiting in their drafts. Do not read the whole "
        "body aloud unless they ask. If the body contains '[확인 필요]', tell them which part needs filling in."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "brief": {
                "type": "string",
                "description": (
                    "What the email needs to say, in one or two lines - the user's intent, not finished prose. "
                    "Include any specifics they gave: dates, times, names, reasons. "
                    "Example: '내일 오후 회의를 다음 주 화요일로 미루자고, 일정이 겹쳐서 그렇다고 설명'."
                ),
            },
            "body": {
                "type": "string",
                "description": (
                    "The exact body text, used verbatim. Only for when the user dictated the wording "
                    "themselves. Leave this empty and use 'brief' in every other case."
                ),
            },
            "to": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Recipient email addresses. Leave empty only when replying via 'reply_to_message_id'."
                ),
            },
            "subject": {
                "type": "string",
                "description": (
                    "Only set this if the user dictated a specific subject. Otherwise leave it empty - "
                    "it is written for you, or taken from the original when replying."
                ),
            },
            "cc": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional CC addresses.",
            },
            "reply_to_message_id": {
                "type": "string",
                "description": (
                    "The 'message_id' of a message from gmail_digest, when this draft is a reply to it. "
                    "Threads the draft onto that conversation and lets the writer read the original."
                ),
            },
        },
        "required": [],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Compose the draft if needed, then save it."""
        brief = (kwargs.get("brief") or "").strip()
        dictated = (kwargs.get("body") or "").strip()

        if not brief and not dictated:
            return {"error": "메일에 무슨 내용을 담을지 알려주세요."}
        if len(dictated) > MAX_BODY_CHARS:
            return {"error": f"본문이 너무 깁니다 ({len(dictated)}자). {MAX_BODY_CHARS}자 이내로 줄여 주세요."}

        reply_to = (kwargs.get("reply_to_message_id") or "").strip() or None
        to, bad_to = _valid_addresses(kwargs.get("to"))
        cc, bad_cc = _valid_addresses(kwargs.get("cc"))

        rejected = bad_to + bad_cc
        if rejected:
            return {"error": f"이메일 주소 형식이 아닙니다: {', '.join(rejected)}. 정확한 주소를 알려주세요."}
        if not to and not reply_to:
            return {"error": "받는 사람이 없습니다. 이메일 주소를 알려주세요."}

        subject = (kwargs.get("subject") or "").strip()

        logger.info(
            "Tool call: gmail_draft to=%s reply_to=%s mode=%s",
            to or "(from original)",
            reply_to,
            "dictated" if dictated else "composed",
        )

        target: dict[str, Any] | None = None
        try:
            if reply_to:
                # The Google client is synchronous; keep it off the event loop.
                target = await asyncio.to_thread(_fetch_original, reply_to)

                if not to and target.get("from"):
                    _, address = parseaddr(target["from"])
                    if address:
                        to = [address]
                if not subject and target.get("subject"):
                    subject = target["subject"]

            if not to:
                return {"error": "답장할 원본 메일에서 보낸사람 주소를 찾지 못했습니다."}

            body = dictated
            if not body:
                written = await _compose(brief, target, to)
                body = written["body"]
                if not subject:
                    subject = written["subject"]

            return await asyncio.to_thread(_save_draft, to, subject, body, cc, target)

        except ReasonError as exc:
            return {"error": f"본문을 작성하지 못했습니다: {exc}"}
        except GoogleAuthError as exc:
            logger.warning("gmail_draft auth error: %s", exc)
            return {"error": f"구글 계정이 연결되어 있지 않습니다: {exc}"}
        except Exception as exc:
            logger.exception("gmail_draft failed")
            return {"error": f"초안을 저장하지 못했습니다: {type(exc).__name__}: {exc}"}
