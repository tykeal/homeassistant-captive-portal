# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""HA integration entity mapping configuration model."""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class IdentifierAttr(str, Enum):
    """Rental Control identifier attribute selector."""

    SLOT_CODE = "slot_code"
    SLOT_NAME = "slot_name"


class HAIntegrationConfig(SQLModel, table=True):
    """HAIntegrationConfig stores per-integration Rental Control mapping.

    Attributes:
        id: Primary key (UUID)
        integration_id: Unique HA integration identifier
        identifier_attr: Chosen attribute (slot_code or slot_name)
        last_sync_utc: Last successful HA poll timestamp (UTC, nullable)
        stale_count: Consecutive missed polls counter
    """

    __tablename__ = "ha_integration_config"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    integration_id: str = Field(unique=True, max_length=128, index=True)
    identifier_attr: IdentifierAttr = Field(default=IdentifierAttr.SLOT_CODE)
    last_sync_utc: Optional[datetime] = Field(default=None)
    stale_count: int = Field(default=0, ge=0)
