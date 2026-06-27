# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Voucher purge admin UI routes."""

from __future__ import annotations

import logging
import urllib.parse
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from captive_portal.persistence.database import get_session
from captive_portal.persistence.repositories import (
    AccessGrantRepository,
    AdminUserRepository,
    VoucherRepository,
)
from captive_portal.security.csrf import CSRFProtection, get_csrf_protection
from captive_portal.security.session_middleware import require_admin
from captive_portal.services.audit_service import AuditService
from captive_portal.services.voucher_purge_service import VoucherPurgeService

logger = logging.getLogger("captive_portal")
router = APIRouter()


def _age_threshold_error(root: str) -> RedirectResponse:
    """Build an invalid age threshold redirect.

    Args:
        root: ASGI root path prefix.

    Returns:
        303 redirect response.
    """
    return RedirectResponse(
        url=f"{root}/admin/vouchers/?error="
        + urllib.parse.quote_plus("Age threshold must be a non-negative integer."),
        status_code=status.HTTP_303_SEE_OTHER,
    )


async def _parse_purge_age(request: Request, root: str) -> int | RedirectResponse:
    """Parse the purge age form field.

    Args:
        request: Incoming HTTP request.
        root: ASGI root path prefix.

    Returns:
        Parsed age in days or redirect response on validation error.
    """
    form = await request.form()
    min_age_raw = form.get("min_age_days", "")

    try:
        min_age_days = int(min_age_raw)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return _age_threshold_error(root)

    if min_age_days < 0:
        return _age_threshold_error(root)
    return min_age_days


def _purge_service(session: Session) -> VoucherPurgeService:
    """Create a voucher purge service for *session*.

    Args:
        session: Database session.

    Returns:
        Configured purge service.
    """
    return VoucherPurgeService(
        voucher_repo=VoucherRepository(session),
        grant_repo=AccessGrantRepository(session),
        audit_service=AuditService(session),
    )


@router.post("/purge-preview")
async def purge_preview(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_id: Annotated[UUID, Depends(require_admin)],
    csrf: Annotated[CSRFProtection, Depends(get_csrf_protection)],
) -> RedirectResponse:
    """Preview the count of vouchers eligible for purge.

    Args:
        request: Incoming HTTP request.
        session: Database session.
        admin_id: Authenticated admin user ID.
        csrf: CSRF protection instance.

    Returns:
        303 redirect to vouchers page with purge preview or error.
    """
    del admin_id
    root = request.scope.get("root_path", "")

    try:
        await csrf.validate_token(request)
    except HTTPException:
        logger.warning("CSRF validation failed for purge preview")
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Invalid+CSRF+token",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    min_age_days = await _parse_purge_age(request, root)
    if isinstance(min_age_days, RedirectResponse):
        return min_age_days

    count = await _purge_service(session).count_purgeable(min_age_days)

    if count == 0:
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?info="
            + urllib.parse.quote_plus("No vouchers are eligible for purging with that threshold."),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"{root}/admin/vouchers/?purge_preview_count={count}&purge_preview_days={min_age_days}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/purge-confirm")
async def purge_confirm(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_id: Annotated[UUID, Depends(require_admin)],
    csrf: Annotated[CSRFProtection, Depends(get_csrf_protection)],
) -> RedirectResponse:
    """Execute the purge of eligible vouchers.

    Args:
        request: Incoming HTTP request.
        session: Database session.
        admin_id: Authenticated admin user ID.
        csrf: CSRF protection instance.

    Returns:
        303 redirect to vouchers page with success or error message.
    """
    root = request.scope.get("root_path", "")

    try:
        await csrf.validate_token(request)
    except HTTPException:
        logger.warning("CSRF validation failed for purge confirm")
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Invalid+CSRF+token",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    min_age_days = await _parse_purge_age(request, root)
    if isinstance(min_age_days, RedirectResponse):
        return min_age_days

    admin_repo = AdminUserRepository(session)
    admin_user_obj = admin_repo.get_by_id(admin_id)
    actor = admin_user_obj.username if admin_user_obj else str(admin_id)
    purged_count = await _purge_service(session).manual_purge(min_age_days, actor=actor)

    success_msg = urllib.parse.quote_plus(f"Purged {purged_count} vouchers")
    return RedirectResponse(
        url=f"{root}/admin/vouchers/?success={success_msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
