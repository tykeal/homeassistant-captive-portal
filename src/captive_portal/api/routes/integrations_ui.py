# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Admin UI routes for Home Assistant integration management."""

from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.persistence.database import get_session
from captive_portal.security.csrf import CSRFProtection, get_csrf_protection
from captive_portal.security.session_middleware import require_admin
from captive_portal.services.audit_service import AuditService

router = APIRouter(prefix="/admin/integrations", tags=["admin-ui-integrations"])
templates = Jinja2Templates(directory="src/captive_portal/web/templates")


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

    statement = select(HAIntegrationConfig)
    integrations = list(session.exec(statement).all())

    return templates.TemplateResponse(
        "admin/integrations.html",
        {
            "request": request,
            "integrations": integrations,
            "integration": None,
            "csrf_token": csrf_token,
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

    statement = select(HAIntegrationConfig)
    integrations = list(session.exec(statement).all())

    return templates.TemplateResponse(
        "admin/integrations.html",
        {
            "request": request,
            "integrations": integrations,
            "integration": integration,
            "csrf_token": csrf_token,
        },
    )


@router.post("/save")
async def save_integration(
    request: Request,
    integration_id: str = Form(...),
    auth_attribute: str = Form(...),
    checkout_grace_minutes: int = Form(...),
    id: UUID | None = Form(None),
    session: Session = Depends(get_session),
    admin_id: UUID = Depends(require_admin),
    csrf: CSRFProtection = Depends(get_csrf_protection),
) -> RedirectResponse:
    """Save or update integration configuration (admin only).

    Args:
        request: FastAPI request
        integration_id: HA integration identifier
        auth_attribute: Authorization attribute (slot_code, slot_name, last_four)
        checkout_grace_minutes: Checkout grace period
        id: Optional existing integration UUID (for updates)
        session: Database session
        admin_id: Authenticated admin user ID
        csrf: CSRF protection

    Returns:
        Redirect to integrations list

    Raises:
        400: Invalid form data
    """
    csrf.validate_token(request)
    audit_service = AuditService(session)

    if id:
        # Update existing
        integration = session.get(HAIntegrationConfig, id)
        if not integration:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found"
            )

        integration.integration_id = integration_id
        integration.auth_attribute = auth_attribute
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
        # Create new
        integration = HAIntegrationConfig(
            integration_id=integration_id,
            auth_attribute=auth_attribute,
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

    return RedirectResponse(url="/admin/integrations", status_code=status.HTTP_303_SEE_OTHER)


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
    csrf.validate_token(request)

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

    return RedirectResponse(url="/admin/integrations", status_code=status.HTTP_303_SEE_OTHER)
