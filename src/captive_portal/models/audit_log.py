# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Audit log model for administrative action tracking."""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlmodel import Column, Field, JSON, SQLModel


class AuditLog(SQLModel, table=True):
    """AuditLog records administrative actions for compliance.

    Attributes:
        id: Primary key (UUID)
        actor: Username or system identifier performing action
        role_snapshot: Actor's role at time of action
        action: Action type (e.g., 'voucher.create', 'grant.revoke')
        target_type: Entity type affected (e.g., 'voucher', 'grant')
        target_id: Entity ID affected
        timestamp_utc: Action timestamp (UTC, immutable)
        outcome: Action outcome ('success', 'failure', etc.)
        meta: Optional JSON metadata (IP, user-agent, etc.)
    """

    __tablename__ = "audit_log"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    actor: str = Field(max_length=128, index=True)
    role_snapshot: str = Field(max_length=32)
    action: str = Field(max_length=64, index=True)
    target_type: str = Field(max_length=32)
    target_id: str = Field(max_length=128)
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    outcome: str = Field(max_length=32)
    meta: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
