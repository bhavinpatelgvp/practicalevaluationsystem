import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from config import settings


def _urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _urlsafe_b64decode(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded)


def create_session_token(user_id: int, role: str, timeout_minutes: int | None = None) -> str:
    """Create an HMAC-SHA256 signed session token."""
    if timeout_minutes is None:
        timeout_minutes = settings.session_timeout_minutes

    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=timeout_minutes)

    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }

    payload_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    b64_payload = _urlsafe_b64encode(payload_json)

    signature_bytes = hmac.new(
        settings.secret_key.encode("utf-8"),
        b64_payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    b64_signature = _urlsafe_b64encode(signature_bytes)

    return f"{b64_payload}.{b64_signature}"


def verify_session_token(token: str) -> dict | None:
    """Verify cryptographic signature and expiration of session token."""
    if not token or "." not in token:
        return None

    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None

        b64_payload, b64_signature = parts

        # Verify signature
        expected_sig_bytes = hmac.new(
            settings.secret_key.encode("utf-8"),
            b64_payload.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        expected_sig = _urlsafe_b64encode(expected_sig_bytes)

        if not hmac.compare_digest(b64_signature, expected_sig):
            return None

        # Decode payload
        payload_bytes = _urlsafe_b64decode(b64_payload)
        payload = json.loads(payload_bytes.decode("utf-8"))

        # Check expiration
        exp = payload.get("exp")
        if not exp or datetime.now(timezone.utc).timestamp() > exp:
            return None

        return {
            "user_id": int(payload["sub"]),
            "role": payload.get("role", ""),
        }
    except Exception:
        return None
