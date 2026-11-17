import logging
from datetime import UTC, date, datetime, time
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from hermes.api.schemas import (
    HealthResponse,
    MessageDetailResponse,
    MessagePageResponse,
)
from hermes.api.security import Permission, Principal, SecurityManager
from hermes.services.message_service import MessageService

logger = logging.getLogger(__name__)


def build_router(
    service: MessageService, security: SecurityManager, max_limit: int
) -> APIRouter:
    router = APIRouter()
    principal_dependency = Annotated[Principal, Depends(security.authenticate)]
    @router.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        return HealthResponse()

    @router.get(
        "/v1/messages/search",
        response_model=MessagePageResponse,
        response_model_by_alias=True,
        tags=["messages"],
    )
    def search_messages(
        principal: principal_dependency,
        folder: str = Query(default="INBOX", pattern=r"^INBOX$"),
        since: date | None = None,
        before: date | None = None,
        from_address: str | None = Query(
            default=None, min_length=1, max_length=320, pattern=r"^[^\x00-\x1f\x7f]+$"
        ),
        subject: str | None = Query(
            default=None, min_length=1, max_length=500, pattern=r"^[^\x00-\x1f\x7f]+$"
        ),
        limit: int = Query(default=20, ge=1, le=max_limit),
        cursor: str | None = Query(default=None, min_length=1, max_length=1024),
    ) -> MessagePageResponse:
        security.authorize(principal, Permission.SEARCH, folder)
        page = service.search(
            folder,
            limit,
            since=datetime.combine(since, time.min, UTC) if since else None,
            before=datetime.combine(before, time.min, UTC) if before else None,
            from_address=from_address,
            subject=subject,
            cursor=cursor,
        )
        logger.info(
            "mail_search identity=%s count=%d",
            security.audit_id(principal),
            len(page.items),
        )
        return MessagePageResponse.from_domain(page)

    @router.get(
        "/v1/messages",
        response_model=MessagePageResponse,
        response_model_by_alias=True,
        tags=["messages"],
    )
    def list_messages(
        principal: principal_dependency,
        folder: str = Query(default="INBOX", pattern=r"^INBOX$"),
        limit: int = Query(default=20, ge=1, le=max_limit),
        cursor: str | None = Query(default=None, min_length=1, max_length=1024),
    ) -> MessagePageResponse:
        security.authorize(principal, Permission.READ, folder)
        page = service.list_messages(folder, limit, cursor)
        logger.info("mail_list identity=%s count=%d", security.audit_id(principal), len(page.items))
        return MessagePageResponse.from_domain(page)

    @router.get(
        "/v1/messages/{uid}",
        response_model=MessageDetailResponse,
        response_model_by_alias=True,
        tags=["messages"],
    )
    def get_message(
        uid: int,
        principal: principal_dependency,
        folder: str = Query(default="INBOX", pattern=r"^INBOX$"),
        uidvalidity: int = Query(gt=0),
    ) -> MessageDetailResponse:
        security.authorize(principal, Permission.READ, folder)
        detail = service.get_message(folder, uidvalidity, uid)
        logger.info("mail_get identity=%s uid=%d", security.audit_id(principal), uid)
        return MessageDetailResponse.from_domain(detail)

    return router

