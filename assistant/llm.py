"""One interface over the brains the assistant can use.

Everything streams, and streams *by sentence* rather than by token. The reason
is latency: a spoken reply can start as soon as the first sentence exists, while
the rest is still being written. Waiting for the whole answer before speaking
adds seconds you can hear.

Providers: local (Ollama), openai, anthropic, gemini, grok.
"""

from __future__ import annotations

import http.client
import json
import re
import sys
import threading
import urllib.parse
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
import netssl  # noqa: E402

TIMEOUT = 120.0
# Sentence enders, Korean and western. The trailing space/quote keeps decimals
# and abbreviations from splitting a sentence in half.
_SENTENCE_END = re.compile(r'(?<=[.!?。！？])\s|(?<=[다요][.!?])\s*')

# Roles that are worth waiting for. Chat is not: on this robot, turning the
# model's own deliberation off cut time-to-first-token from 3.7s to 1.4s, and a
# reply that starts late sounds like the robot did not hear you. Judgement runs
# in the background, where two more seconds cost nothing, so it keeps thinking.
THINKING_ROLES = frozenset({"reason"})


class LLMError(RuntimeError):
    """Raised with a user-facing message when a brain cannot answer."""


# One kept-alive connection per origin. A new TLS handshake to the model provider
# costs ~130ms from the robot, which is audible when it happens on every turn.
# Ollama is plain HTTP on localhost, so the scheme has to be honoured.
_Connection = http.client.HTTPConnection | http.client.HTTPSConnection
_connections: dict[str, _Connection] = {}
_connections_lock = threading.Lock()


def _connect(scheme: str, host: str) -> _Connection:
    """Return a connection to the origin, reusing the last one if it is still open."""
    origin = f"{scheme}://{host}"
    with _connections_lock:
        conn = _connections.pop(origin, None)
    if conn is not None:
        return conn
    if scheme == "https":
        return http.client.HTTPSConnection(host, timeout=TIMEOUT, context=netssl.context())
    return http.client.HTTPConnection(host, timeout=TIMEOUT)


def _keep(scheme: str, host: str, conn: _Connection) -> None:
    """Hand a finished connection back for the next turn."""
    origin = f"{scheme}://{host}"
    with _connections_lock:
        old = _connections.get(origin)
        _connections[origin] = conn
    if old is not None and old is not conn:
        old.close()


def _post_stream(url: str, payload: dict, headers: dict[str, str]) -> Iterator[bytes]:
    """POST and yield response lines as they arrive."""
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme or "https"
    host = parts.netloc
    path = parts.path + (f"?{parts.query}" if parts.query else "")
    body = json.dumps(payload).encode()
    sent = {"Content-Type": "application/json", "Content-Length": str(len(body)), **headers}

    # A kept connection can have been closed by the far end while it sat idle.
    # That failure looks identical to a real network error, so try once more on a
    # fresh socket before deciding the provider is unreachable.
    for attempt in (1, 2):
        conn = _connect(scheme, host)
        try:
            conn.request("POST", path, body=body, headers=sent)
            response = conn.getresponse()
        except (http.client.HTTPException, OSError) as exc:
            conn.close()
            if attempt == 1:
                continue
            raise LLMError(str(exc)) from exc
        break

    if response.status >= 400:
        detail = response.read()[:300].decode("utf-8", "replace")
        conn.close()
        raise LLMError(f"{response.status}: {detail}")

    # Only a fully drained response is safe to reuse. Barge-in abandons this
    # generator mid-answer, which leaves unread bytes on the socket - handing
    # that connection to the next turn would corrupt it.
    drained = False
    try:
        for line in response:
            yield line
        drained = True
    except (http.client.HTTPException, OSError) as exc:
        raise LLMError(str(exc)) from exc
    finally:
        if drained:
            _keep(scheme, host, conn)
        else:
            conn.close()


def _ollama(messages: list[dict], model: str, system: str) -> Iterator[str]:
    base = config.PROVIDERS["local"]["base_url"]
    payload = {
        "model": model,
        "messages": ([{"role": "system", "content": system}] if system else []) + messages,
        "stream": True,
    }
    for line in _post_stream(f"{base}/api/chat", payload, {}):
        line = line.strip()
        if not line:
            continue
        try:
            chunk = json.loads(line)
        except json.JSONDecodeError:
            continue
        piece = chunk.get("message", {}).get("content", "")
        if piece:
            yield piece


