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

logger = logging.getLogger("captive_portal.routes.omada_settings")

router = APIRouter(prefix="/admin/omada-settings", tags=["admin-ui-omada-settings"])
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.globals["app_version"] = __version__

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


async def _test_omada_connection(app_state: Any) -> str | None:
    """Test live connectivity to the Omada controller.

    Attempts an actual API login using the credentials stored in
    ``app.state.omada_config``.  Returns ``"connected"`` on success,
    ``"error"`` on failure, or ``None`` when Omada is not configured.

    Args:
        app_state: FastAPI app.state object.

    Returns:
        ``"connected"``, ``"error"``, or ``None`` if not configured.
    """
    omada_cfg: dict[str, Any] | None = getattr(app_state, "omada_config", None)
    if omada_cfg is None:
        return None

    from captive_portal.controllers.tp_omada.adapter_factory import OmadaRuntimeConfig
    from captive_portal.controllers.tp_omada.base_client import OmadaClientError

    if isinstance(omada_cfg, OmadaRuntimeConfig):
        if omada_cfg.selected_backend == "openapi":
            from captive_portal.controllers.tp_omada.openapi_client import OpenApiClient

            try:
                await OpenApiClient(
                    base_url=omada_cfg.base_url,
                    controller_id=omada_cfg.controller_id,
                    client_id=omada_cfg.client_id,
                    client_secret=omada_cfg.client_secret,
                    verify_ssl=omada_cfg.verify_ssl,
                    token_state=omada_cfg.token_state,
                ).get_access_token()
                return "connected"
            except OmadaClientError as exc:
                logger.warning("Omada OpenAPI connection test failed: %s", exc)
                return "error"
        legacy_cfg: dict[str, Any] = {
            "base_url": omada_cfg.base_url,
            "controller_id": omada_cfg.controller_id,
            "username": omada_cfg.username,
            "password": omada_cfg.password,
            "verify_ssl": omada_cfg.verify_ssl,
        }
    else:
        legacy_cfg = omada_cfg

    from captive_portal.controllers.tp_omada.base_client import OmadaClient

    try:
        async with OmadaClient(
            base_url=legacy_cfg["base_url"],
            controller_id=legacy_cfg["controller_id"],
            username=legacy_cfg["username"],
            password=legacy_cfg["password"],
            verify_ssl=legacy_cfg.get("verify_ssl", True),
            timeout=10.0,
        ):
            pass  # login succeeded inside __aenter__
        return "connected"
    except OmadaClientError as exc:
        logger.warning("Omada connection test failed: %s", exc)
        return "error"
    except Exception as exc:
        logger.warning("Omada connection test error: %s", exc)
        return "error"


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


