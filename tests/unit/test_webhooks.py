"""Tests for webhook signature verification."""

import hashlib
import hmac
import json

from integrations.github.webhooks import verify_signature

SECRET = "test-webhook-secret"
PAYLOAD = {"action": "completed", "workflow_run": {"id": 123}}


def _sign(payload: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={mac}"


def test_valid_signature():
    body = json.dumps(PAYLOAD).encode()
    assert verify_signature(body, _sign(body, SECRET), SECRET) is True


def test_invalid_signature():
    body = json.dumps(PAYLOAD).encode()
    assert verify_signature(body, _sign(body, "wrong-secret"), SECRET) is False


def test_tampered_payload():
    body = json.dumps(PAYLOAD).encode()
    sig = _sign(body, SECRET)
    tampered = json.dumps({"action": "completed", "workflow_run": {"id": 999}}).encode()
    assert verify_signature(tampered, sig, SECRET) is False


def test_missing_secret():
    body = json.dumps(PAYLOAD).encode()
    assert verify_signature(body, _sign(body, SECRET), "") is False


def test_malformed_header():
    body = json.dumps(PAYLOAD).encode()
    assert verify_signature(body, "not-a-signature", SECRET) is False
    assert verify_signature(body, "sha256=zzzz", SECRET) is False


def test_constant_time_no_exception_on_nonhex():
    body = b"{}"
    assert verify_signature(body, "sha256=!!!", SECRET) is False
