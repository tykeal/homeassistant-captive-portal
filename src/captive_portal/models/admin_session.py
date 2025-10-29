# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0

"""Admin session model for server-side session management."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class AdminSession(SQLModel, table=True):
    """Server-side session storage for admin authentication.

    Implements secure session management with idle and absolute timeouts.
    Used with HTTP-only secure cookies containing the session ID.

    Attributes:
        id: Session ID (UUID, serves as session cookie value)
        admin_id: Foreign key to AdminUser.id
        created_utc: Session creation timestamp for absolute timeout
        last_activity_utc: Last request timestamp for idle timeout
        expires_utc: Pre-calculated expiration (min of idle + absolute)
        ip_address: Client IP for security logging (optional)
        user_agent: Client User-Agent for security logging (optional)
    """

    __tablename__ = "admin_session"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    admin_id: UUID = Field(foreign_key="adminuser.id", index=True)
    created_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_utc: datetime  # Calculated based on timeouts
    ip_address: Optional[str] = Field(default=None, max_length=45)  # IPv6 max length
    user_agent: Optional[str] = Field(default=None, max_length=256)