def _openai_compatible(messages: list[dict], model: str, system: str, base: str, key: str) -> Iterator[str]:
    payload = {
        "model": model,
        "messages": ([{"role": "system", "content": system}] if system else []) + messages,
        "stream": True,
    }
    for line in _post_stream(f"{base}/chat/completions", payload, {"Authorization": f"Bearer {key}"}):
        text = line.decode("utf-8", "replace").strip()
        if not text.startswith("data:"):
            continue
        body = text[5:].strip()
        if body == "[DONE]":
            break
        try:
            chunk = json.loads(body)
        except json.JSONDecodeError:
            continue
        for choice in chunk.get("choices", []):
            piece = choice.get("delta", {}).get("content")
            if piece:
                yield piece


def _anthropic(messages: list[dict], model: str, system: str, key: str, think: bool) -> Iterator[str]:
    payload: dict = {
        "model": model,
        "max_tokens": 2000,
        "stream": True,
        "messages": messages,
    }
    if system:
        payload["system"] = system
    if think:
        # max_tokens has to leave room for the thinking on top of the answer.
        payload["max_tokens"] = 6000
        payload["thinking"] = {"type": "enabled", "budget_tokens": 4000}

    headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    for line in _post_stream("https://api.anthropic.com/v1/messages", payload, headers):
        text = line.decode("utf-8", "replace").strip()
        if not text.startswith("data:"):
            continue
        try:
            event = json.loads(text[5:].strip())
        except json.JSONDecodeError:
            continue
        if event.get("type") == "content_block_delta":
            piece = event.get("delta", {}).get("text")
            if piece:
                yield piece


def _gemini(messages: list[dict], model: str, system: str, key: str, think: bool) -> Iterator[str]:
    contents = [
        {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
        for m in messages
    ]
    payload: dict = {"contents": contents}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    if not think:
        payload["generationConfig"] = {"thinkingConfig": {"thinkingBudget": 0}}

    # The key goes in a header, never in the query string: URLs end up in logs,
    # in exception text, and in anything that reports a failed request.
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        ":streamGenerateContent?alt=sse"
    )
    for line in _post_stream(url, payload, {"x-goog-api-key": key}):
        text = line.decode("utf-8", "replace").strip()
        if not text.startswith("data:"):
            continue
        try:
            event = json.loads(text[5:].strip())
        except json.JSONDecodeError:
            continue
        for cand in event.get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                piece = part.get("text")
                if piece:
                    yield piece


def stream_tokens(messages: list[dict], *, system: str = "", role: str = "chat") -> Iterator[str]:
    """Stream the reply from the provider assigned to this role.

    Roles let one robot use different providers for different jobs - a cheap fast
    model for chat, a stronger one for judgement. An unassigned role falls back
    to the main provider, so a setup that never touched roles keeps working.
    """
    provider = config.provider_for_role(role)
    model = config.model_for(provider)
    key = config.api_key(provider)

    spec = config.PROVIDERS.get(provider)
    if spec is None:
        raise LLMError(f"알 수 없는 제공자입니다: {provider}")
    if spec["needs_key"] and not key:
        raise LLMError(f"{spec['label']} 의 API 키가 설정되어 있지 않습니다. 관리자에서 입력해 주세요.")

    think = role in THINKING_ROLES

    if provider == "local":
        yield from _ollama(messages, model, system)
    elif provider == "openai":
        yield from _openai_compatible(messages, model, system, "https://api.openai.com/v1", key)
    elif provider == "grok":
        yield from _openai_compatible(messages, model, system, spec["base_url"], key)
    elif provider == "anthropic":
        yield from _anthropic(messages, model, system, key, think)
    elif provider == "gemini":
        yield from _gemini(messages, model, system, key, think)
    else:
        raise LLMError(f"지원하지 않는 제공자입니다: {provider}")


def stream_sentences(messages: list[dict], *, system: str = "", role: str = "chat") -> Iterator[str]:
    """Stream the reply one sentence at a time, so speech can start early."""
    buffer = ""
    for piece in stream_tokens(messages, system=system, role=role):
        buffer += piece
        while True:
            match = _SENTENCE_END.search(buffer)
            if not match:
                break
            sentence, buffer = buffer[: match.end()].strip(), buffer[match.end():]
            if sentence:
                yield sentence
    tail = buffer.strip()
    if tail:
        yield tail
