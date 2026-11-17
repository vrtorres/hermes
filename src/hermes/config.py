from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigurationError(RuntimeError):
    """Raised when required configuration is missing or unsafe."""


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value


def _token(name: str) -> str:
    value = _required(name)
    if len(value) < 32:
        raise ConfigurationError(f"{name} must contain at least 32 characters")
    return value


def _integer(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    imap_host: str
    imap_port: int
    imap_user: str
    imap_password: str
    imap_folder: str
    connect_timeout_seconds: int
    max_messages_per_request: int
    max_message_bytes: int
    max_body_text_chars: int
    summary_agent_token: str
    commercial_agent_token: str | None
    rate_limit_per_minute: int

    @classmethod
    def from_env(cls) -> Settings:
        imap_host = _required("MAIL_IMAP_HOST")
        imap_user = _required("MAIL_IMAP_USER")
        imap_password = _required("MAIL_IMAP_PASSWORD")
        folder = os.environ.get("MAIL_IMAP_FOLDER", "INBOX").strip()
        if folder != "INBOX":
            raise ConfigurationError("MAIL_IMAP_FOLDER must be INBOX in phase 1")

        commercial = os.environ.get("API_COMMERCIAL_AGENT_TOKEN", "").strip() or None
        if commercial is not None and len(commercial) < 32:
            raise ConfigurationError(
                "API_COMMERCIAL_AGENT_TOKEN must contain at least 32 characters"
            )
        summary = _token("API_AUTH_TOKEN")
        if commercial is not None and commercial == summary:
            raise ConfigurationError("Agent tokens must be distinct")

        return cls(
            imap_host=imap_host,
            imap_port=_integer("MAIL_IMAP_PORT", 993, minimum=1, maximum=65535),
            imap_user=imap_user,
            imap_password=imap_password,
            imap_folder=folder,
            connect_timeout_seconds=_integer(
                "MAIL_CONNECT_TIMEOUT_SECONDS", 15, minimum=1, maximum=120
            ),
            max_messages_per_request=_integer(
                "MAIL_MAX_MESSAGES_PER_REQUEST", 50, minimum=1, maximum=200
            ),
            max_message_bytes=_integer(
                "MAIL_MAX_MESSAGE_BYTES", 2_097_152, minimum=1024, maximum=25_000_000
            ),
            max_body_text_chars=_integer(
                "MAIL_MAX_BODY_TEXT_CHARS", 50_000, minimum=100, maximum=500_000
            ),
            summary_agent_token=summary,
            commercial_agent_token=commercial,
            rate_limit_per_minute=_integer(
                "API_RATE_LIMIT_PER_MINUTE", 60, minimum=1, maximum=10_000
            ),
        )

