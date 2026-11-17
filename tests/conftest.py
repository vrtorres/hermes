from __future__ import annotations

from hermes.config import Settings

SUMMARY_TOKEN = "summary-token-which-is-at-least-32-characters"  # noqa: S105
COMMERCIAL_TOKEN = "commercial-token-which-is-at-least-32-chars"  # noqa: S105


def make_settings(**overrides) -> Settings:
    values = {
        "imap_host": "imap.invalid",
        "imap_port": 993,
        "imap_user": "user@example.invalid",
        "imap_password": "test-password-not-a-real-secret",
        "imap_folder": "INBOX",
        "connect_timeout_seconds": 3,
        "max_messages_per_request": 50,
        "max_message_bytes": 2048,
        "max_body_text_chars": 1000,
        "summary_agent_token": SUMMARY_TOKEN,
        "commercial_agent_token": COMMERCIAL_TOKEN,
        "rate_limit_per_minute": 60,
    }
    values.update(overrides)
    return Settings(**values)

