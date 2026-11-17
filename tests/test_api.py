from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from hermes.api.app import create_app
from hermes.domain.models import MessageDetail, MessageMetadata, MessagePage
from tests.conftest import COMMERCIAL_TOKEN, SUMMARY_TOKEN, make_settings


class StubService:
    def __init__(self) -> None:
        self.item = MessageMetadata(
            uid=9,
            uidvalidity=42,
            folder="INBOX",
            message_id="<id@example.test>",
            from_address="Sender <sender@example.test>",
            to=("to@example.test",),
            subject="Subject",
            date=datetime(2024, 1, 1, tzinfo=UTC),
            size=100,
        )

    def list_messages(self, folder, limit, cursor=None):
        return MessagePage((self.item,), 42, None)

    def search(self, folder, limit, **kwargs):
        return MessagePage((self.item,), 42, None)

    def get_message(self, folder, uidvalidity, uid):
        values = {field: getattr(self.item, field) for field in self.item.__dataclass_fields__}
        return MessageDetail(**values, body_text="untrusted body")


def client(**settings_overrides) -> TestClient:
    return TestClient(create_app(make_settings(**settings_overrides), StubService()))


def auth(token=SUMMARY_TOKEN):
    return {"Authorization": f"Bearer {token}"}


def test_health_is_minimal_and_public() -> None:
    response = client().get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_data_is_fail_closed_and_response_contract_uses_from() -> None:
    api = client()
    assert api.get("/v1/messages").status_code == 401
    assert api.get("/v1/messages", headers=auth("wrong")).status_code == 401
    response = api.get("/v1/messages", headers=auth())
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["uid"] == 9
    assert item["from"] == "Sender <sender@example.test>"
    assert "from_address" not in item


def test_commercial_identity_can_search_but_not_read() -> None:
    api = client()
    assert api.get("/v1/messages/search", headers=auth(COMMERCIAL_TOKEN)).status_code == 200
    assert api.get("/v1/messages", headers=auth(COMMERCIAL_TOKEN)).status_code == 403
    assert (
        api.get("/v1/messages/9?uidvalidity=42", headers=auth(COMMERCIAL_TOKEN)).status_code
        == 403
    )


def test_detail_marks_content_untrusted_and_folder_is_allowlisted() -> None:
    api = client()
    response = api.get("/v1/messages/9?uidvalidity=42", headers=auth())
    assert response.status_code == 200
    assert response.json()["content_is_untrusted"] is True
    assert api.get("/v1/messages?folder=Archive", headers=auth()).status_code == 422


def test_rate_limit_is_enforced() -> None:
    api = client(rate_limit_per_minute=1)
    assert api.get("/v1/messages", headers=auth()).status_code == 200
    assert api.get("/v1/messages", headers=auth()).status_code == 429


def test_search_rejects_control_characters() -> None:
    response = client().get("/v1/messages/search?subject=hello%0Aworld", headers=auth())
    assert response.status_code == 422

