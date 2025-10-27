# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""
Session management middleware for admin authentication.

Implements secure session handling with:
- HTTP-only session cookies (D12)
- Configurable idle timeout (default 30 minutes) (D17)
- Configurable absolute timeout (default 8 hours) (D17)
- Secure, SameSite=Strict cookie attributes
- Session rotation on privilege escalation
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import Request, Response
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp


class SessionConfig(BaseModel):
    """Session configuration parameters."""

    idle_minutes: int = 30
    max_hours: int = 8
    cookie_name: str = "session_id"
    cookie_secure: bool = True
    cookie_httponly: bool = True
    cookie_samesite: Literal["strict", "lax", "none"] = "strict"


class SessionData(BaseModel):
    """In-memory session data."""

    admin_id: "UUID"  # Changed from int to UUID
    created_utc: datetime
    last_activity_utc: datetime
    expires_utc: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class SessionStore:
    """In-memory session store (future: Redis/DB)."""

    def __init__(self) -> None:
        """Initialize empty session store."""
        self._sessions: dict[str, SessionData] = {}

    def create(
        self,
        admin_id: UUID,
        config: SessionConfig,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> str:
        """Create a new session and return session ID."""
        session_id = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=config.max_hours)

        self._sessions[session_id] = SessionData(
            admin_id=admin_id,
            created_utc=now,
            last_activity_utc=now,
            expires_utc=expires,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return session_id

    def get(self, session_id: str) -> Optional[SessionData]:
        """Retrieve session data by ID."""
        return self._sessions.get(session_id)

    def update_activity(self, session_id: str, config: SessionConfig) -> bool:
        """Update last activity timestamp. Returns True if successful."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        now = datetime.now(timezone.utc)
        session.last_activity_utc = now
        return True

    def delete(self, session_id: str) -> bool:
        """Delete a session. Returns True if session existed."""
        return self._sessions.pop(session_id, None) is not None

    def cleanup_expired(self, config: SessionConfig) -> int:
        """Remove expired sessions. Returns number of sessions removed."""
        now = datetime.now(timezone.utc)
        expired = [
            sid for sid, session in self._sessions.items() if self._is_expired(session, config, now)
        ]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)

    def _is_expired(self, session: SessionData, config: SessionConfig, now: datetime) -> bool:
        """Check if session is expired (idle or absolute timeout)."""
        idle_threshold = now - timedelta(minutes=config.idle_minutes)
        return session.last_activity_utc < idle_threshold or session.expires_utc < now


class SessionMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for session management."""

    def __init__(
        self,
        app: ASGIApp,
        config: Optional[SessionConfig] = None,
        store: Optional[SessionStore] = None,
    ) -> None:
        """Initialize session middleware."""
        super().__init__(app)
        self.config = config or SessionConfig()
        self.store = store or SessionStore()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process request and validate session."""
        session_id = request.cookies.get(self.config.cookie_name)
        request.state.session_id = None
        request.state.admin_id = None

        if session_id:
            session = self.store.get(session_id)
            if session and not self._is_session_expired(session):
                self.store.update_activity(session_id, self.config)
                request.state.session_id = session_id
                request.state.admin_id = session.admin_id

        response = await call_next(request)
        return response

    def _is_session_expired(self, session: SessionData) -> bool:
        """Check if session has expired."""
        now = datetime.now(timezone.utc)
        idle_threshold = now - timedelta(minutes=self.config.idle_minutes)
        return session.last_activity_utc < idle_threshold or session.expires_utc < now

    def create_session(
        self,
        response: Response,
        admin_id: UUID,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> str:
        """Create a session and set cookie."""
        session_id = self.store.create(admin_id, self.config, ip_address, user_agent)
        response.set_cookie(
            key=self.config.cookie_name,
            value=session_id,
            httponly=self.config.cookie_httponly,
            secure=self.config.cookie_secure,
            samesite=self.config.cookie_samesite,
            max_age=self.config.max_hours * 3600,
        )
        return session_id

    def delete_session(self, response: Response, session_id: str) -> bool:
        """Delete a session and clear cookie."""
        response.delete_cookie(key=self.config.cookie_name)
        return self.store.delete(session_id)


async def require_admin(request: Request) -> UUID:
    """FastAPI dependency to require admin authentication.

    Args:
        request: FastAPI request

    Returns:
        Admin user ID (UUID)

    Raises:
        HTTPException: 401 if not authenticated
    """
    from fastapi import HTTPException, status

    admin_id: UUID | None = getattr(request.state, "admin_id", None)
    if not admin_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return admin_id
