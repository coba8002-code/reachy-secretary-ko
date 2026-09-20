"""One interface over the brains the assistant can use.

Everything streams, and streams *by sentence* rather than by token. The reason
is latency: a spoken reply can start as soon as the first sentence exists, while
the rest is still being written. Waiting for the whole answer before speaking
adds seconds you can hear.

Providers: local (Ollama), openai, anthropic, gemini, grok.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
import netssl  # noqa: E402

TIMEOUT = 120.0
# Sentence enders, Korean and western. The trailing space/quote keeps decimals
# and abbreviations from splitting a sentence in half.
_SENTENCE_END = re.compile(r'(?<=[.!?。！？])\s|(?<=[다요][.!?])\s*')


class LLMError(RuntimeError):
    """Raised with a user-facing message when a brain cannot answer."""


def _post_stream(url: str, payload: dict, headers: dict[str, str]) -> Iterator[bytes]:
    """POST and yield response lines as they arrive."""
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", **headers}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT, context=netssl.context()) as response:
            for line in response:
                yield line
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:300].decode("utf-8", "replace")
        raise LLMError(f"{exc.code}: {detail}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise LLMError(str(exc)) from exc


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


def _anthropic(messages: list[dict], model: str, system: str, key: str) -> Iterator[str]:
    payload = {
        "model": model,
        "max_tokens": 2000,
        "stream": True,
        "messages": messages,
    }
    if system:
        payload["system"] = system

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


def _gemini(messages: list[dict], model: str, system: str, key: str) -> Iterator[str]:
    contents = [
        {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
        for m in messages
    ]
    payload: dict = {"contents": contents}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":streamGenerateContent?alt=sse&key={key}"
    )
    for line in _post_stream(url, payload, {}):
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


def stream_tokens(messages: list[dict], *, system: str = "") -> Iterator[str]:
    """Stream the reply from whichever provider is configured."""
    settings = config.load()
    provider = settings.get("provider", "local")
    model = config.model_for(provider)
    key = config.api_key(provider)

    spec = config.PROVIDERS.get(provider)
    if spec is None:
        raise LLMError(f"알 수 없는 제공자입니다: {provider}")
    if spec["needs_key"] and not key:
        raise LLMError(f"{spec['label']} 의 API 키가 설정되어 있지 않습니다. 관리자에서 입력해 주세요.")

    if provider == "local":
        yield from _ollama(messages, model, system)
    elif provider == "openai":
        yield from _openai_compatible(messages, model, system, "https://api.openai.com/v1", key)
    elif provider == "grok":
        yield from _openai_compatible(messages, model, system, spec["base_url"], key)
    elif provider == "anthropic":
        yield from _anthropic(messages, model, system, key)
    elif provider == "gemini":
        yield from _gemini(messages, model, system, key)
    else:
        raise LLMError(f"지원하지 않는 제공자입니다: {provider}")


def stream_sentences(messages: list[dict], *, system: str = "") -> Iterator[str]:
    """Stream the reply one sentence at a time, so speech can start early."""
    buffer = ""
    for piece in stream_tokens(messages, system=system):
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
