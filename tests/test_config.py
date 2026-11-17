from __future__ import annotations

import pytest

from hermes.config import ConfigurationError, Settings


def test_missing_secret_fails_without_exposing_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "MAIL_IMAP_HOST",
        "MAIL_IMAP_USER",
        "MAIL_IMAP_PASSWORD",
        "API_AUTH_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ConfigurationError, match="MAIL_IMAP_HOST") as error:
        Settings.from_env()
    assert "password" not in str(error.value).lower()


def test_tokens_must_be_distinct(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAIL_IMAP_HOST", "imap.invalid")
    monkeypatch.setenv("MAIL_IMAP_USER", "user")
    monkeypatch.setenv("MAIL_IMAP_PASSWORD", "secret")
    monkeypatch.setenv("API_AUTH_TOKEN", "x" * 32)
    monkeypatch.setenv("API_COMMERCIAL_AGENT_TOKEN", "x" * 32)
    with pytest.raises(ConfigurationError, match="distinct"):
        Settings.from_env()

