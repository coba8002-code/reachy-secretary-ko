#!/usr/bin/env python3
"""Admin panel for the Reachy secretary.

    python3 admin/server.py          # then open http://localhost:8765

Runs on the standard library alone, because it has to start on the robot as
well as on a laptop and adding a web framework to a Raspberry Pi image for one
settings page is not worth it.

API keys are typed here, never into a chat window or a shell history. They are
written to a 0600 file and only ever sent to the provider they belong to. The
page shows keys masked; the full value is never returned by the API.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "assistant"))
sys.path.insert(0, str(ROOT.parent / "jarvis"))

import config  # noqa: E402
import netssl  # noqa: E402
import robot  # noqa: E402

PORT = int(os.getenv("REACHY_ADMIN_PORT", "8765"))
# On the robot this must be reachable from a browser on another machine, so it
# binds every interface there. The default stays loopback-only: this page holds
# API keys, and it has no login.
HOST = os.getenv("REACHY_ADMIN_HOST", "127.0.0.1")


def audio_levels() -> dict:
    """Return speaker and mic levels, or why they could not be read.

    The daemon is a separate service that can be down while this page is up, so
    a failure here has to be shown rather than crashing the settings request.
    """
    try:
        return {"speaker": robot.volume(), "microphone": robot.mic_volume(), "available": True}
    except robot.RobotError as exc:
        return {"speaker": None, "microphone": None, "available": False, "detail": str(exc)}


def check_provider(provider: str) -> dict:
    """Make one cheap call to see whether a provider actually answers."""
    key = config.api_key(provider)
    spec = config.PROVIDERS.get(provider)
    if spec is None:
        return {"ok": False, "detail": "알 수 없는 제공자"}
    if spec["needs_key"] and not key:
        return {"ok": False, "detail": "키가 없습니다"}

    model = config.model_for(provider)
    try:
        if provider == "local":
            url = f"{spec['base_url']}/api/tags"
            with urllib.request.urlopen(url, timeout=6, context=netssl.context()) as response:
                names = [m["name"] for m in json.loads(response.read()).get("models", [])]
            if model not in names:
                return {"ok": False, "detail": f"모델 {model} 이 없습니다. 받은 모델: {', '.join(names[:4])}"}
            return {"ok": True, "detail": f"Ollama 정상 · 모델 {len(names)}개"}

        if provider == "anthropic":
            payload = {"model": model, "max_tokens": 16, "messages": [{"role": "user", "content": "ping"}]}
            request = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps(payload).encode(),
                headers={
                    "content-type": "application/json",
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                },
                method="POST",
            )
        elif provider in ("openai", "grok"):
            base = spec.get("base_url", "https://api.openai.com/v1")
            payload = {"model": model, "max_tokens": 16, "messages": [{"role": "user", "content": "ping"}]}
            request = urllib.request.Request(
                f"{base}/chat/completions",
                data=json.dumps(payload).encode(),
                headers={"content-type": "application/json", "authorization": f"Bearer {key}"},
                method="POST",
            )
        elif provider == "gemini":
            payload = {"contents": [{"role": "user", "parts": [{"text": "ping"}]}]}
            request = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                data=json.dumps(payload).encode(),
                headers={"content-type": "application/json"},
                method="POST",
            )
        else:
            return {"ok": False, "detail": "지원하지 않습니다"}

        with urllib.request.urlopen(request, timeout=20, context=netssl.context()):
            return {"ok": True, "detail": f"{spec['label']} 응답 정상 · {model}"}

    except urllib.error.HTTPError as exc:
        body = exc.read()[:200].decode("utf-8", "replace")
        hint = "키가 올바르지 않습니다" if exc.code in (401, 403) else f"HTTP {exc.code}"
        return {"ok": False, "detail": f"{hint} — {body}"}
    except (urllib.error.URLError, OSError) as exc:
        return {"ok": False, "detail": f"연결 실패: {exc}"}


class Handler(BaseHTTPRequestHandler):
    """Serve the settings page and its small JSON API."""

    def log_message(self, fmt, *args):  # noqa: D102 - quieter console
        return

    def _send(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        """Serve the page and current settings."""
        if self.path in ("/", "/index.html"):
            html = (ROOT / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return

        if self.path == "/api/settings":
            settings = config.load()
            settings.pop("keys", None)  # never hand real keys back to the page
            self._send({
                "settings": settings,
                "providers": config.status(),
                "roles": config.role_status(),
                "audio": audio_levels(),
            })
            return

        self._send({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        """Apply a settings change, a key, or a connection test."""
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send({"error": "잘못된 요청"}, 400)
            return

        if self.path == "/api/settings":
            payload.pop("keys", None)
            config.update(**payload)
            self._send({"ok": True})
            return

        if self.path == "/api/key":
            provider = payload.get("provider", "")
            if provider not in config.PROVIDERS:
                self._send({"error": "알 수 없는 제공자"}, 400)
                return
            config.set_key(provider, payload.get("key", "").strip())
            self._send({"ok": True, "masked": config.masked_keys().get(provider, "")})
            return

        if self.path == "/api/role":
            config.set_role(payload.get("role", ""), payload.get("provider", ""))
            self._send({"ok": True})
            return

        if self.path == "/api/model":
            provider = payload.get("provider", "")
            if provider not in config.PROVIDERS:
                self._send({"error": "알 수 없는 제공자"}, 400)
                return
            config.set_model(provider, payload.get("model", "").strip())
            self._send({"ok": True, "model": config.model_for(provider)})
            return

        if self.path == "/api/audio":
            target = payload.get("target", "")
            if target not in ("speaker", "microphone"):
                self._send({"error": "speaker 또는 microphone 이어야 합니다"}, 400)
                return
            try:
                level = int(payload.get("level"))
            except (TypeError, ValueError):
                self._send({"error": "0 에서 100 사이의 숫자가 필요합니다"}, 400)
                return
            try:
                setter = robot.set_volume if target == "speaker" else robot.set_mic_volume
                applied = setter(level)
            except robot.RobotError as exc:
                self._send({"error": f"로봇에 전달하지 못했습니다: {exc}"}, 502)
                return
            self._send({"ok": True, "level": applied})
            return

        if self.path == "/api/audio/test":
            try:
                robot.play_test_sound()
            except robot.RobotError as exc:
                self._send({"error": f"소리를 내지 못했습니다: {exc}"}, 502)
                return
            self._send({"ok": True})
            return

        if self.path == "/api/test":
            self._send(check_provider(payload.get("provider", "")))
            return

        self._send({"error": "not found"}, 404)


def main() -> int:
    """Start the admin panel."""
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    shown = "localhost" if HOST in ("127.0.0.1", "localhost") else HOST
    print(f"관리자 화면: http://{shown}:{PORT}")
    if HOST not in ("127.0.0.1", "localhost"):
        print("  주의: 이 화면에는 로그인이 없고 API 키가 들어 있습니다.")
        print("        신뢰하는 네트워크에서만 여세요.")
    print(f"설정 파일  : {config.CONFIG_PATH}")
    print("Ctrl-C 로 종료\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
