import time
from session_manager import create_session_token, verify_session_token


def test_session_token_create_and_verify():
    token = create_session_token(user_id=42, role="Administrator", timeout_minutes=30)
    assert token is not None
    assert "." in token

    payload = verify_session_token(token)
    assert payload is not None
    assert payload["user_id"] == 42
    assert payload["role"] == "Administrator"


def test_session_token_tampering_fails():
    token = create_session_token(user_id=42, role="Faculty")
    parts = token.split(".")

    # Tamper payload
    tampered_token = f"{parts[0]}extra.{parts[1]}"
    assert verify_session_token(tampered_token) is None

    # Tamper signature
    tampered_sig = parts[1][:-2] + "xx"
    tampered_token2 = f"{parts[0]}.{tampered_sig}"
    assert verify_session_token(tampered_token2) is None


def test_session_token_expiration_fails():
    # Create token expired 5 seconds ago
    token = create_session_token(user_id=10, role="Student", timeout_minutes=-1)
    assert verify_session_token(token) is None
