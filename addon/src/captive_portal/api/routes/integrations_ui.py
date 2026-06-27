# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Admin UI routes for Home Assistant integration management."""

import logging
from pathlib import Path
from typing import Any, Optional, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from captive_portal._version import __version__
from captive_portal.integrations.ha_discovery_service import (
    DiscoveryResult,
    HADiscoveryService,
)
from captive_portal.models.ha_integration_config import (
    HAIntegrationConfig,
    IdentifierAttr,
)
from captive_portal.persistence.database import get_session
from captive_portal.security.csrf import CSRFProtection, get_csrf_protection
from captive_portal.security.session_middleware import require_admin
from captive_portal.services.audit_service import AuditService
from captive_portal.api.routes.integrations_helpers import (
    IntegrationSaveData,
    create_integration_record,
    integrations_redirect,
    parse_allowed_vlans,
    update_integration_record,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/integrations", tags=["admin-ui-integrations"])
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.globals["app_version"] = __version__


async def _run_discovery(request: Request, session: Session) -> DiscoveryResult:
    """Run HA discovery if an HAClient is available on app state.

    Args:
        request: FastAPI request (provides access to app.state).
        session: Database session for cross-referencing configured integrations.

    Returns:
        DiscoveryResult from the discovery service, or an unavailable
        result if no HAClient is configured.
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


@router.get("/", response_class=HTMLResponse)
async def list_integrations(
    request: Request,
    session: Session = Depends(get_session),
    admin_id: UUID = Depends(require_admin),
    csrf: CSRFProtection = Depends(get_csrf_protection),
) -> HTMLResponse:
    """Display integrations list and form (admin only).

    Args:
        request: FastAPI request
        session: Database session
        admin_id: Authenticated admin user ID
        csrf: CSRF protection

    Returns:
        HTML response with integrations template
    """
    existing_token = csrf.get_token_from_request(request)
    need_csrf_cookie = existing_token is None
    csrf_token: str = existing_token if existing_token is not None else csrf.generate_token()

    success_message = request.query_params.get("success")
    error_message = request.query_params.get("error")

    statement: Any = select(HAIntegrationConfig)
    integrations = list(cast(list[HAIntegrationConfig], session.exec(statement).all()))

    discovery_result = await _run_discovery(request, session)

    response = templates.TemplateResponse(
        request=request,
        name="admin/integrations.html",
        context={
            "integrations": integrations,
            "integration": None,
            "csrf_token": csrf_token,
            "discovery_result": discovery_result,
            "success_message": success_message,
            "error_message": error_message,
        },
    )
    if need_csrf_cookie:
        csrf.set_csrf_cookie(response, csrf_token)
    return response


@router.get("/edit/{integration_id}", response_class=HTMLResponse)
async def edit_integration(
    request: Request,
    integration_id: UUID,
    session: Session = Depends(get_session),
    admin_id: UUID = Depends(require_admin),
    csrf: CSRFProtection = Depends(get_csrf_protection),
) -> HTMLResponse:
    """Display integration edit form (admin only).

    Args:
        request: FastAPI request
        integration_id: Integration UUID
        session: Database session
        admin_id: Authenticated admin user ID
        csrf: CSRF protection

    Returns:
        HTML response with integrations template

    Raises:
        404: Integration not found
    """
    integration = session.get(HAIntegrationConfig, integration_id)
    if not integration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")

    existing_token = csrf.get_token_from_request(request)
    need_csrf_cookie = existing_token is None
    csrf_token: str = existing_token if existing_token is not None else csrf.generate_token()

    statement: Any = select(HAIntegrationConfig)
    integrations = list(cast(list[HAIntegrationConfig], session.exec(statement).all()))

    discovery_result = await _run_discovery(request, session)

    response = templates.TemplateResponse(
        request=request,
        name="admin/integrations.html",
        context={
            "integrations": integrations,
            "integration": integration,
            "csrf_token": csrf_token,
            "discovery_result": discovery_result,
        },
    )
    if need_csrf_cookie:
        csrf.set_csrf_cookie(response, csrf_token)
    return response


def _resolve_identifier_attr(
    identifier_attr: Optional[str],
    auth_attribute: Optional[str],
) -> IdentifierAttr:
    """Resolve identifier_attr from form fields with backward compatibility.

    Prefers ``identifier_attr`` when present; falls back to the legacy
    ``auth_attribute`` field.

    Args:
        identifier_attr: New form field value (may be None).
        auth_attribute: Legacy form field value (may be None).

    Returns:
        IdentifierAttr enum value.

    Raises:
        HTTPException: If neither field is provided or value is invalid.
    """
    raw = identifier_attr or auth_attribute
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="identifier_attr or auth_attribute is required",
        )
    try:
        return IdentifierAttr(raw)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid identifier_attr value: {raw}",
        )


@router.post("/save")
async def save_integration(
    request: Request,
    integration_id: str = Form(...),
    checkout_grace_minutes: int = Form(...),
    identifier_attr: Optional[str] = Form(None),
    auth_attribute: Optional[str] = Form(None),
    allowed_vlans: Optional[str] = Form(None),
    id: UUID | None = Form(None),
    session: Session = Depends(get_session),
    admin_id: UUID = Depends(require_admin),
    csrf: CSRFProtection = Depends(get_csrf_protection),
) -> RedirectResponse:
    """Save or update integration configuration (admin only).

    Accepts both ``identifier_attr`` (preferred) and ``auth_attribute``
    (legacy) form fields for backward compatibility.

    Args:
        request: FastAPI request
        integration_id: HA integration identifier
        checkout_grace_minutes: Checkout grace period
        identifier_attr: Identifier attribute (new field name)
        auth_attribute: Legacy field name (backward compat)
        allowed_vlans: Comma-separated VLAN IDs (e.g. "50,51,52")
        id: Optional existing integration UUID (for updates)
        session: Database session
        admin_id: Authenticated admin user ID
        csrf: CSRF protection

    Returns:
        303 redirect to integrations page with success or error message.
    """
    root = request.scope.get("root_path", "")

    try:
        await csrf.validate_token(request)
    except HTTPException:
        logger.warning("CSRF validation failed for integration save")
        return integrations_redirect(root, "error", "Invalid CSRF token")

    try:
        resolved_attr = _resolve_identifier_attr(identifier_attr, auth_attribute)
    except HTTPException as exc:
        logger.warning("Invalid identifier attribute for integration save: %s", exc.detail)
        return integrations_redirect(root, "error", str(exc.detail))

    parsed_vlans = parse_allowed_vlans(allowed_vlans, root)
    if isinstance(parsed_vlans, RedirectResponse):
        return parsed_vlans

    data = IntegrationSaveData(
        integration_id=integration_id,
        identifier_attr=resolved_attr,
        checkout_grace_minutes=checkout_grace_minutes,
        allowed_vlans=parsed_vlans,
    )

    audit_service = AuditService(session)

    if id:
        integration = session.get(HAIntegrationConfig, id)
        if not integration:
            logger.warning("Integration not found for update: %s", id)
            return integrations_redirect(root, "error", "Integration not found")
        await update_integration_record(session, audit_service, admin_id, integration, data)
    else:
        duplicate = await create_integration_record(session, audit_service, admin_id, data, root)
        if duplicate is not None:
            return duplicate

    return integrations_redirect(root, "success", "Integration saved successfully")


@router.post("/delete/{integration_id}")
async def delete_integration(
    request: Request,
    integration_id: UUID,
    session: Session = Depends(get_session),
    admin_id: UUID = Depends(require_admin),
    csrf: CSRFProtection = Depends(get_csrf_protection),
) -> RedirectResponse:
    """Delete integration configuration (admin only).

    Args:
        request: FastAPI request
        integration_id: Integration UUID
        session: Database session
        admin_id: Authenticated admin user ID
        csrf: CSRF protection

    Returns:
        303 redirect to integrations page with success or error message.
    """
    root = request.scope.get("root_path", "")

    try:
        await csrf.validate_token(request)
    except HTTPException:
        logger.warning("CSRF validation failed for integration delete %s", integration_id)
        return RedirectResponse(
            url=f"{root}/admin/integrations/?error=Invalid+CSRF+token",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    integration = session.get(HAIntegrationConfig, integration_id)
    if not integration:
        logger.warning("Integration not found for delete: %s", integration_id)
        return RedirectResponse(
            url=f"{root}/admin/integrations/?error=Integration+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    session.delete(integration)
    session.commit()

    audit_service = AuditService(session)
    await audit_service.log_admin_action(
        admin_id=admin_id,
        action="delete_integration",
        target_type="ha_integration_config",
        target_id=str(integration_id),
    )

    return RedirectResponse(
        url=f"{root}/admin/integrations/?success=Integration+deleted+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )
