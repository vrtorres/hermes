from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hermes.adapters.imap_reader import ImapMailReader
from hermes.api.routes import build_router
from hermes.api.security import SecurityManager
from hermes.config import Settings
from hermes.domain.models import (
    MailConnectionError,
    MailProtocolError,
    MessageNotFoundError,
    MessageTooLargeError,
    UidValidityChangedError,
)
from hermes.logging_config import configure_logging
from hermes.services.message_parser import MessageParser
from hermes.services.message_service import InvalidCursorError, MessageService


def create_app(
    settings: Settings | None = None,
    service: MessageService | None = None,
) -> FastAPI:
    configure_logging()
    settings = settings or Settings.from_env()
    parser = MessageParser(settings.max_body_text_chars)
    if service is None:
        service = MessageService(
            ImapMailReader(settings, parser), parser, settings.max_messages_per_request
        )
    security = SecurityManager(settings)
    app = FastAPI(
        title="Hermes",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.include_router(build_router(service, security, settings.max_messages_per_request))

    @app.exception_handler(InvalidCursorError)
    @app.exception_handler(ValueError)
    async def invalid_request(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(MessageNotFoundError)
    async def not_found(_: Request, exc: MessageNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(UidValidityChangedError)
    async def conflict(_: Request, exc: UidValidityChangedError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(MessageTooLargeError)
    async def too_large(_: Request, exc: MessageTooLargeError) -> JSONResponse:
        return JSONResponse(status_code=413, content={"detail": str(exc)})

    @app.exception_handler(MailConnectionError)
    async def unavailable(_: Request, exc: MailConnectionError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(MailProtocolError)
    async def bad_gateway(_: Request, exc: MailProtocolError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    return app

