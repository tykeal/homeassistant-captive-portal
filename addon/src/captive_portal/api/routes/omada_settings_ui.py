# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Admin UI routes for Omada controller settings management.

Provides GET/POST endpoints for the Omada controller configuration
form at ``/admin/omada-settings/``.  Follows the same PRG pattern
as the existing portal-settings page.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Annotated, Any, Optional, cast
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from captive_portal.models.admin_user import AdminUser
from captive_portal.models.omada_config import OmadaConfig
from captive_portal.persistence.database import get_session
from captive_portal.security.credential_encryption import (
    encrypt_credential,
)
from captive_portal.security.csrf import CSRFProtection, get_csrf_protection
from captive_portal.security.session_middleware import require_admin
from captive_portal.services.audit_service import AuditService

logger = logging.getLogger("captive_portal.routes.omada_settings")

router = APIRouter(prefix="/admin/omada-settings", tags=["admin-ui-omada-settings"])
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_CONTROLLER_ID_PATTERN = re.compile(r"^[a-fA-F0-9]{12,64}$")


def _get_current_admin(request: Request, db: Session = Depends(get_session)) -> AdminUser:  # noqa: B008
    """Get currently authenticated admin from session.

    Args:
        request: FastAPI request.
        db: Database session.

    Returns:
        Authenticated admin user.

    Raises:
        HTTPException: If not authenticated or session is invalid.
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


def _get_or_create_omada_config(session: Session) -> OmadaConfig:
    """Load OmadaConfig singleton or create default.

    Args:
        session: Database session.

    Returns:
        OmadaConfig record (id=1).
    """
    stmt: Any = select(OmadaConfig).where(OmadaConfig.id == 1)
    config: Optional[OmadaConfig] = session.exec(stmt).first()
    if not config:
        config = OmadaConfig(id=1)
        session.add(config)
        session.commit()
        session.refresh(config)
    return config


def _get_connection_status(app_state: Any) -> str | None:
    """Determine Omada connection status from app state.

    Args:
        app_state: FastAPI app.state object.

    Returns:
        ``"connected"``, ``"error"``, or ``None`` if not configured.
    """
    omada_cfg = getattr(app_state, "omada_config", None)
    if omada_cfg is None:
        return None
    return "connected"


@router.get("/", response_class=HTMLResponse)
async def get_omada_settings(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_id: Annotated[UUID, Depends(require_admin)],
    csrf: Annotated[CSRFProtection, Depends(get_csrf_protection)],
) -> HTMLResponse:
    """Display Omada controller settings form (admin only).

    Args:
        request: FastAPI request.
        session: Database session.
        admin_id: Authenticated admin user ID.
        csrf: CSRF protection.

    Returns:
        HTML response with Omada settings template.
    """
    csrf_token = csrf.generate_token()
    config = _get_or_create_omada_config(session)

    response = templates.TemplateResponse(
        request=request,
        name="admin/omada_settings.html",
        context={
            "config": config,
            "csrf_token": csrf_token,
            "has_password": bool(config.encrypted_password),
            "connection_status": _get_connection_status(request.app.state),
            "success_message": request.query_params.get("success"),
            "error_message": request.query_params.get("error"),
        },
    )
    csrf.set_csrf_cookie(response, csrf_token)
    return response


def _validate_omada_form(
    controller_url: str,
    username: str,
    controller_id: str,
    password: str,
    password_changed: str,
    base_url: str,
) -> str | None:
    """Validate Omada settings form inputs.

    Returns an error message string if validation fails, or ``None``
    if all inputs are valid.

    Args:
        controller_url: Stripped controller URL.
        username: Stripped username.
        controller_id: Stripped controller ID.
        password: Raw password value.
        password_changed: ``"true"`` or ``"false"``.
        base_url: Redirect base URL (unused in validation logic).

    Returns:
        Error message or None.
    """
    if controller_url:
        parts = urlsplit(controller_url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            return "Controller+URL+must+be+a+valid+HTTP+or+HTTPS+URL"

    if controller_url and not username:
        return "Username+is+required+when+controller+URL+is+set"

    if controller_id and not _CONTROLLER_ID_PATTERN.match(controller_id):
        return "Controller+ID+must+be+a+hex+string+(12-64+characters)"

    if controller_url and password_changed == "true" and not password:
        return "Password+is+required+when+setting+up+a+new+connection"

    return None


@router.post("/", response_class=HTMLResponse)
async def update_omada_settings(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[AdminUser, Depends(_get_current_admin)],
    csrf: Annotated[CSRFProtection, Depends(get_csrf_protection)],
    csrf_token: Annotated[str, Form()],
    controller_url: Annotated[str, Form()] = "",
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    password_changed: Annotated[str, Form()] = "false",
    site_name: Annotated[str, Form()] = "Default",
    controller_id: Annotated[str, Form()] = "",
    verify_ssl: Annotated[Optional[str], Form()] = None,
) -> RedirectResponse:
    """Save Omada controller settings and trigger reconnection.

    Args:
        request: FastAPI request.
        session: Database session.
        current_user: Authenticated admin user.
        csrf: CSRF protection.
        csrf_token: CSRF token from form.
        controller_url: Omada controller URL.
        username: Omada hotspot operator username.
        password: Omada password (only when changed).
        password_changed: Whether the password field was modified.
        site_name: Omada site name.
        controller_id: Omada controller ID (hex).
        verify_ssl: SSL verification checkbox.

    Returns:
        Redirect to settings page with success/error message.
    """
    root = request.scope.get("root_path", "")
    redirect_base = f"{root}/admin/omada-settings/"

    # Only admins can update configuration
    if current_user.role != "admin":
        return RedirectResponse(
            url=f"{redirect_base}?error=Only+administrators+can+modify+Omada+configuration",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Validate CSRF token
    try:
        await csrf.validate_token(request)
    except HTTPException:
        return RedirectResponse(
            url=f"{redirect_base}?error=Invalid+CSRF+token",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Strip inputs
    controller_url = controller_url.strip()
    username = username.strip()
    site_name = site_name.strip() or "Default"
    controller_id = controller_id.strip()

    # Validate form inputs
    error = _validate_omada_form(
        controller_url, username, controller_id, password, password_changed, redirect_base
    )
    if error:
        return RedirectResponse(
            url=f"{redirect_base}?error={error}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Load or create config
    config = _get_or_create_omada_config(session)

    # Update fields
    config.controller_url = controller_url
    config.username = username
    config.site_name = site_name
    config.controller_id = controller_id
    config.verify_ssl = verify_ssl == "true"

    # Handle password
    if password_changed == "true" and password:
        config.encrypted_password = encrypt_credential(password)
    # If password_changed is false, preserve existing encrypted_password

    session.add(config)
    session.commit()

    # Rebuild app.state.omada_config
    error_msg = None
    if config.omada_configured:
        try:
            from captive_portal.config.omada_config import build_omada_config

            new_omada_cfg = await build_omada_config(config, logger)
            request.app.state.omada_config = new_omada_cfg
        except Exception as exc:
            error_msg = f"Settings saved but connection failed: {exc}"
            logger.error("Omada connection error after settings update: %s", exc)
    else:
        request.app.state.omada_config = None

    # Log audit event
    audit_service = AuditService(session)
    await audit_service.log_admin_action(
        admin_id=current_user.id,
        action="omada_config.update",
        target_type="omada_config",
        target_id="1",
        metadata={
            "controller_url": controller_url,
            "username": username,
            "password_changed": password_changed == "true",
            "site_name": site_name,
            "controller_id": controller_id or "auto-discover",
            "verify_ssl": config.verify_ssl,
        },
    )

    if error_msg:
        return RedirectResponse(
            url=f"{redirect_base}?error={error_msg}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"{redirect_base}?success=Omada+controller+settings+saved+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )
