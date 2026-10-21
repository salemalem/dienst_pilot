"""Signed demo tokens (HMAC-SHA256). Real single sign-on replaces this later."""

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta


class InvalidTokenError(Exception):
    """The token is malformed, forged or expired."""


@dataclass(frozen=True)
class Claims:
    """What a token says about its holder."""

    user_id: str
    role: str
    department_id: str
    expires: datetime


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue(claims: Claims, secret: str) -> str:
    """Return a signed token for the claims."""
    body = _b64(
        json.dumps(
            {
                "sub": claims.user_id,
                "role": claims.role,
                "dep": claims.department_id,
                "exp": claims.expires.isoformat(),
            },
            separators=(",", ":"),
        ).encode()
    )
    sig = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify(token: str, secret: str, now: datetime) -> Claims:
    """Return the claims of a valid token, or raise InvalidTokenError."""
    try:
        body, sig = token.split(".")
    except ValueError as e:
        raise InvalidTokenError("malformed") from e
    expected = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise InvalidTokenError("bad signature")
    data = json.loads(_unb64(body))
    claims = Claims(data["sub"], data["role"], data["dep"], datetime.fromisoformat(data["exp"]))
    if claims.expires <= now:
        raise InvalidTokenError("expired")
    return claims


def expiry(now: datetime, hours: int) -> datetime:
    """Return when a token issued now expires."""
    return now + timedelta(hours=hours)
