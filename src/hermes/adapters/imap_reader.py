from __future__ import annotations

import imaplib
import logging
import re
import ssl
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import wraps
from typing import Any

from hermes.config import Settings
from hermes.domain.models import (
    MailConnectionError,
    MailProtocolError,
    MessageMetadata,
    MessageNotFoundError,
    MessageTooLargeError,
    RawMessage,
    SearchFilters,
    UidValidityChangedError,
)
from hermes.services.message_parser import MessageParser

logger = logging.getLogger(__name__)
_SIZE_RE = re.compile(rb"RFC822\.SIZE\s+(\d+)", re.IGNORECASE)
_UID_RE = re.compile(rb"UID\s+(\d+)", re.IGNORECASE)


def _retry_transient(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        for attempt in range(len(self._retry_delays) + 1):
            try:
                return method(self, *args, **kwargs)
            except (imaplib.IMAP4.abort, TimeoutError, OSError) as exc:
                if attempt == len(self._retry_delays):
                    raise MailConnectionError("IMAP connection dropped during operation") from exc
                logger.warning(
                    "transient_imap_error operation=%s retry=%d",
                    method.__name__,
                    attempt + 1,
                )
                time.sleep(self._retry_delays[attempt])
        raise AssertionError("unreachable")  # pragma: no cover

    return wrapped


class ImapMailReader:
    def __init__(
        self,
        settings: Settings,
        parser: MessageParser,
        connection_factory: Callable[..., Any] = imaplib.IMAP4_SSL,
        *,
        retry_delays: tuple[float, ...] = (0.2, 0.8),
    ) -> None:
        self._settings = settings
        self._parser = parser
        self._connection_factory = connection_factory
        self._retry_delays = retry_delays

    def _connect(self) -> Any:
        context = ssl.create_default_context()
        return self._connection_factory(
            self._settings.imap_host,
            port=self._settings.imap_port,
            ssl_context=context,
            timeout=self._settings.connect_timeout_seconds,
        )

    @contextmanager
    def _selected(self, folder: str) -> Iterator[tuple[Any, int]]:
        if folder != self._settings.imap_folder:
            raise MailProtocolError("Folder is not allowed")
        last_error: BaseException | None = None
        connection = None
        for attempt in range(len(self._retry_delays) + 1):
            try:
                connection = self._connect()
                status, _ = connection.login(
                    self._settings.imap_user, self._settings.imap_password
                )
                if status != "OK":
                    raise MailProtocolError("IMAP authentication failed")
                status, _ = connection.select(folder, readonly=True)
                if status != "OK":
                    raise MailProtocolError("Unable to select mailbox read-only")
                uidvalidity = self._uidvalidity(connection)
                break
            except (imaplib.IMAP4.abort, TimeoutError, OSError) as exc:
                last_error = exc
                if connection is not None:
                    self._close(connection)
                if attempt == len(self._retry_delays):
                    raise MailConnectionError("Unable to connect to IMAP server") from exc
                time.sleep(self._retry_delays[attempt])
        else:  # pragma: no cover
            raise MailConnectionError("Unable to connect to IMAP server") from last_error

        try:
            yield connection, uidvalidity
        finally:
            self._close(connection)

    @staticmethod
    def _close(connection: Any) -> None:
        try:
            connection.close()
        except (imaplib.IMAP4.error, OSError):
            pass
        try:
            connection.logout()
        except (imaplib.IMAP4.error, OSError):
            pass

    @staticmethod
    def _uidvalidity(connection: Any) -> int:
        status, data = connection.response("UIDVALIDITY")
        if status != "UIDVALIDITY" or not data or not data[0]:
            raise MailProtocolError("IMAP server did not provide UIDVALIDITY")
        try:
            return int(data[0])
        except (TypeError, ValueError) as exc:
            raise MailProtocolError("Malformed UIDVALIDITY from IMAP server") from exc

    @staticmethod
    def _safe_search_text(value: str) -> str:
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise MailProtocolError("Search value contains control characters")
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    @classmethod
    def _criteria(cls, filters: SearchFilters) -> list[str]:
        criteria = ["ALL"]
        if filters.since:
            criteria.extend(["SINCE", filters.since.strftime("%d-%b-%Y")])
        if filters.before:
            criteria.extend(["BEFORE", filters.before.strftime("%d-%b-%Y")])
        if filters.from_address:
            criteria.extend(["FROM", cls._safe_search_text(filters.from_address)])
        if filters.subject:
            criteria.extend(["SUBJECT", cls._safe_search_text(filters.subject)])
        return criteria

    @_retry_transient
    def search_uids(self, folder: str, filters: SearchFilters) -> tuple[int, list[int]]:
        with self._selected(folder) as (connection, uidvalidity):
            status, data = connection.uid("SEARCH", None, *self._criteria(filters))
            if status != "OK" or not data:
                raise MailProtocolError("IMAP UID SEARCH failed")
            try:
                uids = [int(value) for value in data[0].split()]
            except (TypeError, ValueError) as exc:
                raise MailProtocolError("Malformed UID SEARCH response") from exc
            return uidvalidity, sorted(uids, reverse=True)

    @_retry_transient
    def fetch_metadata(
        self, folder: str, uidvalidity: int, uids: list[int]
    ) -> list[MessageMetadata]:
        if not uids:
            return []
        with self._selected(folder) as (connection, current_uidvalidity):
            self._check_uidvalidity(uidvalidity, current_uidvalidity)
            results: list[MessageMetadata] = []
            for uid in uids:
                status, data = connection.uid(
                    "FETCH",
                    str(uid),
                    "(UID RFC822.SIZE BODY.PEEK[HEADER.FIELDS "
                    "(MESSAGE-ID FROM TO SUBJECT DATE CONTENT-TYPE CONTENT-DISPOSITION)])",
                )
                if status != "OK":
                    raise MailProtocolError("IMAP metadata fetch failed")
                content, size = self._parse_fetch(data, uid, require_body=True)
                results.append(
                    self._parser.metadata(RawMessage(uid, uidvalidity, folder, size, content))
                )
            return results

    @_retry_transient
    def fetch_message(self, folder: str, uidvalidity: int, uid: int) -> RawMessage:
        with self._selected(folder) as (connection, current_uidvalidity):
            self._check_uidvalidity(uidvalidity, current_uidvalidity)
            status, size_data = connection.uid("FETCH", str(uid), "(UID RFC822.SIZE)")
            if status != "OK":
                raise MailProtocolError("IMAP size fetch failed")
            _, size = self._parse_fetch(size_data, uid, require_body=False)
            if size > self._settings.max_message_bytes:
                raise MessageTooLargeError("Message exceeds configured size limit")

            status, data = connection.uid("FETCH", str(uid), "(UID BODY.PEEK[])")
            if status != "OK":
                raise MailProtocolError("IMAP message fetch failed")
            content, _ = self._parse_fetch(data, uid, require_body=True, fallback_size=size)
            if len(content) > self._settings.max_message_bytes:
                raise MessageTooLargeError("Message exceeds configured size limit")
            return RawMessage(uid, uidvalidity, folder, size, content)

    @staticmethod
    def _check_uidvalidity(expected: int, current: int) -> None:
        if expected != current:
            raise UidValidityChangedError("Mailbox UIDVALIDITY changed; refresh the listing")

    @staticmethod
    def _parse_fetch(
        data: Any, uid: int, *, require_body: bool, fallback_size: int | None = None
    ) -> tuple[bytes, int]:
        if not data:
            raise MessageNotFoundError("Message not found")
        body: bytes | None = None
        size = fallback_size
        found_uid = False
        for item in data:
            header: bytes | None = None
            if isinstance(item, tuple) and len(item) == 2:
                header, candidate = item
                if isinstance(candidate, bytes):
                    body = candidate
            elif isinstance(item, bytes):
                header = item
            if isinstance(header, bytes):
                uid_match = _UID_RE.search(header)
                found_uid = found_uid or bool(uid_match and int(uid_match.group(1)) == uid)
                size_match = _SIZE_RE.search(header)
                if size_match:
                    size = int(size_match.group(1))
        if not found_uid:
            raise MessageNotFoundError("Message not found")
        if size is None:
            size = len(body) if body is not None else 0
        if require_body and body is None:
            raise MailProtocolError("Malformed IMAP FETCH response")
        return body or b"", size

