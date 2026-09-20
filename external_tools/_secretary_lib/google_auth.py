"""Shared Google OAuth handling for the Reachy secretary tools.

Design note: the robot is headless. This module never launches a browser at tool
call time - a tool call that blocks on an interactive consent screen would hang
the conversation. Instead the OAuth dance happens once, ahead of time, via
``authorize.py`` on a machine with a browser; this module only loads the
resulting token and refreshes it silently.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Calendar needs write access (the assistant creates events).
#
# Gmail needs two scopes: readonly to summarize the inbox, and compose to create
# drafts. Note that Google publishes gmail.compose as "Manage drafts and send
# emails" - there is no drafts-only scope, so this credential is technically
# capable of sending. No code here ever reaches a Gmail send or delete endpoint;
# the guarantee that mail is never sent is enforced by the tool code, not by the
# scope. Drop gmail.compose (and gmail_draft.py) if you would rather have that
# enforced by Google.
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]

_ENV_DIR = "REACHY_SECRETARY_GOOGLE_DIR"


class GoogleAuthError(RuntimeError):
    """Raised when no usable Google credential is available."""


def credential_dir() -> Path:
    """Return the directory holding credentials.json and token.json."""
    override = os.getenv(_ENV_DIR)
    if override:
        return Path(override).expanduser()

    data_home = os.getenv("XDG_DATA_HOME")
    root = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return root / "reachy_secretary_ko"


def token_path() -> Path:
    """Return the path to the stored OAuth token."""
    return credential_dir() / "token.json"


def client_secret_path() -> Path:
    """Return the path to the downloaded OAuth client secret."""
    return credential_dir() / "credentials.json"


def load_credentials() -> Any:
    """Load stored credentials, refreshing them if they have expired.

    Raises:
        GoogleAuthError: if the token is missing, unreadable, or unrefreshable.

    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise GoogleAuthError(
            "google-auth is not installed. Run: pip install google-api-python-client google-auth-oauthlib"
        ) from exc

    path = token_path()
    if not path.exists():
        raise GoogleAuthError(
            f"No Google token at {path}. Run authorize.py once on a machine with a browser, "
            "then copy token.json to the robot."
        )

    try:
        creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    except (ValueError, OSError) as exc:
        raise GoogleAuthError(f"Could not read the Google token at {path}: {exc}") from exc

    if creds.valid:
        return creds

    # An expired token with a refresh token can be renewed without any user
    # interaction. Anything else needs the one-time browser flow again.
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as exc:
            raise GoogleAuthError(
                f"Refreshing the Google token failed ({exc}). Re-run authorize.py to grant access again."
            ) from exc
        _save(creds, path)
        return creds

    raise GoogleAuthError("The stored Google token is not usable. Re-run authorize.py to grant access again.")


def _save(creds: Any, path: Path) -> None:
    """Persist refreshed credentials, ignoring a read-only filesystem."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(creds.to_json(), encoding="utf-8")
    except OSError as exc:
        # A failed write is not fatal: the in-memory credential still works for
        # this process, we just pay the refresh again next start.
        logger.warning("Could not persist refreshed Google token to %s: %s", path, exc)


def build_service(api: str, version: str) -> Any:
    """Build a Google API client for the given API.

    This is a blocking call - run it inside ``asyncio.to_thread`` from async tools.
    """
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise GoogleAuthError(
            "google-api-python-client is not installed. "
            "Run: pip install google-api-python-client google-auth-oauthlib"
        ) from exc

    creds = load_credentials()
    return build(api, version, credentials=creds, cache_discovery=False)
