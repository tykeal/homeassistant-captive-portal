# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Portal configuration API endpoints."""

from typing import Annotated, Any, Optional, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from captive_portal.models.admin_user import AdminUser
from captive_portal.models.portal_config import PortalConfig
from captive_portal.persistence.database import get_session
from captive_portal.security.session_middleware import require_admin

router = APIRouter(prefix="/admin/portal-config", tags=["portal_config"])


def get_current_admin(request: Request, db: Session = Depends(get_session)) -> AdminUser:
    """Get currently authenticated admin from session.

    Raises HTTP 401 if not authenticated.
    """
    if not hasattr(request.state, "admin_id") or not request.state.admin_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    stmt: Any = select(AdminUser).where(AdminUser.id == request.state.admin_id)
    admin = cast(Optional[AdminUser], db.exec(stmt).first())

    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin session invalid",
        )

    return admin


class PortalConfigResponse(BaseModel):
    """Portal configuration response model."""

    id: int
    success_redirect_url: str
    rate_limit_attempts: int
    rate_limit_window_seconds: int
    redirect_to_original_url: bool


class PortalConfigUpdate(BaseModel):
    """Portal configuration update request model."""

    success_redirect_url: str | None = Field(None, max_length=2048)
    rate_limit_attempts: int | None = Field(None, ge=1, le=1000)
    rate_limit_window_seconds: int | None = Field(None, ge=1, le=3600)
    redirect_to_original_url: bool | None = None


@router.get("", response_model=PortalConfigResponse)
async def get_portal_config(
    session: Annotated[Session, Depends(get_session)],
    admin_id: Annotated[UUID, Depends(require_admin)],
    request: Request,
) -> PortalConfigResponse:
    """
    Get portal configuration.

    Requires authentication. Any role can view configuration.
    """
    # Get singleton config (id=1)
    config = session.exec(select(PortalConfig).where(PortalConfig.id == 1)).first()

    if not config:
        # Create default config if it doesn't exist
        config = PortalConfig(id=1)
        session.add(config)
        session.commit()
        session.refresh(config)

    return PortalConfigResponse(
        id=config.id,
        success_redirect_url=config.success_redirect_url,
        rate_limit_attempts=config.rate_limit_attempts,
        rate_limit_window_seconds=config.rate_limit_window_seconds,
        redirect_to_original_url=config.redirect_to_original_url,
    )


@router.put("", response_model=PortalConfigResponse)
async def update_portal_config(
    updates: PortalConfigUpdate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[AdminUser, Depends(get_current_admin)],
    request: Request,
) -> PortalConfigResponse:
    """
    Update portal configuration.

    Requires admin role. Viewer and operator roles cannot modify configuration.
    """
    # Only admins can update configuration
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Only administrators can modify portal configuration",
        )

    # Get singleton config
    config = session.exec(select(PortalConfig).where(PortalConfig.id == 1)).first()

    if not config:
        # Create config with provided updates
        config = PortalConfig(id=1)
        session.add(config)

    # Apply updates (only non-None fields)
    if updates.success_redirect_url is not None:
        config.success_redirect_url = updates.success_redirect_url
    if updates.rate_limit_attempts is not None:
        config.rate_limit_attempts = updates.rate_limit_attempts
    if updates.rate_limit_window_seconds is not None:
        config.rate_limit_window_seconds = updates.rate_limit_window_seconds
    if updates.redirect_to_original_url is not None:
        config.redirect_to_original_url = updates.redirect_to_original_url

    session.add(config)
    session.commit()
    session.refresh(config)

    return PortalConfigResponse(
        id=config.id,
        success_redirect_url=config.success_redirect_url,
        rate_limit_attempts=config.rate_limit_attempts,
        rate_limit_window_seconds=config.rate_limit_window_seconds,
        redirect_to_original_url=config.redirect_to_original_url,
    )
