# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""API routes for Home Assistant integration configuration (admin-only)."""

import logging
from typing import Optional, cast, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlmodel import Session, select

from captive_portal.integrations.ha_discovery_service import (
    DiscoveryResult,
    HADiscoveryService,
)

from captive_portal.models.ha_integration_config import (
    HAIntegrationConfig,
    IdentifierAttr,
)
from captive_portal.persistence.database import get_session
from captive_portal.security.session_middleware import require_admin
from captive_portal.services.audit_service import AuditService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


# Request/Response schemas
class IntegrationConfigCreate(BaseModel):
    """Request schema for creating HA integration configuration."""

    integration_id: str = Field(..., min_length=1, max_length=128)
    identifier_attr: IdentifierAttr = Field(default=IdentifierAttr.SLOT_CODE)
    checkout_grace_minutes: int = Field(default=15, ge=0, le=30)
    allowed_vlans: list[int] = Field(default_factory=list)

    @field_validator("allowed_vlans", mode="before")
    @classmethod
    def coerce_and_validate_vlans(cls, v: list[int] | None) -> list[int]:
        """Coerce None to empty list and validate VLAN IDs."""
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("allowed_vlans must be a list")
        for vid in v:
            if isinstance(vid, bool) or not isinstance(vid, int) or vid < 1 or vid > 4094:
                raise ValueError(f"Invalid VLAN ID: {vid} (must be 1-4094)")
        return sorted(set(v))


class IntegrationConfigUpdate(BaseModel):
    """Request schema for updating HA integration configuration."""

    identifier_attr: Optional[IdentifierAttr] = None
    checkout_grace_minutes: Optional[int] = Field(None, ge=0, le=30)
    allowed_vlans: list[int] | None = None

    @field_validator("allowed_vlans", mode="before")
    @classmethod
    def validate_vlans(cls, v: list[int] | None) -> list[int] | None:
        """Validate VLAN IDs when provided."""
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError("allowed_vlans must be a list")
        for vid in v:
            if isinstance(vid, bool) or not isinstance(vid, int) or vid < 1 or vid > 4094:
                raise ValueError(f"Invalid VLAN ID: {vid} (must be 1-4094)")
        return sorted(set(v))


