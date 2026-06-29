# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Admin UI routes for portal configuration management."""

from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Annotated, Any, Optional, cast
from urllib.parse import quote_plus
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.routing import APIRoute
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlmodel import Session, select
from starlette.responses import Response

from captive_portal._version import __version__
from captive_portal.api.routes.admin_redirects import safe_admin_redirect
from captive_portal.models.admin_user import AdminUser
from captive_portal.models.portal_config import PortalConfig
from captive_portal.persistence.database import get_session
from captive_portal.security.csrf import CSRFProtection, get_csrf_protection
from captive_portal.security.session_middleware import (
    refresh_runtime_session_config,
    require_admin,
)
from captive_portal.services.audit_service import AuditService
from captive_portal.services.redirect_validator import GuestExternalUrlValidator

_REQUIRED_FORM_FIELDS = frozenset(
    {
        "csrf_token",
        "rate_limit_attempts",
        "rate_limit_window_seconds",
        "success_redirect_url",
    }
)


class PortalSettingsValidationRoute(APIRoute):
    """Route class preserving legacy validation payloads for form models."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        """Return a route handler that normalizes form-model validation errors."""
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            """Handle requests and preserve individual-form missing-field errors."""
            try:
                return await original_route_handler(request)
            except RequestValidationError as exc:
                normalized_exc = _normalize_missing_form_field_errors(exc)
                if normalized_exc is exc:
                    raise
                raise normalized_exc from exc

        return custom_route_handler


def _normalize_missing_form_field_errors(exc: RequestValidationError) -> RequestValidationError:
    """Normalize required form-model errors to legacy individual-field errors."""
    normalized_errors: list[Any] = []
    changed = False
    for error in exc.errors():
        normalized_error = dict(error)
        loc = normalized_error.get("loc", ())
        if (
            normalized_error.get("type") == "missing"
            and len(loc) == 2
            and loc[0] == "body"
            and loc[1] in _REQUIRED_FORM_FIELDS
            and isinstance(normalized_error.get("input"), dict)
        ):
            normalized_error["input"] = None
            changed = True
        normalized_errors.append(normalized_error)

    if not changed:
        return exc
    return RequestValidationError(normalized_errors, body=exc.body)


router = APIRouter(
    prefix="/admin/portal-settings",
    tags=["admin-ui-portal-settings"],
    route_class=PortalSettingsValidationRoute,
)
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.globals["app_version"] = __version__


class PortalSettingsForm(BaseModel):
    """Portal settings form data submitted by the admin UI."""

    csrf_token: str
    rate_limit_attempts: int
    rate_limit_window_seconds: int
    success_redirect_url: str
    redirect_to_original_url: Optional[str] = None
    session_idle_minutes: int = 30
    session_max_hours: int = 8
    guest_external_url: str = ""


def _settings_redirect(root: str, message_type: str, message: str) -> RedirectResponse:
    """Build a portal settings redirect response.

    Args:
        root: Application root path.
        message_type: Query parameter name for the redirect message.
        message: Already URL-encoded query parameter value.

    Returns:
        Redirect response to the portal settings UI.
    """
    return safe_admin_redirect(root, f"/admin/portal-settings?{message_type}={message}")


def _validate_portal_settings_form(
    root: str,
    form: PortalSettingsForm,
) -> tuple[RedirectResponse | None, str]:
    """Validate portal settings values that must redirect on failure.

    Args:
        root: Application root path.
        form: Submitted portal settings form data.

    Returns:
        A validation redirect when invalid, otherwise the normalized guest URL.
    """
    if form.rate_limit_attempts < 1 or form.rate_limit_attempts > 1000:
        return (
            _settings_redirect(
                root,
                "error",
                "Rate+limit+attempts+must+be+between+1+and+1000",
            ),
            "",
        )

    if form.rate_limit_window_seconds < 1 or form.rate_limit_window_seconds > 3600:
        return (
            _settings_redirect(
                root,
                "error",
                "Rate+limit+window+must+be+between+1+and+3600+seconds",
            ),
            "",
        )

    if len(form.success_redirect_url) > 2048:
        return (
            _settings_redirect(
                root,
                "error",
                "Redirect+URL+too+long+(max+2048+characters)",
            ),
            "",
        )

    if form.session_idle_minutes < 1 or form.session_idle_minutes > 1440:
        return (
            _settings_redirect(
                root,
                "error",
                "Session+idle+timeout+must+be+between+1+and+1440+minutes",
            ),
            "",
        )

    if form.session_max_hours < 1 or form.session_max_hours > 168:
        return (
            _settings_redirect(
                root,
                "error",
                "Session+max+duration+must+be+between+1+and+168+hours",
            ),
            "",
        )

    guest_url_validation = GuestExternalUrlValidator.validate(form.guest_external_url)
    if not guest_url_validation.valid:
        return (
            _settings_redirect(
                root,
                "error",
                quote_plus(guest_url_validation.error_message or ""),
            ),
            "",
        )

    return None, guest_url_validation.normalized_url


def _get_or_create_portal_config(session: Session) -> PortalConfig:
    """Get the singleton portal config, creating it when absent.

    Args:
        session: Database session.

    Returns:
        Portal configuration row.
    """
    stmt: Any = select(PortalConfig).where(PortalConfig.id == 1)
    config: Optional[PortalConfig] = session.exec(stmt).first()

    if not config:
        config = PortalConfig(id=1)
        session.add(config)

    return config


def _apply_portal_settings_form(
    config: PortalConfig,
    form: PortalSettingsForm,
    guest_external_url: str,
) -> None:
    """Apply submitted portal settings to a configuration row.

    Args:
        config: Portal configuration row to update.
        form: Submitted portal settings form data.
        guest_external_url: Normalized guest external URL.
    """
    config.rate_limit_attempts = form.rate_limit_attempts
    config.rate_limit_window_seconds = form.rate_limit_window_seconds
    config.success_redirect_url = form.success_redirect_url
    config.redirect_to_original_url = form.redirect_to_original_url == "true"
    config.session_idle_minutes = form.session_idle_minutes
    config.session_max_hours = form.session_max_hours
    config.guest_external_url = guest_external_url


async def _log_portal_settings_update(
    session: Session,
    current_user: AdminUser,
    config: PortalConfig,
    form: PortalSettingsForm,
) -> None:
    """Record the portal settings update in the audit log.

    Args:
        session: Database session.
        current_user: Authenticated admin user.
        config: Updated portal configuration row.
        form: Submitted portal settings form data.
    """
    audit_service = AuditService(session)
    await audit_service.log_admin_action(
        admin_id=current_user.id,
        action="portal_config.update",
        target_type="portal_config",
        target_id="1",
        metadata={
            "rate_limit_attempts": form.rate_limit_attempts,
            "rate_limit_window_seconds": form.rate_limit_window_seconds,
            "redirect_to_original_url": config.redirect_to_original_url,
            "session_idle_minutes": form.session_idle_minutes,
            "session_max_hours": form.session_max_hours,
            "guest_external_url": config.guest_external_url,
        },
    )


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
    stmt: Any = select(PortalConfig).where(PortalConfig.id == 1)
    config: Optional[PortalConfig] = session.exec(stmt).first()

    if not config:
        # Create default config if it doesn't exist
        config = PortalConfig(id=1)
        session.add(config)
        session.commit()
        session.refresh(config)

    response = templates.TemplateResponse(
        request=request,
        name="admin/portal_settings.html",
        context={
            "config": config,
            "csrf_token": csrf_token,
            "success_message": request.query_params.get("success"),
            "error_message": request.query_params.get("error"),
        },
    )
    csrf.set_csrf_cookie(response, csrf_token)
    return response


@router.post("/", response_class=RedirectResponse)
async def update_portal_settings(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[AdminUser, Depends(get_current_admin)],
    csrf: Annotated[CSRFProtection, Depends(get_csrf_protection)],
    form: Annotated[PortalSettingsForm, Form()],
) -> RedirectResponse:
    """Update portal configuration settings (admin only).

    Args:
        request: FastAPI request
        session: Database session
        current_user: Authenticated admin user
        csrf: CSRF protection
        form: Portal settings form data

    Returns:
        Redirect to settings page

    Raises:
        403: User is not admin
        400: Invalid CSRF token
    """
    root = request.scope.get("root_path", "")

    # Only admins can update configuration
    if current_user.role != "admin":
        return _settings_redirect(
            root,
            "error",
            "Only+administrators+can+modify+portal+configuration",
        )

    try:
        await csrf.validate_token(request)
    except HTTPException:
        return _settings_redirect(
            root,
            "error",
            "Invalid+CSRF+token",
        )

    validation_redirect, guest_external_url = _validate_portal_settings_form(root, form)
    if validation_redirect is not None:
        return validation_redirect

    config = _get_or_create_portal_config(session)
    _apply_portal_settings_form(config, form, guest_external_url)

    session.add(config)
    session.commit()
    refresh_runtime_session_config(
        request.app.state,
        config.session_idle_minutes,
        config.session_max_hours,
    )

    await _log_portal_settings_update(session, current_user, config, form)

    return _settings_redirect(
        root,
        "success",
        "Portal+configuration+updated+successfully",
    )
