from __future__ import annotations

import pytest

from hermes.adapters.imap_reader import ImapMailReader
from hermes.domain.models import (
    MailConnectionError,
    MessageTooLargeError,
    SearchFilters,
    UidValidityChangedError,
)
from hermes.services.message_parser import MessageParser
from tests.conftest import make_settings


class FakeImap:
    def __init__(self, *, uidvalidity: bytes = b"42", fetches=None) -> None:
        self.uidvalidity = uidvalidity
        self.fetches = list(fetches or [])
        self.calls = []
        self.readonly = None

    def login(self, user, password):
        self.calls.append(("login", user, password))
        return "OK", [b""]

    def select(self, folder, readonly=False):
        self.readonly = readonly
        return "OK", [b"2"]

    def response(self, name):
        return name, [self.uidvalidity]

    def uid(self, command, *args):
        self.calls.append((command, *args))
        if command == "SEARCH":
            return "OK", [b"2 9"]
        return self.fetches.pop(0)

    def close(self):
        return "OK", []

    def logout(self):
        return "BYE", []


class DropOnceImap(FakeImap):
    def __init__(self) -> None:
        super().__init__()
        self.dropped = False

    def uid(self, command, *args):
        if not self.dropped:
            self.dropped = True
            raise TimeoutError
        return super().uid(command, *args)


def reader(fake: FakeImap, **settings_overrides) -> ImapMailReader:
    return ImapMailReader(
        make_settings(**settings_overrides),
        MessageParser(1000),
        connection_factory=lambda *args, **kwargs: fake,
        retry_delays=(),
    )


def test_search_uses_uid_and_readonly() -> None:
    fake = FakeImap()
    uidvalidity, uids = reader(fake).search_uids("INBOX", SearchFilters(subject="safe"))
    assert (uidvalidity, uids) == (42, [9, 2])
    assert fake.readonly is True
    assert fake.calls[-1][0] == "SEARCH"
    assert '"safe"' in fake.calls[-1]


def test_fetch_uses_size_before_body_peek_and_rejects_large_message() -> None:
    fake = FakeImap(fetches=[("OK", [(b"1 (UID 9 RFC822.SIZE 3000)", b")")])])
    with pytest.raises(MessageTooLargeError):
        reader(fake, max_message_bytes=2048).fetch_message("INBOX", 42, 9)
    assert fake.calls[-1] == ("FETCH", "9", "(UID RFC822.SIZE)")
    assert all("BODY.PEEK[]" not in call for call in fake.calls)


def test_fetch_body_uses_peek_and_checks_uidvalidity() -> None:
    fake = FakeImap(
        fetches=[
            ("OK", [(b"1 (UID 9 RFC822.SIZE 20)", b")")]),
            ("OK", [(b"1 (UID 9 BODY[] {20}", b"Subject: ok\r\n\r\nbody"), b")"]),
        ]
    )
    message = reader(fake).fetch_message("INBOX", 42, 9)
    assert message.content.endswith(b"body")
    assert fake.calls[-1] == ("FETCH", "9", "(UID BODY.PEEK[])")

    changed = FakeImap(uidvalidity=b"43")
    with pytest.raises(UidValidityChangedError):
        reader(changed).fetch_message("INBOX", 42, 9)


def test_transient_connection_error_is_bounded() -> None:
    attempts = 0

    def fail(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        raise TimeoutError

    value = ImapMailReader(
        make_settings(), MessageParser(1000), connection_factory=fail, retry_delays=(0, 0)
    )
    with pytest.raises(MailConnectionError):
        value.search_uids("INBOX", SearchFilters())
    assert attempts == 3


def test_connection_drop_during_operation_is_retried() -> None:
    fake = DropOnceImap()
    value = ImapMailReader(
        make_settings(),
        MessageParser(1000),
        connection_factory=lambda *args, **kwargs: fake,
        retry_delays=(0,),
    )
    assert value.search_uids("INBOX", SearchFilters()) == (42, [9, 2])
    assert fake.dropped is True

