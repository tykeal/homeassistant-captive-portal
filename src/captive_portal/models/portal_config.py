# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Guest portal configuration model."""

from sqlmodel import Field, SQLModel


class PortalConfig(SQLModel, table=True):
    """Guest portal configuration.

    Attributes:
        id: Primary key (integer, singleton record with id=1)
        success_redirect_url: Post-auth redirect URL (default: /guest/welcome)
        rate_limit_attempts: Max auth attempts per IP in window (1-1000, default: 5)
        rate_limit_window_seconds: Rolling window size in seconds (1-3600, default: 60)
        redirect_to_original_url: Redirect to original URL vs success page (default: True)
    """

    __tablename__ = "portal_config"

    model_config = {"validate_assignment": True}

    id: int = Field(default=1, primary_key=True)
    success_redirect_url: str = Field(default="/guest/welcome", max_length=2048)
    rate_limit_attempts: int = Field(default=5, ge=1, le=1000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    redirect_to_original_url: bool = Field(default=True)
