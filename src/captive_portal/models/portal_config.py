# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Guest portal configuration model."""

from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class PortalConfig(SQLModel, table=True):
    """Guest portal configuration.

    Attributes:
        id: Primary key (UUID, singleton record)
        success_redirect_url: Post-auth redirect URL (default: /guest/welcome)
        rate_limit_attempts: Max auth attempts per IP in window (1-100, default: 5)
        rate_limit_window_seconds: Rolling window size in seconds (10-3600, default: 60)
    """

    __tablename__ = "portal_config"

    model_config = {"validate_assignment": True}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    success_redirect_url: str = Field(default="/guest/welcome", max_length=2048)
    rate_limit_attempts: int = Field(default=5, ge=1, le=100)
    rate_limit_window_seconds: int = Field(default=60, ge=10, le=3600)
