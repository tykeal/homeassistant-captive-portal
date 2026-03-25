# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Admin account model for portal authentication."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class AdminRole(str, Enum):
    """Admin access control roles."""

    VIEWER = "viewer"
    AUDITOR = "auditor"
    OPERATOR = "operator"
    ADMIN = "admin"


class AdminUser(SQLModel, table=True):
    """AdminUser represents an administrative account.

    Attributes:
        id: Primary key (UUID)
        username: Unique username
        email: Admin email address
        role: RBAC role (viewer, auditor, operator, admin)
        password_hash: Argon2 password hash (PHC format)
        created_utc: Creation timestamp (UTC)
        last_login_utc: Last successful login timestamp (UTC, nullable)
        active: Account active flag
        version: Optimistic locking version counter
    """

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    username: str = Field(unique=True, max_length=64, index=True)
    email: str = Field(max_length=255, index=True)
    role: AdminRole = Field(default=AdminRole.VIEWER)
    password_hash: str = Field(max_length=255)  # Argon2 PHC format
    created_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_utc: Optional[datetime] = Field(default=None)
    active: bool = Field(default=True)
    version: int = Field(default=1, sa_column_kwargs={"server_default": "1"})


# Alias for API response models to distinguish from database models
AdminAccount = AdminUser
