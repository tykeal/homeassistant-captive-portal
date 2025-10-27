# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""API routes for Home Assistant integration configuration (admin-only)."""

import logging
from collections.abc import Generator
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from captive_portal.models.ha_integration_config import (
    HAIntegrationConfig,
    IdentifierAttr,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


# Request/Response schemas
class IntegrationConfigCreate(BaseModel):
    """Request schema for creating HA integration configuration."""

    integration_id: str = Field(..., min_length=1, max_length=128)
    identifier_attr: IdentifierAttr = Field(default=IdentifierAttr.SLOT_CODE)
    checkout_grace_minutes: int = Field(default=15, ge=0, le=30)


class IntegrationConfigUpdate(BaseModel):
    """Request schema for updating HA integration configuration."""

    identifier_attr: Optional[IdentifierAttr] = None
    checkout_grace_minutes: Optional[int] = Field(None, ge=0, le=30)


class IntegrationConfigResponse(BaseModel):
    """Response schema for HA integration configuration."""

    id: UUID
    integration_id: str
    identifier_attr: IdentifierAttr
    checkout_grace_minutes: int
    last_sync_utc: Optional[str] = None
    stale_count: int

    class Config:
        """Pydantic config."""

        from_attributes = True


# Global engine instance - will be initialized by application startup
_engine: Optional[Engine] = None


def set_db_engine(engine: Engine) -> None:
    """Set the global database engine instance.

    This should be called during application startup.

    Args:
        engine: SQLAlchemy engine instance
    """
    global _engine
    _engine = engine


# Dependency: DB session
def get_db_session() -> Generator[Session, None, None]:
    """Get database session dependency.

    Yields:
        SQLModel Session instance

    Raises:
        RuntimeError: If database engine not initialized
    """
    if _engine is None:
        raise RuntimeError("Database engine not initialized. Call set_db_engine() during startup.")
    with Session(_engine) as session:
        yield session


# Dependency: Admin authentication (placeholder - will be implemented in Phase 4)
async def require_admin() -> None:
    """Require admin authentication.

    Raises:
        HTTPException: If not authenticated as admin
    """
    # TODO: Implement actual admin auth check in Phase 4
    pass


@router.post(
    "",
    response_model=IntegrationConfigResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_integration(
    config: IntegrationConfigCreate,
    session: Session = Depends(get_db_session),
    _admin: None = Depends(require_admin),
) -> HAIntegrationConfig:
    """Create new HA integration configuration.

    Args:
        config: Integration configuration data
        session: Database session
        _admin: Admin authentication dependency

    Returns:
        Created integration configuration

    Raises:
        HTTPException: If integration_id already exists (409 Conflict)
    """
    # Check for duplicate integration_id
    existing = session.exec(
        select(HAIntegrationConfig).where(
            HAIntegrationConfig.integration_id == config.integration_id
        )
    ).first()

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
    )

    session.add(new_config)
    session.commit()
    session.refresh(new_config)

    # Audit log
    # TODO: Integrate with AuditService in proper context
    logger.info(f"Created HA integration config: {config.integration_id}")

    return new_config


@router.get("", response_model=list[IntegrationConfigResponse])
async def list_integrations(
    session: Session = Depends(get_db_session),
    _admin: None = Depends(require_admin),
) -> list[HAIntegrationConfig]:
    """List all HA integration configurations.

    Args:
        session: Database session
        _admin: Admin authentication dependency

    Returns:
        List of integration configurations
    """
    configs = session.exec(select(HAIntegrationConfig)).all()
    return list(configs)


@router.get("/{config_id}", response_model=IntegrationConfigResponse)
async def get_integration(
    config_id: UUID,
    session: Session = Depends(get_db_session),
    _admin: None = Depends(require_admin),
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
    config = session.get(HAIntegrationConfig, config_id)

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
    session: Session = Depends(get_db_session),
    _admin: None = Depends(require_admin),
) -> HAIntegrationConfig:
    """Update HA integration configuration.

    Args:
        config_id: Integration configuration UUID
        updates: Fields to update
        session: Database session
        _admin: Admin authentication dependency

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

    # Apply updates
    if updates.identifier_attr is not None:
        config.identifier_attr = updates.identifier_attr
    if updates.checkout_grace_minutes is not None:
        config.checkout_grace_minutes = updates.checkout_grace_minutes

    session.add(config)
    session.commit()
    session.refresh(config)

    logger.info(f"Updated HA integration config: {config.integration_id}")

    return config


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(
    config_id: UUID,
    session: Session = Depends(get_db_session),
    _admin: None = Depends(require_admin),
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
