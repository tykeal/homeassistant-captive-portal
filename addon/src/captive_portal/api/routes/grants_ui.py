# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Admin UI routes for grant management (list, extend, revoke).

Provides HTML pages for viewing, filtering, extending, and revoking
access grants using the Post/Redirect/Get (PRG) pattern.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, col, select

from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.persistence.database import get_session
from captive_portal.security.csrf import CSRFProtection, get_csrf_protection
from captive_portal.security.session_middleware import require_admin
from captive_portal.services.audit_service import AuditService
from captive_portal.services.grant_service import (
    GrantNotFoundError,
    GrantOperationError,
    GrantService,
)

logger = logging.getLogger("captive_portal")

router = APIRouter(prefix="/admin/grants", tags=["admin-ui-grants"])
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _recompute_status(grant: AccessGrant, now: datetime) -> str:
    """Re-compute grant status based on current time.

    Args:
        grant: The access grant to evaluate.
        now: Current UTC time for comparison.

    Returns:
        Computed status string: pending, active, expired, or revoked.
    """
    if grant.status == GrantStatus.REVOKED:
        return "revoked"
    # Ensure timezone-aware comparison (SQLite may deserialize as naive)
    start = grant.start_utc
    end = grant.end_utc
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if now < start:
        return "pending"
    if now >= end:
        return "expired"
    return "active"


@router.get("/", response_class=HTMLResponse)
async def get_grants(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_id: Annotated[UUID, Depends(require_admin)],
    csrf: Annotated[CSRFProtection, Depends(get_csrf_protection)],
) -> HTMLResponse:
    """Display grant list with optional status filter.

    Args:
        request: Incoming HTTP request.
        session: Database session.
        admin_id: Authenticated admin user ID.
        csrf: CSRF protection instance.

    Returns:
        HTML response with grants list template.
    """
    existing_token = csrf.get_token_from_request(request)
    need_csrf_cookie = existing_token is None
    csrf_token: str = existing_token if existing_token is not None else csrf.generate_token()

    now = datetime.now(timezone.utc)

    status_filter = request.query_params.get("status", "")
    success_message = request.query_params.get("success")
    error_message = request.query_params.get("error")

    # Fetch all grants ordered by creation date (filtered by status below)
    stmt: Any = select(AccessGrant).order_by(col(AccessGrant.created_utc).desc())
    all_grants = list(cast(list[AccessGrant], session.exec(stmt).all()))

    # Re-compute status at render time and filter
    grants: list[AccessGrant] = []
    grant_statuses: dict[str, str] = {}
    for grant in all_grants:
        computed = _recompute_status(grant, now)
        if not status_filter or computed == status_filter:
            grants.append(grant)
            grant_statuses[str(grant.id)] = computed

    response = templates.TemplateResponse(
        request=request,
        name="admin/grants_enhanced.html",
        context={
            "grants": grants,
            "grant_statuses": grant_statuses,
            "status_filter": status_filter,
            "csrf_token": csrf_token,
            "success_message": success_message,
            "error_message": error_message,
        },
    )
    if need_csrf_cookie:
        csrf.set_csrf_cookie(response, csrf_token)
    return response


@router.post("/extend/{grant_id}")
async def extend_grant(
    request: Request,
    grant_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    admin_id: Annotated[UUID, Depends(require_admin)],
    csrf: Annotated[CSRFProtection, Depends(get_csrf_protection)],
) -> RedirectResponse:
    """Extend a grant's duration by specified minutes.

    Args:
        request: Incoming HTTP request.
        grant_id: UUID of the grant to extend.
        session: Database session.
        admin_id: Authenticated admin user ID.
        csrf: CSRF protection instance.

    Returns:
        303 redirect to grants page with success or error message.
    """
    root = request.scope.get("root_path", "")

    # Validate CSRF
    try:
        await csrf.validate_token(request)
    except HTTPException:
        logger.warning("CSRF validation failed for grant extend %s", grant_id)
        return RedirectResponse(
            url=f"{root}/admin/grants/?error=Invalid+CSRF+token",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Parse and validate minutes from form data
    form = await request.form()
    minutes_raw = form.get("minutes", "")
    try:
        minutes = int(minutes_raw)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        logger.warning("Invalid minutes value '%s' for grant extend %s", minutes_raw, grant_id)
        return RedirectResponse(
            url=f"{root}/admin/grants/?error=Minutes+must+be+between+1+and+1440",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if minutes < 1 or minutes > 1440:
        logger.warning("Minutes out of range (%d) for grant extend %s", minutes, grant_id)
        return RedirectResponse(
            url=f"{root}/admin/grants/?error=Minutes+must+be+between+1+and+1440",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Execute extend
    from captive_portal.persistence.repositories import AccessGrantRepository

    grant_service = GrantService(session=session, grant_repo=AccessGrantRepository(session))
    try:
        await grant_service.extend(grant_id, minutes)
    except GrantNotFoundError:
        logger.warning("Grant not found for extend: %s", grant_id)
        return RedirectResponse(
            url=f"{root}/admin/grants/?error=Grant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except GrantOperationError:
        logger.warning("Cannot extend revoked grant: %s", grant_id)
        return RedirectResponse(
            url=f"{root}/admin/grants/?error=Cannot+extend+a+revoked+grant",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Audit log
    audit_service = AuditService(session)
    await audit_service.log_admin_action(
        admin_id=admin_id,
        action="grant.extend",
        target_type="grant",
        target_id=str(grant_id),
        metadata={"minutes": minutes},
    )

    return RedirectResponse(
        url=f"{root}/admin/grants/?success=Grant+extended+by+{minutes}+minutes",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/revoke/{grant_id}")
async def revoke_grant(
    request: Request,
    grant_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    admin_id: Annotated[UUID, Depends(require_admin)],
    csrf: Annotated[CSRFProtection, Depends(get_csrf_protection)],
) -> RedirectResponse:
    """Revoke a grant (idempotent for already-revoked grants).

    Args:
        request: Incoming HTTP request.
        grant_id: UUID of the grant to revoke.
        session: Database session.
        admin_id: Authenticated admin user ID.
        csrf: CSRF protection instance.

    Returns:
        303 redirect to grants page with success or error message.
    """
    root = request.scope.get("root_path", "")

    # Validate CSRF
    try:
        await csrf.validate_token(request)
    except HTTPException:
        logger.warning("CSRF validation failed for grant revoke %s", grant_id)
        return RedirectResponse(
            url=f"{root}/admin/grants/?error=Invalid+CSRF+token",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Execute revoke
    from captive_portal.persistence.repositories import AccessGrantRepository

    grant_service = GrantService(session=session, grant_repo=AccessGrantRepository(session))
    try:
        await grant_service.revoke(grant_id)
    except GrantNotFoundError:
        logger.warning("Grant not found for revoke: %s", grant_id)
        return RedirectResponse(
            url=f"{root}/admin/grants/?error=Grant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Audit log
    audit_service = AuditService(session)
    await audit_service.log_admin_action(
        admin_id=admin_id,
        action="grant.revoke",
        target_type="grant",
        target_id=str(grant_id),
    )

    return RedirectResponse(
        url=f"{root}/admin/grants/?success=Grant+revoked+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )
