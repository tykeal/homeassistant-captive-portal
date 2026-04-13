# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""HA integration entity mapping configuration model."""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import field_validator
from sqlalchemy import Column
from sqlmodel import Field, SQLModel
from sqlmodel import JSON as SA_JSON


class IdentifierAttr(str, Enum):
    """Rental Control identifier attribute selector."""

    SLOT_CODE = "slot_code"
    SLOT_NAME = "slot_name"
    LAST_FOUR = "last_four"


class HAIntegrationConfig(SQLModel, table=True):
    """HAIntegrationConfig stores per-integration Rental Control mapping.

    Attributes:
        id: Primary key (UUID)
        integration_id: Unique HA integration identifier
        identifier_attr: Chosen attribute (slot_code, slot_name, last_four)
        checkout_grace_minutes: Minutes of WiFi access after checkout (0-30)
        last_sync_utc: Last successful HA poll timestamp (UTC, nullable)
        stale_count: Consecutive missed polls counter
        allowed_vlans: Optional list of VLAN IDs (1-4094) authorized for
            this integration. None or empty means unrestricted.
    """

    __tablename__ = "ha_integration_config"

    model_config = {"validate_assignment": True}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    integration_id: str = Field(unique=True, max_length=128, index=True)
    identifier_attr: IdentifierAttr = Field(default=IdentifierAttr.SLOT_CODE)
    checkout_grace_minutes: int = Field(default=15, ge=0, le=30)
    last_sync_utc: Optional[datetime] = Field(default=None)
    stale_count: int = Field(default=0, ge=0)
    allowed_vlans: list[int] | None = Field(
        default=None,
        sa_column=Column(SA_JSON, nullable=True),
    )

    @field_validator("allowed_vlans", mode="before")
    @classmethod
    def validate_vlans(cls, v: list[int] | None) -> list[int] | None:
        """Validate VLAN IDs are integers in the 1-4094 range."""
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError("allowed_vlans must be a list")
        for vid in v:
            if not isinstance(vid, int) or vid < 1 or vid > 4094:
                raise ValueError(f"Invalid VLAN ID: {vid} (must be 1-4094)")
        return sorted(set(v))
