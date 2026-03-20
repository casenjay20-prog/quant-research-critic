# backend/app/services/billing/paid_token.py
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional, Tuple


def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("utf-8").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * ((4 - (len(s) % 4)) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("utf-8"))


def _sign(message: bytes, secret: str) -> bytes:
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).digest()


def issue_paid_token(
    *,
    secret: str,
    subject: str,
    ttl_seconds: int = 60 * 60 * 24 * 30,  # 30 days
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Issues a simple signed token (HMAC SHA256) with exp timestamp.
    """
    now = int(time.time())
    payload: Dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + int(ttl_seconds),
    }
    if extra:
        payload.update(extra)

    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = _sign(body, secret)

    return f"{_b64url_encode(body)}.{_b64url_encode(sig)}"


def verify_paid_token(token: str, secret: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Verifies token signature + expiration.
    Returns (ok, payload).
    """
    try:
        body_b64, sig_b64 = token.split(".", 1)
        body = _b64url_decode(body_b64)
        sig = _b64url_decode(sig_b64)

        expected = _sign(body, secret)
        if not hmac.compare_digest(sig, expected):
            return False, None

        payload = json.loads(body.decode("utf-8"))
        exp = int(payload.get("exp", 0))
        if exp and int(time.time()) > exp:
            return False, None

        return True, payload
    except Exception:
        return False, None