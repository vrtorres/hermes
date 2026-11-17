from __future__ import annotations

from typing import Protocol

from hermes.domain.models import MessageMetadata, RawMessage, SearchFilters


class MailReader(Protocol):
    def search_uids(self, folder: str, filters: SearchFilters) -> tuple[int, list[int]]: ...

    def fetch_metadata(
        self, folder: str, uidvalidity: int, uids: list[int]
    ) -> list[MessageMetadata]: ...

    def fetch_message(self, folder: str, uidvalidity: int, uid: int) -> RawMessage: ...


class MailWriter(Protocol):
    """Reserved port for a separately authorized future phase; no implementation exists."""

