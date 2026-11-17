from __future__ import annotations

import base64
import json
from datetime import datetime

from hermes.domain.interfaces import MailReader
from hermes.domain.models import MessageDetail, MessagePage, SearchFilters
from hermes.services.message_parser import MessageParser


class InvalidCursorError(ValueError):
    pass


class MessageService:
    def __init__(self, reader: MailReader, parser: MessageParser, max_limit: int) -> None:
        self._reader = reader
        self._parser = parser
        self._max_limit = max_limit

    @staticmethod
    def _encode_cursor(uidvalidity: int, before_uid: int) -> str:
        raw = json.dumps(
            {"v": 1, "uidvalidity": uidvalidity, "before_uid": before_uid},
            separators=(",", ":"),
        ).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[int, int]:
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            value = json.loads(base64.urlsafe_b64decode(padded).decode())
            if set(value) != {"v", "uidvalidity", "before_uid"} or value["v"] != 1:
                raise ValueError
            uidvalidity = int(value["uidvalidity"])
            before_uid = int(value["before_uid"])
            if uidvalidity <= 0 or before_uid <= 0:
                raise ValueError
            return uidvalidity, before_uid
        except (ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
            raise InvalidCursorError("Invalid cursor") from exc

    def list_messages(
        self,
        folder: str,
        limit: int,
        cursor: str | None = None,
        filters: SearchFilters | None = None,
    ) -> MessagePage:
        if not 1 <= limit <= self._max_limit:
            raise ValueError(f"limit must be between 1 and {self._max_limit}")
        expected_uidvalidity: int | None = None
        before_uid: int | None = None
        if cursor:
            expected_uidvalidity, before_uid = self._decode_cursor(cursor)

        uidvalidity, uids = self._reader.search_uids(folder, filters or SearchFilters())
        if expected_uidvalidity is not None and expected_uidvalidity != uidvalidity:
            from hermes.domain.models import UidValidityChangedError

            raise UidValidityChangedError("Mailbox UIDVALIDITY changed; restart pagination")
        if before_uid is not None:
            uids = [uid for uid in uids if uid < before_uid]
        selected = uids[: limit + 1]
        page_uids = selected[:limit]
        items = self._reader.fetch_metadata(folder, uidvalidity, page_uids)
        next_cursor = None
        if len(selected) > limit and page_uids:
            next_cursor = self._encode_cursor(uidvalidity, page_uids[-1])
        return MessagePage(tuple(items), uidvalidity, next_cursor)

    def get_message(self, folder: str, uidvalidity: int, uid: int) -> MessageDetail:
        if uid <= 0 or uidvalidity <= 0:
            raise ValueError("uid and uidvalidity must be positive")
        return self._parser.detail(self._reader.fetch_message(folder, uidvalidity, uid))

    def search(
        self,
        folder: str,
        limit: int,
        *,
        since: datetime | None,
        before: datetime | None,
        from_address: str | None,
        subject: str | None,
        cursor: str | None,
    ) -> MessagePage:
        if since and before and since >= before:
            raise ValueError("since must be before before")
        return self.list_messages(
            folder,
            limit,
            cursor,
            SearchFilters(since, before, from_address, subject),
        )

