# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Audit configuration model for retention policy management."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AuditConfig(BaseModel):
    """Audit log retention configuration.

    Attributes:
        audit_retention_days: Number of days to retain audit logs (default 30, max 90)
    """

    audit_retention_days: int = Field(
        default=30,
        ge=1,
        le=90,
        description="Number of days to retain audit logs",
    )
