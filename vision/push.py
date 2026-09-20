"""Send a notification to the owner's phone.

An intruder alert that only the empty room hears is worthless, so this is the
one part of the system that must reach outside the house.

Uses ntfy.sh: no account, no API key - you pick a topic name and subscribe to it
in the ntfy app. Anyone who knows the topic can read it, so the topic is treated
as a secret and generated long and random by `setup_topic`.
"""

from __future__ import annotations

import json
import os
import secrets
import urllib.error
import urllib.request
from pathlib import Path

CONFIG_PATH = Path(
    os.getenv("REACHY_PUSH_CONFIG", Path.home() / ".local" / "share" / "reachy-secretary" / "push.json")
)
TIMEOUT = 8.0


def _config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def setup_topic() -> str:
    """Create and store a random ntfy topic. Returns the topic name."""
    config = _config()
    topic = config.get("topic") or f"reachy-{secrets.token_urlsafe(16)}"
    config["topic"] = topic
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return topic


def topic() -> str | None:
    """Return the configured topic, if there is one."""
    return _config().get("topic")


def send(title: str, message: str, *, priority: str = "default", image: bytes | None = None) -> bool:
    """Push a notification. Returns False when it could not be delivered."""
    name = topic()
    if not name:
        return False

    url = f"https://ntfy.sh/{name}"
    headers = {
        "Title": title.encode("utf-8").decode("latin-1", "ignore") or "Reachy",
        "Priority": priority,
        "Markdown": "yes",
    }

    # ntfy headers are latin-1 only, so Korean titles must ride in the body.
    body = message.encode("utf-8")
    if image is not None:
        headers["Filename"] = "snapshot.jpg"
        body = image

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT, context=_ssl_context()):
            return True
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        # macOS ships Pythons with no CA bundle, so urllib fails TLS where curl
        # succeeds. This runs from both the system Python (hooks) and a venv
        # (vision), so fall back rather than depend on the caller's setup.
        return _send_via_curl(url, headers, body)


def _ssl_context():
    """Return the shared SSL context."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "assistant"))
    import netssl

    return netssl.context()


def _send_via_curl(url: str, headers: dict[str, str], body: bytes) -> bool:
    """Deliver through curl, which always has working trust roots on macOS."""
    import shutil
    import subprocess
    import tempfile

    if not shutil.which("curl"):
        return False

    args = ["curl", "-s", "-S", "-m", str(int(TIMEOUT)), "-o", "/dev/null", "-w", "%{http_code}", "-X", "POST", url]
    for key, value in headers.items():
        args += ["-H", f"{key}: {value}"]

    with tempfile.NamedTemporaryFile(delete=True) as tmp:
        tmp.write(body)
        tmp.flush()
        args += ["--data-binary", f"@{tmp.name}"]
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=TIMEOUT + 4)
        except (subprocess.SubprocessError, OSError):
            return False

    return result.stdout.strip().startswith("2")
