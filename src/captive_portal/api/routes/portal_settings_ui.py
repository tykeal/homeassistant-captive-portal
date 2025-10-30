# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Admin UI routes for portal configuration management."""

from typing import Annotated, Any, Optional, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from captive_portal.models.admin_user import AdminUser
from captive_portal.models.portal_config import PortalConfig
from captive_portal.persistence.database import get_session
from captive_portal.security.csrf import CSRFProtection, get_csrf_protection
from captive_portal.security.session_middleware import require_admin
from captive_portal.services.audit_service import AuditService

router = APIRouter(prefix="/admin/portal-settings", tags=["admin-ui-portal-settings"])
templates = Jinja2Templates(directory="src/captive_portal/web/templates")


def get_current_admin(request: Request, db: Session = Depends(get_session)) -> AdminUser:
    """Get currently authenticated admin from session.

    Args:
        request: FastAPI request
        db: Database session

    Returns:
        Authenticated admin user

    Raises:
        HTTP 401: Not authenticated
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


@router.get("/", response_class=HTMLResponse)
async def get_portal_settings(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_id: Annotated[UUID, Depends(require_admin)],
    csrf: Annotated[CSRFProtection, Depends(get_csrf_protection)],
) -> HTMLResponse:
    """Display portal configuration settings (admin only).

    Args:
        request: FastAPI request
        session: Database session
        admin_id: Authenticated admin user ID
        csrf: CSRF protection

    Returns:
        HTML response with portal settings template
    """
    csrf_token = csrf.generate_token()

    # Get singleton config (id=1)
    config = session.exec(select(PortalConfig).where(PortalConfig.id == 1)).first()

    if not config:
        # Create default config if it doesn't exist
        config = PortalConfig(id=1)
        session.add(config)
        session.commit()
        session.refresh(config)

    return templates.TemplateResponse(
        request=request,
        name="admin/portal_settings.html",
        context={
            "config": config,
            "csrf_token": csrf_token,
            "success_message": request.query_params.get("success"),
            "error_message": request.query_params.get("error"),
        },
    )


@router.post("/", response_class=HTMLResponse)
async def update_portal_settings(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[AdminUser, Depends(get_current_admin)],
    csrf: Annotated[CSRFProtection, Depends(get_csrf_protection)],
    csrf_token: Annotated[str, Form()],
    rate_limit_attempts: Annotated[int, Form()],
    rate_limit_window_seconds: Annotated[int, Form()],
    success_redirect_url: Annotated[str, Form()],
    redirect_to_original_url: Annotated[Optional[str], Form()] = None,
) -> RedirectResponse:
    """Update portal configuration settings (admin only).

    Args:
        request: FastAPI request
        session: Database session
        current_user: Authenticated admin user
        csrf: CSRF protection
        csrf_token: CSRF token from form
        rate_limit_attempts: Max attempts per IP
        rate_limit_window_seconds: Rolling window in seconds
        success_redirect_url: Default redirect URL
        redirect_to_original_url: Checkbox value (present if checked)

    Returns:
        Redirect to settings page

    Raises:
        403: User is not admin
        400: Invalid CSRF token
    """
    # Only admins can update configuration
    if current_user.role != "admin":
        return RedirectResponse(
            url="/admin/portal-settings?error=Only+administrators+can+modify+portal+configuration",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Validate CSRF token
    try:
        await csrf.validate_token(request)
    except HTTPException:
        return RedirectResponse(
            url="/admin/portal-settings?error=Invalid+CSRF+token",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Validate input ranges
    if rate_limit_attempts < 1 or rate_limit_attempts > 1000:
        return RedirectResponse(
            url="/admin/portal-settings?error=Rate+limit+attempts+must+be+between+1+and+1000",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if rate_limit_window_seconds < 1 or rate_limit_window_seconds > 3600:
        return RedirectResponse(
            url="/admin/portal-settings?error=Rate+limit+window+must+be+between+1+and+3600+seconds",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if len(success_redirect_url) > 2048:
        return RedirectResponse(
            url="/admin/portal-settings?error=Redirect+URL+too+long+(max+2048+characters)",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Get singleton config
    config = session.exec(select(PortalConfig).where(PortalConfig.id == 1)).first()

    if not config:
        # Create config with provided values
        config = PortalConfig(id=1)
        session.add(config)

    # Apply updates
    config.rate_limit_attempts = rate_limit_attempts
    config.rate_limit_window_seconds = rate_limit_window_seconds
    config.success_redirect_url = success_redirect_url
    config.redirect_to_original_url = redirect_to_original_url == "true"

    session.add(config)
    session.commit()

    # Log audit event
    audit_service = AuditService(session)
    await audit_service.log_admin_action(
        admin_id=current_user.id,
        action="portal_config.update",
        target_type="portal_config",
        target_id="1",
        metadata={
            "rate_limit_attempts": rate_limit_attempts,
            "rate_limit_window_seconds": rate_limit_window_seconds,
            "redirect_to_original_url": config.redirect_to_original_url,
        },
    )

    return RedirectResponse(
        url="/admin/portal-settings?success=Portal+configuration+updated+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )
