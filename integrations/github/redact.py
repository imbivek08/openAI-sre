"""Redaction of secrets and credentials from untrusted text.

Applied to logs and other untrusted content before excerpts are stored or
sent to a model. Redaction is best-effort pattern matching — the primary
defense is that secrets are never logged in the first place.
"""

from __future__ import annotations

import re

# Order matters: specific token formats first, generic key=value last.
PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # GitHub tokens
    (re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b"), "<redacted-github-token>"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "<redacted-github-fine-grained-token>"),
    # Generic API keys
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "<redacted-key>"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "<redacted-aws-access-key>"),
    (re.compile(r"\b-----BEGIN [A-Z ]*PRIVATE KEY-----"), "<redacted-private-key>"),
    # Basic auth in URLs
    (re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@@]+@"), r"\1<redacted>:<redacted>@"),
    # Authorization headers
    (re.compile(r"(?i)(authorization\s*[:=]\s*(bearer|basic)\s+)\S+"), r"\1<redacted>"),
    # Connection strings with passwords
    (re.compile(r"(?i)(postgres(?:ql)?://[^:\s]+:)[^@(\s]+(@)"), r"\1<redacted>\2"),
    # Key=value style secrets (generic, applied last; skip already-redacted <> placeholders)
    (re.compile(r"(?i)(\b(SECRET|TOKEN|PASSWORD|API_KEY|PASSWD|AUTH)\b\s*[=:]\s*)(?!<)\S+"), r"\1<redacted>"),
]

_SECRET_KEYS = {"password", "token", "api_key", "secret", "authorization", "access_token"}


def redact_text(text: str) -> str:
    if not text:
        return text
    result = text
    for pattern, replacement in PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def redact_dict(obj: dict) -> dict:
    """Recursively redact likely-secret values in a parsed structure."""
    result: dict = {}
    for key, value in obj.items():
        lower = str(key).lower()
        if any(marker in lower for marker in _SECRET_KEYS):
            result[key] = "<redacted>"
        elif isinstance(value, dict):
            result[key] = redact_dict(value)
        elif isinstance(value, list):
            result[key] = [redact_dict(v) if isinstance(v, dict) else v for v in value]
        else:
            result[key] = value
    return result


def redact_json_text(text: str) -> str:
    """Redact secrets inside a JSON string by re-serializing with redacted values."""
    import json

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return redact_text(text)
    if isinstance(data, dict):
        return json.dumps(redact_dict(data), default=str)
    return redact_text(text)
