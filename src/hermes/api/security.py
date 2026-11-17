from __future__ import annotations

import hashlib
import hmac
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from enum import StrEnum

from fastapi import Header, HTTPException, status

from hermes.config import Settings

logger = logging.getLogger(__name__)


class Permission(StrEnum):
    READ = "mail:read"
    SEARCH = "mail:search"


@dataclass(frozen=True, slots=True)
class Principal:
    identity: str
    permissions: frozenset[Permission]
    folders: frozenset[str]


class RateLimiter:
    def __init__(self, requests_per_minute: int) -> None:
        self._limit = requests_per_minute
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, identity: str) -> None:
        now = time.monotonic()
        with self._lock:
            events = self._events[identity]
            while events and events[0] <= now - 60:
                events.popleft()
            if len(events) >= self._limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": "60"},
                )
            events.append(now)


class SecurityManager:
    def __init__(self, settings: Settings) -> None:
        self._tokens: list[tuple[str, Principal]] = [
            (
                settings.summary_agent_token,
                Principal(
                    "summary_agent",
                    frozenset({Permission.READ, Permission.SEARCH}),
                    frozenset({settings.imap_folder}),
                ),
            )
        ]
        if settings.commercial_agent_token:
            self._tokens.append(
                (
                    settings.commercial_agent_token,
                    Principal(
                        "commercial_agent",
                        frozenset({Permission.SEARCH}),
                        frozenset({settings.imap_folder}),
                    ),
                )
            )
        self._limiter = RateLimiter(settings.rate_limit_per_minute)

    def authenticate(self, authorization: str | None = Header(default=None)) -> Principal:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        candidate = authorization.removeprefix("Bearer ")
        match: Principal | None = None
        for token, principal in self._tokens:
            if hmac.compare_digest(candidate, token):
                match = principal
        if match is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        self._limiter.check(match.identity)
        return match

    @staticmethod
    def authorize(principal: Principal, permission: Permission, folder: str) -> None:
        if permission not in principal.permissions or folder not in principal.folders:
            logger.warning(
                "authorization_denied identity=%s permission=%s folder_allowed=%s",
                principal.identity,
                permission,
                folder in principal.folders,
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    @staticmethod
    def audit_id(principal: Principal) -> str:
        return hashlib.sha256(principal.identity.encode()).hexdigest()[:12]

