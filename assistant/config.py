"""Settings and API keys for the assistant.

Everything the admin panel writes lands here. Keys are stored on this machine
only, in a file the owner alone can read (0600), and are never logged or sent
anywhere except to the provider they belong to.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(
    os.getenv("REACHY_CONFIG", Path.home() / ".local" / "share" / "reachy-secretary" / "config.json")
)

# Which brains the assistant can use. "local" needs no key and no network.
PROVIDERS: dict[str, dict[str, Any]] = {
    "local": {
        "label": "로컬 (Ollama)",
        "needs_key": False,
        "base_url": "http://localhost:11434",
        "default_model": "qwen2.5:7b",
        "note": "키 없이 완전 로컬. 인터넷과 비용이 들지 않고 대화가 밖으로 나가지 않습니다.",
    },
    "openai": {
        "label": "OpenAI",
        "needs_key": True,
        "key_env": "OPENAI_API_KEY",
        "default_model": "gpt-4o",
        "note": "실시간 음성 모델(gpt-realtime)을 쓸 수 있는 유일한 선택지입니다.",
    },
    "anthropic": {
        "label": "Claude",
        "needs_key": True,
        "key_env": "ANTHROPIC_API_KEY",
        "default_model": "claude-opus-5",
        "note": "판단력이 가장 좋습니다. 다만 실시간 음성 API는 없어 음성 계층은 다른 것을 씁니다.",
    },
    "gemini": {
        "label": "Gemini",
        "needs_key": True,
        "key_env": "GEMINI_API_KEY",
        "default_model": "gemini-2.0-flash",
        "note": "Live API 로 실시간 음성이 가능합니다.",
    },
    "grok": {
        "label": "Grok (xAI)",
        "needs_key": True,
        "key_env": "XAI_API_KEY",
        "base_url": "https://api.x.ai/v1",
        "default_model": "grok-2-latest",
        "note": "OpenAI 호환 API 를 씁니다.",
    },
}

DEFAULTS: dict[str, Any] = {
    "provider": "local",
    "model": "",                    # empty means the provider's default
    "persona": "secretary_ko",
    "voice": "Yuna",
    "language": "ko",
    "output": "robot",              # robot | mac
    "stt_model": "base",            # faster-whisper size
    "wake_word": "",                # empty means always listening
    "vision_enabled": False,
    "owner_name": "",
    "keys": {},                     # provider -> key
}


def _read() -> dict[str, Any]:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load() -> dict[str, Any]:
    """Return the full settings, with defaults filled in."""
    settings = dict(DEFAULTS)
    settings.update(_read())
    settings.setdefault("keys", {})
    return settings


def save(settings: dict[str, Any]) -> None:
    """Write settings, keeping the file readable only by its owner."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        CONFIG_PATH.chmod(0o600)
    except OSError:
        pass


def update(**fields: Any) -> dict[str, Any]:
    """Change some settings and return the result."""
    settings = load()
    settings.update(fields)
    save(settings)
    return settings


def set_key(provider: str, key: str) -> None:
    """Store one provider's API key."""
    settings = load()
    keys = settings.setdefault("keys", {})
    if key:
        keys[provider] = key
    else:
        keys.pop(provider, None)
    save(settings)


def api_key(provider: str) -> str | None:
    """Return a provider's key: the stored one, else its environment variable."""
    stored = load().get("keys", {}).get(provider)
    if stored:
        return stored
    env_name = PROVIDERS.get(provider, {}).get("key_env")
    return os.getenv(env_name) if env_name else None


def model_for(provider: str) -> str:
    """Return the model to use for a provider."""
    settings = load()
    if settings.get("provider") == provider and settings.get("model"):
        return str(settings["model"])
    return str(PROVIDERS.get(provider, {}).get("default_model", ""))


def masked_keys() -> dict[str, str]:
    """Return keys for display: enough to recognise, not enough to use."""
    result: dict[str, str] = {}
    for name in PROVIDERS:
        key = api_key(name)
        if not key:
            result[name] = ""
        elif len(key) <= 10:
            result[name] = "*" * len(key)
        else:
            result[name] = f"{key[:6]}...{key[-4:]}"
    return result


def status() -> list[dict[str, Any]]:
    """Return each provider with whether it is usable right now."""
    settings = load()
    masked = masked_keys()
    rows = []
    for name, spec in PROVIDERS.items():
        has_key = bool(api_key(name))
        rows.append(
            {
                "id": name,
                "label": spec["label"],
                "needs_key": spec["needs_key"],
                "ready": (not spec["needs_key"]) or has_key,
                "masked_key": masked[name],
                "model": model_for(name),
                "note": spec["note"],
                "selected": settings.get("provider") == name,
            }
        )
    return rows
