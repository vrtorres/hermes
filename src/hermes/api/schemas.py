from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from hermes.domain.models import MessageDetail, MessageMetadata, MessagePage


class AttachmentResponse(BaseModel):
    filename: str | None
    content_type: str
    size: int | None


class MessageMetadataResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    uid: int
    uidvalidity: int
    folder: str
    message_id: str | None
    from_address: str | None = Field(serialization_alias="from")
    to: list[str]
    subject: str | None
    date: datetime | None
    size: int
    has_attachments: bool
    attachments: list[AttachmentResponse]

    @classmethod
    def from_domain(cls, item: MessageMetadata) -> MessageMetadataResponse:
        return cls(
            uid=item.uid,
            uidvalidity=item.uidvalidity,
            folder=item.folder,
            message_id=item.message_id,
            from_address=item.from_address,
            to=list(item.to),
            subject=item.subject,
            date=item.date,
            size=item.size,
            has_attachments=item.has_attachments,
            attachments=[
                AttachmentResponse(
                    filename=value.filename,
                    content_type=value.content_type,
                    size=value.size,
                )
                for value in item.attachments
            ],
        )


class MessageDetailResponse(MessageMetadataResponse):
    body_text: str
    body_truncated: bool
    content_is_untrusted: bool

    @classmethod
    def from_domain(cls, item: MessageDetail) -> MessageDetailResponse:
        base = MessageMetadataResponse.from_domain(item).model_dump()
        return cls(
            **base,
            body_text=item.body_text,
            body_truncated=item.body_truncated,
            content_is_untrusted=item.content_is_untrusted,
        )


class MessagePageResponse(BaseModel):
    items: list[MessageMetadataResponse]
    uidvalidity: int
    next_cursor: str | None

    @classmethod
    def from_domain(cls, page: MessagePage) -> MessagePageResponse:
        return cls(
            items=[MessageMetadataResponse.from_domain(item) for item in page.items],
            uidvalidity=page.uidvalidity,
            next_cursor=page.next_cursor,
        )


class HealthResponse(BaseModel):
    status: str = "ok"


class ErrorResponse(BaseModel):
    detail: str

