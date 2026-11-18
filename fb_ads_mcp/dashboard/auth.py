"""Simple password login with a signed cookie. No extra packages needed."""

from __future__ import annotations

import hashlib
import hmac
import time

COOKIE = "fbdash_session"
SESSION_SECONDS = 7 * 24 * 3600  # stay logged in for 7 days


def _key(password: str, secret: str | None) -> bytes:
    # Changing DASHBOARD_PASSWORD (or DASHBOARD_SECRET) logs everybody out.
    return hashlib.sha256(f"fb-ads-dashboard|{secret or ''}|{password}".encode()).digest()


def make_cookie(password: str, secret: str | None = None) -> str:
    exp = str(int(time.time()) + SESSION_SECONDS)
    sig = hmac.new(_key(password, secret), exp.encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def check_cookie(value: str | None, password: str, secret: str | None = None) -> bool:
    if not value or "." not in value:
        return False
    exp, sig = value.split(".", 1)
    if not exp.isdigit() or int(exp) < time.time():
        return False
    good = hmac.new(_key(password, secret), exp.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, good)


def check_password(given: str, password: str) -> bool:
    return hmac.compare_digest(given.encode(), password.encode())
