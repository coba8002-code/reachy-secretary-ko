"""One TLS context for every outbound call.

macOS ships several Pythons with different ideas about trust roots. Apple's
/usr/bin/python3 uses the system keychain and works; a python.org build has
certifi on disk but urllib ignores it until someone runs Install Certificates,
which nobody does. The assistant has to work under whichever interpreter it is
launched with, so pick a working bundle here instead of at every call site.
"""

from __future__ import annotations

import ssl

_context: ssl.SSLContext | None = None


def context() -> ssl.SSLContext:
    """Return an SSL context with trust roots that actually load."""
    global _context
    if _context is not None:
        return _context

    try:
        import certifi

        _context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        _context = ssl.create_default_context()
    return _context
