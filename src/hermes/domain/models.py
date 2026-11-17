from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AttachmentMetadata:
    filename: str | None
    content_type: str
    size: int | None


@dataclass(frozen=True, slots=True)
class MessageMetadata:
    uid: int
    uidvalidity: int
    folder: str
    message_id: str | None
    from_address: str | None
    to: tuple[str, ...]
    subject: str | None
    date: datetime | None
    size: int
    has_attachments: bool = False
    attachments: tuple[AttachmentMetadata, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class MessageDetail(MessageMetadata):
    body_text: str = ""
    body_truncated: bool = False
    content_is_untrusted: bool = True


@dataclass(frozen=True, slots=True)
class MessagePage:
    items: tuple[MessageMetadata, ...]
    uidvalidity: int
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class SearchFilters:
    since: datetime | None = None
    before: datetime | None = None
    from_address: str | None = None
    subject: str | None = None


@dataclass(frozen=True, slots=True)
class RawMessage:
    uid: int
    uidvalidity: int
    folder: str
    size: int
    content: bytes


class MailError(RuntimeError):
    pass


class MailConnectionError(MailError):
    pass


class MailProtocolError(MailError):
    pass


class MessageNotFoundError(MailError):
    pass


class MessageTooLargeError(MailError):
    pass


class UidValidityChangedError(MailError):
    pass

