"""One interface over the brains the assistant can use.

Everything streams, and streams *by sentence* rather than by token. The reason
is latency: a spoken reply can start as soon as the first sentence exists, while
the rest is still being written. Waiting for the whole answer before speaking
adds seconds you can hear.

Providers: local (Ollama), openai, anthropic, gemini, grok.
"""

from __future__ import annotations

import base64
import http.client
import json
import re
import sys
import threading
import urllib.parse
from collections.abc import Iterator
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
import netssl  # noqa: E402

# Reaching the provider at all should be quick - the robot is on wifi, and the
# handshake measured 140ms. Five seconds means something is actually wrong.
CONNECT_TIMEOUT = 5.0

# How long to wait for the next byte once the request is in. This is a gap
# timeout, not a total: it only fires when nothing at all arrives. Chat gets a
# short one because a silent robot reads as broken - better to say "잠시
# 문제가 있어요" at fifteen seconds than to stand there for two minutes.
# Judgement runs in the background where a long pause costs nothing.
READ_TIMEOUT = 90.0
READ_TIMEOUT_CHAT = 15.0

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


def _reason(exc: BaseException) -> str:
    """Turn a socket failure into something worth saying out loud."""
    if isinstance(exc, TimeoutError):
        return "응답이 제때 오지 않았습니다"
    if isinstance(exc, ConnectionRefusedError):
        return "연결이 거부되었습니다"
    if isinstance(exc, OSError) and exc.errno is not None:
        return f"연결에 실패했습니다: {exc.strerror or exc}"
    return str(exc) or exc.__class__.__name__


# One kept-alive connection per origin. A new TLS handshake to the model provider
# costs ~130ms from the robot, which is audible when it happens on every turn.
# Ollama is plain HTTP on localhost, so the scheme has to be honoured.
_Connection = http.client.HTTPConnection | http.client.HTTPSConnection
_connections: dict[str, _Connection] = {}
_connections_lock = threading.Lock()


def _connect(scheme: str, host: str) -> tuple[_Connection, bool]:
    """Return a connection to the origin, and whether it came from the pool."""
    origin = f"{scheme}://{host}"
    with _connections_lock:
        conn = _connections.pop(origin, None)
    if conn is not None:
        return conn, True
    if scheme == "https":
        return http.client.HTTPSConnection(host, timeout=CONNECT_TIMEOUT, context=netssl.context()), False
    return http.client.HTTPConnection(host, timeout=CONNECT_TIMEOUT), False


def _keep(scheme: str, host: str, conn: _Connection) -> None:
    """Hand a finished connection back for the next turn."""
    origin = f"{scheme}://{host}"
    with _connections_lock:
        old = _connections.get(origin)
        _connections[origin] = conn
    if old is not None and old is not conn:
        old.close()


def _post_stream(
    url: str, payload: dict, headers: dict[str, str], read_timeout: float = READ_TIMEOUT
) -> Iterator[bytes]:
    """POST and yield response lines as they arrive."""
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme or "https"
    host = parts.netloc
    path = parts.path + (f"?{parts.query}" if parts.query else "")
    body = json.dumps(payload).encode()
    sent = {"Content-Type": "application/json", "Content-Length": str(len(body)), **headers}

    # A kept connection can have been closed by the far end while it sat idle.
    # That failure looks identical to a real network error, so retry once on a
    # fresh socket - but only when the connection was a reused one. Retrying a
    # brand new connection just makes the user wait for the same failure twice.
    for attempt in (1, 2):
        conn, reused = _connect(scheme, host)
        try:
            conn.request("POST", path, body=body, headers=sent)
            if conn.sock is not None:
                conn.sock.settimeout(read_timeout)
            response = conn.getresponse()
        except (http.client.HTTPException, OSError) as exc:
            conn.close()
            if attempt == 1 and reused:
                continue
            raise LLMError(_reason(exc)) from exc
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
        raise LLMError(_reason(exc)) from exc
    finally:
        if drained:
            _keep(scheme, host, conn)
        else:
            conn.close()


def _ollama(
    messages: list[dict], model: str, system: str, read_timeout: float, schema: dict | None = None
) -> Iterator[dict]:
    base = config.PROVIDERS["local"]["base_url"]
    payload: dict = {
        "model": model,
        "messages": ([{"role": "system", "content": system}] if system else []) + messages,
        "stream": True,
    }
    if schema is not None:
        payload["format"] = schema
    for line in _post_stream(f"{base}/api/chat", payload, {}, read_timeout):
        line = line.strip()
        if not line:
            continue
        try:
            chunk = json.loads(line)
        except json.JSONDecodeError:
            continue
        piece = chunk.get("message", {}).get("content", "")
        if piece:
            yield {"text": piece}


def _openai_compatible(
    messages: list[dict], model: str, system: str, base: str, key: str, read_timeout: float,
    schema: dict | None = None,
) -> Iterator[dict]:
    payload: dict = {
        "model": model,
        "messages": ([{"role": "system", "content": system}] if system else []) + messages,
        "stream": True,
    }
    if schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "result", "schema": schema, "strict": True},
        }
    for line in _post_stream(
        f"{base}/chat/completions", payload, {"Authorization": f"Bearer {key}"}, read_timeout
    ):
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
                yield {"text": piece}


