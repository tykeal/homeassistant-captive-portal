# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Guest booking code validation and authorization endpoint."""

import logging
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from captive_portal.models.access_grant import AccessGrant
from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.models.rental_control_event import RentalControlEvent
from captive_portal.services.booking_code_validator import (
    BookingCodeValidator,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/guest", tags=["guest"])


# Request/Response schemas
class BookingAuthorizeRequest(BaseModel):
    """Request schema for guest booking code authorization."""

    booking_code: str = Field(..., min_length=1, max_length=255)
    mac_address: str = Field(..., min_length=17, max_length=17)


class BookingAuthorizeResponse(BaseModel):
    """Response schema for successful booking authorization."""

    grant_id: str
    mac_address: str
    start_utc: str
    end_utc: str
    message: str


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


@router.post(
    "/authorize",
    response_model=BookingAuthorizeResponse,
    status_code=status.HTTP_200_OK,
)
async def authorize_booking(
    request: BookingAuthorizeRequest,
    session: Session = Depends(get_db_session),
) -> BookingAuthorizeResponse:
    """Authorize guest access using booking code.

    Guest endpoint - no authentication required.
    Validates booking code against Rental Control events and creates access grant.

    Args:
        request: Booking code and MAC address
        session: Database session

    Returns:
        Access grant details

    Raises:
        HTTPException:
            - 400 Bad Request: Invalid booking code format
            - 404 Not Found: Booking code not found
            - 409 Conflict: Duplicate authorization (idempotent)
            - 410 Gone: Booking outside valid window
            - 503 Service Unavailable: HA integration unavailable
    """
    # For now, simplified implementation - full implementation in Phase 5
    # This is a placeholder that validates the structure

    # Get all integrations (simplified - should use proper lookup)
    integrations = session.exec(select(HAIntegrationConfig)).all()

    if not integrations:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No HA integrations configured",
        )

    # Try to find booking code across all integrations
    event: Optional[RentalControlEvent] = None
    matching_integration: Optional[HAIntegrationConfig] = None

    validator = BookingCodeValidator(session)

    for integration in integrations:
        event = validator.validate_code(request.booking_code, integration)
        if event:
            matching_integration = integration
            break

    if not event or not matching_integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking code not found",
        )

    # Check if booking is within valid time window
    now_utc = datetime.now(timezone.utc)

    # Apply grace period (only applied here at grant creation)
    grace_minutes = matching_integration.checkout_grace_minutes
    effective_end = event.end_utc + timedelta(minutes=grace_minutes)
    # Note: Grace period extends access but doesn't modify stored booking window

    if now_utc < event.start_utc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"Booking has not started yet. Start time: {event.start_utc.isoformat()}",
        )
    if now_utc > effective_end:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"Booking has ended. End time: {effective_end.isoformat()}",
        )

    # Check for existing grant (idempotency)
    existing_grant = session.exec(
        select(AccessGrant).where(AccessGrant.booking_ref == request.booking_code)
    ).first()

    if existing_grant:
        logger.info(f"Duplicate authorization attempt for booking {request.booking_code}")
        return BookingAuthorizeResponse(
            grant_id=str(existing_grant.id),
            mac_address=existing_grant.mac,
            start_utc=existing_grant.start_utc.isoformat(),
            end_utc=existing_grant.end_utc.isoformat(),
            message="Access already granted (existing authorization)",
        )

    # Create new access grant
    grant = AccessGrant(
        id=uuid4(),
        mac=request.mac_address,
        start_utc=event.start_utc,
        end_utc=effective_end,
        booking_ref=request.booking_code,
        created_utc=now_utc,
    )

    session.add(grant)
    session.commit()
    session.refresh(grant)

    logger.info(f"Created access grant {grant.id} for booking {request.booking_code}")

    return BookingAuthorizeResponse(
        grant_id=str(grant.id),
        mac_address=grant.mac,
        start_utc=grant.start_utc.isoformat(),
        end_utc=grant.end_utc.isoformat(),
        message="Access granted successfully",
    )
