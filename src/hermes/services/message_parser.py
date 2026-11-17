from __future__ import annotations

import re
from datetime import UTC, datetime
from email import policy
from email.headerregistry import Address
from email.message import Message
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser

from hermes.domain.models import AttachmentMetadata, MessageDetail, MessageMetadata, RawMessage


class _SafeHTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in {"script", "style", "noscript", "template"}:
            self.ignored_depth += 1
        elif not self.ignored_depth and tag in {"br", "p", "div", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "template"} and self.ignored_depth:
            self.ignored_depth -= 1
        elif not self.ignored_depth and tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth:
            self.parts.append(data)

    def text(self) -> str:
        value = "".join(self.parts)
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\n\s*\n\s*\n+", "\n\n", value)
        return value.strip()


def _header(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    return text or None


def _addresses(values: list[str]) -> tuple[str, ...]:
    result: list[str] = []
    for name, address in getaddresses(values):
        if address:
            try:
                result.append(str(Address(display_name=name, addr_spec=address)))
            except (IndexError, ValueError):
                continue
    return tuple(result)


def _date(message: Message) -> datetime | None:
    raw = message.get("Date")
    if not raw:
        return None
    try:
        value = parsedate_to_datetime(str(raw))
    except (TypeError, ValueError, OverflowError):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _part_size(part: Message) -> int | None:
    raw = part.get_payload(decode=False)
    if isinstance(raw, str):
        return len(raw.encode("utf-8", errors="replace"))
    if isinstance(raw, bytes):
        return len(raw)
    return None


def _attachments(message: Message) -> tuple[AttachmentMetadata, ...]:
    items: list[AttachmentMetadata] = []
    for part in message.walk():
        if part.is_multipart():
            continue
        if part.get_content_disposition() == "attachment" or part.get_filename():
            filename = _header(part.get_filename())
            if filename is not None:
                filename = filename.replace("/", "_").replace("\\", "_")[:255]
            items.append(AttachmentMetadata(filename, part.get_content_type(), _part_size(part)))
    return tuple(items)


def _body(message: Message) -> str:
    plain: list[str] = []
    html: list[str] = []
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        try:
            content = part.get_content()
        except (LookupError, UnicodeError):
            payload = part.get_payload(decode=True) or b""
            content = payload.decode("utf-8", errors="replace")
        if content_type == "text/plain":
            plain.append(str(content))
        else:
            html.append(str(content))
    if plain:
        return "\n\n".join(item.strip() for item in plain if item.strip())
    extractor = _SafeHTMLTextExtractor()
    extractor.feed("\n".join(html))
    return extractor.text()


class MessageParser:
    def __init__(self, max_body_text_chars: int) -> None:
        self._max_body_text_chars = max_body_text_chars

    def metadata(self, raw: RawMessage) -> MessageMetadata:
        message = BytesParser(policy=policy.default).parsebytes(raw.content, headersonly=True)
        return self._metadata(raw, message)

    def detail(self, raw: RawMessage) -> MessageDetail:
        message = BytesParser(policy=policy.default).parsebytes(raw.content)
        metadata = self._metadata(raw, message)
        body = _body(message)
        truncated = len(body) > self._max_body_text_chars
        return MessageDetail(
            **{field: getattr(metadata, field) for field in metadata.__dataclass_fields__},
            body_text=body[: self._max_body_text_chars],
            body_truncated=truncated,
        )

    @staticmethod
    def _metadata(raw: RawMessage, message: Message) -> MessageMetadata:
        attachments = _attachments(message)
        from_values = _addresses([str(value) for value in message.get_all("From", [])])
        return MessageMetadata(
            uid=raw.uid,
            uidvalidity=raw.uidvalidity,
            folder=raw.folder,
            message_id=_header(message.get("Message-ID")),
            from_address=from_values[0] if from_values else None,
            to=_addresses([str(value) for value in message.get_all("To", [])]),
            subject=_header(message.get("Subject")),
            date=_date(message),
            size=raw.size,
            has_attachments=bool(attachments),
            attachments=attachments,
        )