def _anthropic(
    messages: list[dict], model: str, system: str, key: str, think: bool, read_timeout: float
) -> Iterator[dict]:
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
    for line in _post_stream("https://api.anthropic.com/v1/messages", payload, headers, read_timeout):
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
                yield {"text": piece}


# Gemini accepts a subset of JSON Schema and rejects the request outright when it
# meets a keyword it does not know, so anything it cannot read is dropped.
_GEMINI_SCHEMA_KEYS = frozenset({
    "type", "format", "description", "nullable", "enum",
    "items", "properties", "required", "maxItems", "minItems",
})


def _gemini_schema(node: Any) -> Any:
    """Strip a JSON Schema down to what Gemini will accept."""
    if isinstance(node, list):
        return [_gemini_schema(v) for v in node]
    if not isinstance(node, dict):
        return node
    out = {}
    for key, value in node.items():
        if key not in _GEMINI_SCHEMA_KEYS:
            continue
        if key == "properties" and isinstance(value, dict):
            out[key] = {k: _gemini_schema(v) for k, v in value.items()}
        elif key == "items":
            out[key] = _gemini_schema(value)
        else:
            out[key] = value
    return out


def _gemini(
    messages: list[dict], model: str, system: str, key: str, think: bool, read_timeout: float,
    schema: dict | None = None,
    tools: list[dict] | None = None,
) -> Iterator[dict]:
    # A message normally carries plain text, but a tool round trip needs richer
    # parts - the model's functionCall and our functionResponse, or an image the
    # robot just took - so a caller may supply "parts" directly instead.
    contents = [
        {
            "role": "model" if m["role"] == "assistant" else "user",
            "parts": m["parts"] if "parts" in m else [{"text": m["content"]}],
        }
        for m in messages
    ]
    payload: dict = {"contents": contents}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}

    generation: dict = {}
    if not think:
        generation["thinkingConfig"] = {"thinkingBudget": 0}
    if schema is not None:
        generation["responseMimeType"] = "application/json"
        generation["responseSchema"] = _gemini_schema(schema)
    if generation:
        payload["generationConfig"] = generation
    if tools:
        payload["tools"] = [{"functionDeclarations": tools}]

    # The key goes in a header, never in the query string: URLs end up in logs,
    # in exception text, and in anything that reports a failed request.
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        ":streamGenerateContent?alt=sse"
    )
    for line in _post_stream(url, payload, {"x-goog-api-key": key}, read_timeout):
        text = line.decode("utf-8", "replace").strip()
        if not text.startswith("data:"):
            continue
        try:
            event = json.loads(text[5:].strip())
        except json.JSONDecodeError:
            continue
        for cand in event.get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                if part.get("text"):
                    yield {"text": part["text"]}
                call = part.get("functionCall")
                if call:
                    # Gemini 3 signs each call and rejects the follow-up turn if
                    # the signature does not come back with it, so carry it along
                    # rather than reconstructing the part from name and args.
                    yield {"tool_call": {
                        "name": call.get("name", ""),
                        "args": call.get("args") or {},
                        "signature": part.get("thoughtSignature"),
                    }}


def stream_events(
    messages: list[dict], *, system: str = "", role: str = "chat",
    schema: dict | None = None, tools: list[dict] | None = None,
) -> Iterator[dict]:
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
    read_timeout = READ_TIMEOUT_CHAT if role == "chat" else READ_TIMEOUT

    if tools and provider != "gemini":
        # Better to say so than to drop the tools and let the robot explain why
        # it cannot dance while the tool sat there unused.
        raise LLMError(f"{spec['label']} 에는 아직 도구 호출이 연결되어 있지 않습니다.")

    if provider == "local":
        yield from _ollama(messages, model, system, read_timeout, schema)
    elif provider == "openai":
        yield from _openai_compatible(
            messages, model, system, "https://api.openai.com/v1", key, read_timeout, schema
        )
    elif provider == "grok":
        yield from _openai_compatible(
            messages, model, system, spec["base_url"], key, read_timeout, schema
        )
    elif provider == "anthropic":
        yield from _anthropic(messages, model, system, key, think, read_timeout)
    elif provider == "gemini":
        yield from _gemini(messages, model, system, key, think, read_timeout, schema, tools)
    else:
        raise LLMError(f"지원하지 않는 제공자입니다: {provider}")


def stream_tokens(
    messages: list[dict], *, system: str = "", role: str = "chat", schema: dict | None = None
) -> Iterator[str]:
    """Stream just the words, for callers that have no tools to run."""
    for event in stream_events(messages, system=system, role=role, schema=schema):
        if "text" in event:
            yield event["text"]


def image_part(jpeg: bytes) -> dict:
    """Wrap a JPEG so it can be put in a message's parts."""
    return {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(jpeg).decode()}}


def take_sentence(buffer: str) -> tuple[str, str]:
    """Split off the first complete sentence. Returns (sentence, rest)."""
    match = _SENTENCE_END.search(buffer)
    if not match:
        return "", buffer
    return buffer[: match.end()].strip(), buffer[match.end() :]


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
