# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Admin UI routes for Omada controller settings management.

Provides GET/POST endpoints for the Omada controller configuration
form at ``/admin/omada-settings/``.  Follows the same PRG pattern
as the existing portal-settings page.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Any, Optional, cast
from urllib.parse import quote_plus
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from captive_portal._version import __version__
from captive_portal.models.admin_user import AdminUser
from captive_portal.models.omada_config import OmadaConfig
from captive_portal.persistence.database import get_session
from captive_portal.security.credential_encryption import (
    encrypt_credential,
)
from captive_portal.security.csrf import CSRFProtection, get_csrf_protection
from captive_portal.security.session_middleware import require_admin
from captive_portal.services.audit_service import AuditService
from captive_portal.api.routes.omada_settings_helpers import (
    OmadaFormData,
    client_secret_changed_for_audit as _client_secret_changed_for_audit,
    omada_runtime_error_message as _omada_runtime_error_message,
    rebuild_runtime_after_save,
    set_runtime_omada_config as _set_runtime_omada_config,
    test_omada_connection as _test_omada_connection,
    validate_omada_form as _validate_omada_form,
)

__all__ = [
    "_client_secret_changed_for_audit",
    "_omada_runtime_error_message",
    "_set_runtime_omada_config",
    "_test_omada_connection",
    "_validate_omada_form",
    "get_omada_settings",
    "router",
    "update_omada_settings",
]

logger = logging.getLogger("captive_portal.routes.omada_settings")

router = APIRouter(prefix="/admin/omada-settings", tags=["admin-ui-omada-settings"])
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.globals["app_version"] = __version__


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


def _settings_error_redirect(redirect_base: str, message: str) -> RedirectResponse:
    """Build a settings redirect with a URL-encoded error message.

    Args:
        redirect_base: Base URL for the Omada settings page.
        message: User-facing error message to include in the query string.

    Returns:
        Redirect response to the settings page.
    """
    return RedirectResponse(
        url=f"{redirect_base}?error={quote_plus(message)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


async def _rebuild_runtime_after_save(config: OmadaConfig, app_state: Any) -> str | None:
    """Rebuild runtime config using this module's patchable tester.

    Args:
        config: Persisted Omada configuration.
        app_state: FastAPI application state.

    Returns:
        Error message when rebuild or connectivity failed.
    """
    return await rebuild_runtime_after_save(config, app_state, _test_omada_connection)


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
            "connection_status": await _test_omada_connection(request.app.state),
            "success_message": request.query_params.get("success"),
            "error_message": request.query_params.get("error"),
        },
    )
    csrf.set_csrf_cookie(response, csrf_token)
    return response


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
    client_id: Annotated[str, Form()] = "",
    client_secret: Annotated[str, Form()] = "",
    client_secret_changed: Annotated[str, Form()] = "false",
    openapi_mode: Annotated[str, Form()] = "auto",
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
        client_id: OpenAPI client ID.
        client_secret: OpenAPI client secret (only when changed).
        client_secret_changed: Whether the OpenAPI secret field was modified.
        openapi_mode: Backend selection mode.
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
        return _settings_error_redirect(
            redirect_base,
            "Only administrators can modify Omada configuration",
        )

    try:
        await csrf.validate_token(request)
    except HTTPException:
        return _settings_error_redirect(redirect_base, "Invalid CSRF token")

    # Strip inputs
    controller_url = controller_url.strip()
    username = username.strip()
    client_id = client_id.strip()
    openapi_mode = openapi_mode.strip().lower() or "auto"
    site_name = site_name.strip() or "Default"
    controller_id = controller_id.strip()

    existing_stmt: Any = select(OmadaConfig).where(OmadaConfig.id == 1)
    existing_config: Optional[OmadaConfig] = session.exec(existing_stmt).first()
    error = _validate_omada_form(
        OmadaFormData(
            controller_url=controller_url,
            username=username,
            client_id=client_id,
            controller_id=controller_id,
            password=password,
            password_changed=password_changed,
            openapi_mode=openapi_mode,
            client_secret=client_secret,
            client_secret_changed=client_secret_changed,
            client_secret_exists=bool(
                existing_config and existing_config.encrypted_client_secret.strip()
            ),
        )
    )
    if error:
        return _settings_error_redirect(redirect_base, error)

    config = existing_config or _get_or_create_omada_config(session)

    config.controller_url = controller_url
    config.username = username
    config.site_name = site_name
    config.controller_id = controller_id
    config.verify_ssl = verify_ssl == "true"
    config.client_id = client_id
    config.openapi_mode = openapi_mode

    if password_changed == "true" and password:
        config.encrypted_password = encrypt_credential(password)
    # If password_changed is false, preserve existing encrypted_password
    if client_secret:
        config.encrypted_client_secret = encrypt_credential(client_secret)

    session.add(config)
    session.commit()

    # Rebuild app.state.omada_config and test connection
    error_msg = None
    if config.omada_configured or config.openapi_configured:
        error_msg = await _rebuild_runtime_after_save(config, request.app.state)
    else:
        _set_runtime_omada_config(request.app.state, None)

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
            "client_id_set": bool(client_id),
            # aislop-ignore-next-line ai-slop/hardcoded-id -- audit metadata key
            "client_secret_changed": _client_secret_changed_for_audit(
                client_secret,
                client_secret_changed,
            ),
            "openapi_mode": openapi_mode,
            "site_name": site_name,
            "controller_id": controller_id or "auto-discover",
            "verify_ssl": config.verify_ssl,
        },
    )

    if error_msg:
        return _settings_error_redirect(redirect_base, error_msg)

    return RedirectResponse(
        url=f"{redirect_base}?success=Omada+controller+settings+saved+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )
