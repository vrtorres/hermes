from __future__ import annotations

import pytest

from hermes.domain.models import MessageMetadata, RawMessage, SearchFilters, UidValidityChangedError
from hermes.services.message_parser import MessageParser
from hermes.services.message_service import InvalidCursorError, MessageService


class Reader:
    def __init__(self, uidvalidity=42):
        self.uidvalidity = uidvalidity

    def search_uids(self, folder: str, filters: SearchFilters):
        return self.uidvalidity, [10, 9, 8]

    def fetch_metadata(self, folder, uidvalidity, uids):
        return [
            MessageMetadata(uid, uidvalidity, folder, None, None, (), None, None, 1)
            for uid in uids
        ]

    def fetch_message(self, folder, uidvalidity, uid):
        return RawMessage(uid, uidvalidity, folder, 20, b"Subject: test\r\n\r\nbody")


def test_cursor_paginates_and_detects_mailbox_recreation() -> None:
    reader = Reader()
    service = MessageService(reader, MessageParser(100), 50)
    first = service.list_messages("INBOX", 2)
    assert [item.uid for item in first.items] == [10, 9]
    assert first.next_cursor
    second = service.list_messages("INBOX", 2, first.next_cursor)
    assert [item.uid for item in second.items] == [8]
    reader.uidvalidity = 43
    with pytest.raises(UidValidityChangedError):
        service.list_messages("INBOX", 2, first.next_cursor)


def test_invalid_cursor_is_rejected() -> None:
    service = MessageService(Reader(), MessageParser(100), 50)
    with pytest.raises(InvalidCursorError):
        service.list_messages("INBOX", 2, "not-base64")