class IntegrationConfigResponse(BaseModel):
    """Response schema for HA integration configuration."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    integration_id: str
    identifier_attr: IdentifierAttr
    checkout_grace_minutes: int
    last_sync_utc: Optional[str] = None
    stale_count: int
    allowed_vlans: list[int] = Field(default_factory=list)

    @field_validator("allowed_vlans", mode="before")
    @classmethod
    def coerce_none_to_empty(cls, v: list[int] | None) -> list[int]:
        """Coerce None to empty list for response serialization."""
        return v if v is not None else []


@router.post(
    "",
    response_model=IntegrationConfigResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_integration(
    config: IntegrationConfigCreate,
    session: Session = Depends(get_session),
    admin_id: UUID = Depends(require_admin),
) -> HAIntegrationConfig:
    """Create new HA integration configuration.

    Args:
        config: Integration configuration data
        session: Database session
        admin_id: Admin user ID from authentication

    Returns:
        Created integration configuration

    Raises:
        HTTPException: If integration_id already exists (409 Conflict)
    """
    audit_service = AuditService(session)

    # Check for duplicate integration_id
    statement: Any = select(HAIntegrationConfig).where(
        HAIntegrationConfig.integration_id == config.integration_id
    )
    existing: HAIntegrationConfig | None = cast(
        Optional[HAIntegrationConfig], session.exec(statement).first()
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Integration '{config.integration_id}' already exists",
        )

    # Create new configuration
    new_config = HAIntegrationConfig(
        integration_id=config.integration_id,
        identifier_attr=config.identifier_attr,
        checkout_grace_minutes=config.checkout_grace_minutes,
        allowed_vlans=config.allowed_vlans or None,
    )

    session.add(new_config)
    session.commit()
    session.refresh(new_config)

    # Audit log
    await audit_service.log_admin_action(
        admin_id=admin_id,
        action="create_integration",
        target_type="ha_integration",
        target_id=str(new_config.id),
        metadata={
            "integration_id": config.integration_id,
            "identifier_attr": config.identifier_attr.value,
            "checkout_grace_minutes": config.checkout_grace_minutes,
            "allowed_vlans": config.allowed_vlans,
        },
    )

    return new_config


@router.get("", response_model=list[IntegrationConfigResponse])
async def list_integrations(
    session: Session = Depends(get_session),
    _admin: UUID = Depends(require_admin),
) -> list[HAIntegrationConfig]:
    """List all HA integration configurations.

    Args:
        session: Database session
        _admin: Admin authentication dependency

    Returns:
        List of integration configurations
    """
    statement: Any = select(HAIntegrationConfig)
    configs: list[HAIntegrationConfig] = list(
        cast(list[HAIntegrationConfig], session.exec(statement).all())
    )
    return configs


@router.get("/discover")
async def discover_integrations(
    request: Request,
    session: Session = Depends(get_session),
    _admin: UUID = Depends(require_admin),
) -> DiscoveryResult:
    """Discover Rental Control calendar entities from Home Assistant.

    Always returns HTTP 200.  When HA is reachable the result contains
    discovered entities; when not, ``available`` is ``False`` with an
    error message.

    Args:
        request: FastAPI request (provides access to app.state.ha_client).
        session: Database session for cross-referencing configs.
        _admin: Admin authentication dependency.

    Returns:
        DiscoveryResult JSON.
    """
    ha_client = getattr(request.app.state, "ha_client", None)
    if ha_client is None:
        return DiscoveryResult(
            available=False,
            error_message="Home Assistant client not configured",
            error_category="connection",
        )
    service = HADiscoveryService(ha_client, session)
    return await service.discover()


@router.get("/{config_id}", response_model=IntegrationConfigResponse)
async def get_integration(
    config_id: UUID,
    session: Session = Depends(get_session),
    _admin: UUID = Depends(require_admin),
) -> HAIntegrationConfig:
    """Get specific HA integration configuration.

    Args:
        config_id: Integration configuration UUID
        session: Database session
        _admin: Admin authentication dependency

    Returns:
        Integration configuration

    Raises:
        HTTPException: If configuration not found (404)
    """
    config = cast(Optional[HAIntegrationConfig], session.get(HAIntegrationConfig, config_id))

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration configuration {config_id} not found",
        )

    return config


@router.patch("/{config_id}", response_model=IntegrationConfigResponse)
async def update_integration(
    config_id: UUID,
    updates: IntegrationConfigUpdate,
    session: Session = Depends(get_session),
    admin_id: UUID = Depends(require_admin),
) -> HAIntegrationConfig:
    """Update HA integration configuration.

    Args:
        config_id: Integration configuration UUID
        updates: Fields to update
        session: Database session
        admin_id: Admin user ID from authentication

    Returns:
        Updated integration configuration

    Raises:
        HTTPException: If configuration not found (404)
    """
    config = session.get(HAIntegrationConfig, config_id)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration configuration {config_id} not found",
        )

    audit_service = AuditService(session)
    old_vlans = list(config.allowed_vlans or [])

    # Apply updates
    if updates.identifier_attr is not None:
        config.identifier_attr = updates.identifier_attr
    if updates.checkout_grace_minutes is not None:
        config.checkout_grace_minutes = updates.checkout_grace_minutes
    if updates.allowed_vlans is not None:
        config.allowed_vlans = updates.allowed_vlans or None

    session.add(config)
    session.commit()
    session.refresh(config)
    assert isinstance(config, HAIntegrationConfig)

    await audit_service.log_admin_action(
        admin_id=admin_id,
        action="update_integration",
        target_type="ha_integration_config",
        target_id=str(config_id),
        metadata={
            "integration_id": config.integration_id,
            "allowed_vlans_old": old_vlans,
            "allowed_vlans_new": list(config.allowed_vlans or []),
        },
    )

    logger.info(f"Updated HA integration config: {config.integration_id}")

    return config


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(
    config_id: UUID,
    session: Session = Depends(get_session),
    _admin: UUID = Depends(require_admin),
) -> None:
    """Delete HA integration configuration.

    Args:
        config_id: Integration configuration UUID
        session: Database session
        _admin: Admin authentication dependency

    Raises:
        HTTPException: If configuration not found (404)
    """
    config = session.get(HAIntegrationConfig, config_id)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration configuration {config_id} not found",
        )

    session.delete(config)
    session.commit()

    logger.info(f"Deleted HA integration config: {config.integration_id}")
