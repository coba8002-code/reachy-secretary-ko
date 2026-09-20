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
        "default_model": "gemini-3.6-flash",
        "note": "Live API 로 실시간 음성이 가능합니다.",
        # 모델명은 구글이 예고 없이 내린다. 404 가 나면 관리자 화면에서
        # 모델을 바꾸거나 https://ai.google.dev/gemini-api/docs/models 확인.
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

# What each provider is used for. Keeping them separate is the point of
# holding several keys: the model that is best at holding a conversation is not
# the one that is best at thinking through a hard problem, and neither of them
# transcribes Korean speech.
ROLES: dict[str, dict[str, str]] = {
    "chat": {
        "label": "대화",
        "note": "말을 주고받는 쪽. 지연이 품질을 좌우합니다.",
    },
    "reason": {
        "label": "깊은 판단",
        "note": "여러 단계를 따져야 하는 질문. 느려도 정확한 쪽이 낫습니다.",
    },
    "stt": {
        "label": "음성 인식",
        "note": "한국어 받아쓰기.",
    },
}

DEFAULTS: dict[str, Any] = {
    "provider": "local",
    "model": "",                    # empty means the provider's default
    # role -> provider id. Empty falls back to "provider".
    "roles": {},
    # provider id -> model override, set from the admin panel. Providers retire
    # model names without warning (gemini-2.0-flash vanished mid-build), and
    # re-deploying code to fix a string is the wrong shape of fix.
    "models": {},
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
    override = (settings.get("models") or {}).get(provider)
    if override:
        return str(override)
    if settings.get("provider") == provider and settings.get("model"):
        return str(settings["model"])
    return str(PROVIDERS.get(provider, {}).get("default_model", ""))


def set_model(provider: str, model: str) -> None:
    """Pin a provider to a specific model, or clear the override."""
    settings = load()
    models = settings.setdefault("models", {})
    if model:
        models[provider] = model
    else:
        models.pop(provider, None)
    save(settings)


def provider_for_role(role: str) -> str:
    """Return the provider assigned to a role, falling back to the main one."""
    settings = load()
    assigned = (settings.get("roles") or {}).get(role)
    if assigned and assigned in PROVIDERS:
        return str(assigned)
    return str(settings.get("provider", "local"))


def set_role(role: str, provider: str) -> None:
    """Assign a provider to a role, or clear the assignment."""
    if role not in ROLES:
        return
    settings = load()
    roles = settings.setdefault("roles", {})
    if provider and provider in PROVIDERS:
        roles[role] = provider
    else:
        roles.pop(role, None)
    save(settings)


def role_status() -> list[dict[str, Any]]:
    """Return each role with the provider currently serving it."""
    settings = load()
    rows = []
    for role, spec in ROLES.items():
        assigned = (settings.get("roles") or {}).get(role, "")
        effective = provider_for_role(role)
        rows.append({
            "id": role,
            "label": spec["label"],
            "note": spec["note"],
            "assigned": assigned,
            "effective": effective,
            "effective_label": PROVIDERS.get(effective, {}).get("label", effective),
            "ready": (not PROVIDERS.get(effective, {}).get("needs_key")) or bool(api_key(effective)),
        })
    return rows


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
