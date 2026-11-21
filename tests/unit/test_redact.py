"""Tests for secret redaction."""

from integrations.github.redact import redact_json_text, redact_text


def test_redacts_github_token():
    text = "token=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 done"
    out = redact_text(text)
    assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" not in out
    assert "<redacted-github-token>" in out


def test_redacts_key_value_secret():
    text = "PASSWORD=hunter2 connected"
    out = redact_text(text)
    assert "hunter2" not in out
    assert "<redacted>" in out


def test_redacts_connection_string():
    text = "postgresql://user:secretpw@localhost:5432/db"
    out = redact_text(text)
    assert "secretpw" not in out


def test_redacts_authorization_header():
    text = "authorization: Bearer abcdef123456"
    out = redact_text(text)
    assert "abcdef123456" not in out


def test_redact_json_text():
    text = '{"token": "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", "msg": "ok"}'
    out = redact_json_text(text)
    assert "ghp_" not in out
    assert "<redacted>" in out
    assert '"ok"' in out


def test_plain_text_unchanged():
    text = "everything is fine here"
    assert redact_text(text) == text