def _validate_omada_form(
    controller_url: str,
    username: str,
    client_id: str,
    controller_id: str,
    password: str,
    password_changed: str,
    openapi_mode: str,
    client_secret: str,
    client_secret_changed: str,
    base_url: str,
    client_secret_exists: bool = False,
) -> str | None:
    """Validate Omada settings form inputs.

    Returns an error message string if validation fails, or ``None``
    if all inputs are valid.

    Args:
        controller_url: Stripped controller URL.
        username: Stripped username.
        client_id: Stripped OpenAPI client ID.
        controller_id: Stripped controller ID.
        password: Raw password value.
        password_changed: ``"true"`` or ``"false"``.
        openapi_mode: Backend mode.
        client_secret: Raw OpenAPI client secret.
        client_secret_changed: Whether the OpenAPI secret field changed.
        base_url: Redirect base URL (unused in validation logic).
        client_secret_exists: Whether an encrypted OpenAPI secret is already stored.

    Returns:
        Error message or None.
    """
    if controller_url:
        parts = urlsplit(controller_url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            return "Controller+URL+must+be+a+valid+HTTP+or+HTTPS+URL"

    if openapi_mode not in {"auto", "openapi", "legacy"}:
        return "Backend+mode+must+be+auto,+openapi,+or+legacy"

    openapi_secret_available = bool(client_id) and bool(client_secret or client_secret_exists)
    legacy_required = openapi_mode == "legacy" or (
        openapi_mode == "auto" and not openapi_secret_available
    )

    if controller_url and legacy_required and not username:
        return "Username+is+required+when+controller+URL+is+set"

    if controller_id and not _CONTROLLER_ID_PATTERN.match(controller_id):
        return "Controller+ID+must+be+a+hex+string+(12-64+characters)"

    if controller_url and legacy_required and password_changed == "true" and not password:
        return "Password+is+required+when+setting+up+a+new+connection"

    if openapi_mode == "openapi" and not client_id:
        return "Client+ID+is+required+for+OpenAPI+mode"

    if openapi_mode == "openapi" and not openapi_secret_available:
        return "Client+Secret+is+required+for+OpenAPI+mode"

    return None


def _set_runtime_omada_config(state: Any, runtime_config: Any) -> None:
    """Update runtime Omada config everywhere it is cached.

    Args:
        state: FastAPI application state.
        runtime_config: Selected Omada runtime config or ``None``.
    """
    state.omada_config = runtime_config
    expiry_service = getattr(state, "grant_expiry_service", None)
    if expiry_service is not None:
        expiry_service.omada_config = runtime_config


def _client_secret_changed_for_audit(client_secret: str, client_secret_changed: str) -> bool:
    """Return whether audit metadata should record a secret update.

    Args:
        client_secret: Submitted OpenAPI client secret.
        client_secret_changed: Hidden form field indicating a changed secret.

    Returns:
        True only when a non-empty secret was submitted.
    """
    del client_secret_changed
    return bool(client_secret)


def _omada_runtime_error_message(runtime_config: Any) -> str | None:
    """Return settings error text when runtime config rebuild failed.

    Args:
        runtime_config: Runtime Omada config returned by the builder.

    Returns:
        URL-encoded error message when config is unusable, otherwise ``None``.
    """
    if runtime_config is None:
        return "Settings+saved+but+configuration+error"
    return None


async def _rebuild_runtime_after_save(config: OmadaConfig, app_state: Any) -> str | None:
    """Rebuild runtime Omada config and test connectivity after save.

    Args:
        config: Persisted Omada configuration.
        app_state: FastAPI application state.

    Returns:
        URL-encoded error message when rebuild or connectivity failed.
    """
    try:
        from captive_portal.config.omada_config import build_omada_config

        new_omada_cfg = await build_omada_config(config, logger)
        _set_runtime_omada_config(app_state, new_omada_cfg)
        error_msg = _omada_runtime_error_message(new_omada_cfg)
        if error_msg is not None:
            return error_msg
        if await _test_omada_connection(app_state) == "error":
            return (
                "Settings+saved+but+connection+test+failed+-+check+controller+URL+and+credentials"
            )
    except Exception as exc:
        logger.error(
            "Omada config build error after settings update: %s",
            exc,
        )
        return "Settings+saved+but+configuration+error"
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
        return RedirectResponse(
            url=f"{redirect_base}?error=Only+administrators+can+modify+Omada+configuration",
            status_code=status.HTTP_303_SEE_OTHER,
        )

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
    client_id = client_id.strip()
    openapi_mode = openapi_mode.strip().lower() or "auto"
    site_name = site_name.strip() or "Default"
    controller_id = controller_id.strip()

    existing_stmt: Any = select(OmadaConfig).where(OmadaConfig.id == 1)
    existing_config: Optional[OmadaConfig] = session.exec(existing_stmt).first()
    error = _validate_omada_form(
        controller_url,
        username,
        client_id,
        controller_id,
        password,
        password_changed,
        openapi_mode,
        client_secret,
        client_secret_changed,
        redirect_base,
        client_secret_exists=bool(
            existing_config and existing_config.encrypted_client_secret.strip()
        ),
    )
    if error:
        return RedirectResponse(
            url=f"{redirect_base}?error={error}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

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
        # aislop-ignore-next-line ai-slop/hardcoded-id -- singleton config audit target
        target_id="1",
        metadata={
            "controller_url": controller_url,
            "username": username,
            "password_changed": password_changed == "true",
            # aislop-ignore-next-line ai-slop/hardcoded-id -- audit metadata key
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
        return RedirectResponse(
            url=f"{redirect_base}?error={error_msg}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"{redirect_base}?success=Omada+controller+settings+saved+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )
