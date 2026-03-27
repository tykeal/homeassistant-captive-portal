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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/integrations", tags=["admin-ui-integrations"])
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


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
    csrf_token = csrf.generate_token()

    statement: Any = select(HAIntegrationConfig)
    integrations = list(cast(list[HAIntegrationConfig], session.exec(statement).all()))

    discovery_result = await _run_discovery(request, session)

    return templates.TemplateResponse(
        request=request,
        name="admin/integrations.html",
        context={
            "integrations": integrations,
            "integration": None,
            "csrf_token": csrf_token,
            "discovery_result": discovery_result,
        },
    )


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

    csrf_token = csrf.generate_token()

    statement: Any = select(HAIntegrationConfig)
    integrations = list(cast(list[HAIntegrationConfig], session.exec(statement).all()))

    discovery_result = await _run_discovery(request, session)

    return templates.TemplateResponse(
        request=request,
        name="admin/integrations.html",
        context={
            "integrations": integrations,
            "integration": integration,
            "csrf_token": csrf_token,
            "discovery_result": discovery_result,
        },
    )


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
        id: Optional existing integration UUID (for updates)
        session: Database session
        admin_id: Authenticated admin user ID
        csrf: CSRF protection

    Returns:
        Redirect to integrations list

    Raises:
        HTTPException: 404 on missing integration, 409 on duplicate, 422 on invalid data
    """
    await csrf.validate_token(request)
    audit_service = AuditService(session)
    resolved_attr = _resolve_identifier_attr(identifier_attr, auth_attribute)

    if id:
        # Update existing
        integration = session.get(HAIntegrationConfig, id)
        if not integration:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found"
            )

        integration.integration_id = integration_id
        integration.identifier_attr = resolved_attr
        integration.checkout_grace_minutes = checkout_grace_minutes

        session.add(integration)
        session.commit()

        await audit_service.log_admin_action(
            admin_id=admin_id,
            action="update_integration",
            target_type="ha_integration_config",
            target_id=str(id),
        )
    else:
        # Duplicate guard
        dup_stmt: Any = select(HAIntegrationConfig).where(
            HAIntegrationConfig.integration_id == integration_id
        )
        existing: HAIntegrationConfig | None = cast(
            Optional[HAIntegrationConfig], session.exec(dup_stmt).first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Integration '{integration_id}' already exists",
            )

        # Create new
        integration = HAIntegrationConfig(
            integration_id=integration_id,
            identifier_attr=resolved_attr,
            checkout_grace_minutes=checkout_grace_minutes,
        )

        session.add(integration)
        session.commit()
        session.refresh(integration)

        await audit_service.log_admin_action(
            admin_id=admin_id,
            action="create_integration",
            target_type="ha_integration_config",
            target_id=str(integration.id),
        )

    return RedirectResponse(
        url=f"{request.scope.get('root_path', '')}/admin/integrations",
        status_code=status.HTTP_303_SEE_OTHER,
    )


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
        Redirect to integrations list

    Raises:
        404: Integration not found
    """
    await csrf.validate_token(request)

    integration = session.get(HAIntegrationConfig, integration_id)
    if not integration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")

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
        url=f"{request.scope.get('root_path', '')}/admin/integrations",
        status_code=status.HTTP_303_SEE_OTHER,
    )
