#!/usr/bin/env python3
"""One-time Google authorization for the Reachy secretary tools.

Run this on a machine with a web browser (your Mac), not on the robot. It opens
a consent screen, then writes token.json next to credentials.json. Copy that
token.json to the robot afterwards - the robot never needs a browser.

    python3 authorize.py

Requires: pip install google-api-python-client google-auth-oauthlib
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "external_tools"))
from _secretary_lib.google_auth import SCOPES, client_secret_path, token_path  # noqa: E402


def main() -> int:
    """Run the interactive OAuth flow and store the token."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("google-auth-oauthlib is not installed.", file=sys.stderr)
        print("Run: pip install google-api-python-client google-auth-oauthlib", file=sys.stderr)
        return 1

    secret = client_secret_path()
    if not secret.exists():
        print(f"OAuth client secret not found at:\n  {secret}\n", file=sys.stderr)
        print(
            "Create an OAuth client (type: Desktop app) in Google Cloud Console,\n"
            "download the JSON, and save it at that exact path as credentials.json.",
            file=sys.stderr,
        )
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
    creds = flow.run_local_server(port=0)

    out = token_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(creds.to_json(), encoding="utf-8")

    print(f"\nAuthorized. Token written to:\n  {out}")
    print("\nNow copy it to the robot, for example:")
    print(f"  scp {out} <robot-user>@<robot-host>:~/.local/share/reachy_secretary_ko/token.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
