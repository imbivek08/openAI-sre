"""GitHub webhook signature verification (HMAC-SHA256, constant-time)."""

from __future__ import annotations

import hashlib
import hmac
import logging

logger = logging.getLogger(__name__)


class SignatureError(Exception):
    pass


def verify_signature(payload: bytes, signature_header: str | None, secret: str) -> bool:
    """Verify X-Hub-Signature-256 using constant-time comparison.

    Returns False on any mismatch or malformed input. Never raises for bad
    input so callers can return a uniform rejection.
    """
    if not secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected_mac = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    provided = signature_header[len("sha256=") :]
    try:
        provided_bytes = bytes.fromhex(provided)
    except ValueError:
        return False
    return hmac.compare_digest(expected_mac, provided_bytes)


def summarize_delivery(event_type: str | None, action: str | None, payload: dict) -> dict:
    """Non-sensitive metadata about a delivery for persistence. Never logs body."""
    repo = payload.get("repository", {}) or {}
    run = payload.get("workflow_run", {}) or {}
    return {
        "event_type": event_type or "",
        "action": action or "",
        "repository": repo.get("full_name", ""),
        "run_id": str(run.get("id", "")),
        "sender_login": (payload.get("sender", {}) or {}).get("login", ""),
    }
