# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Admin UI routes for voucher management (list, create).

Provides HTML pages for viewing vouchers with redemption status and
creating new vouchers using the Post/Redirect/Get (PRG) pattern.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, col, select

from captive_portal.models.voucher import Voucher
from captive_portal.persistence.database import get_session
from captive_portal.persistence.repositories import VoucherRepository
from captive_portal.security.csrf import CSRFProtection, get_csrf_protection
from captive_portal.security.session_middleware import require_admin
from captive_portal.services.audit_service import AuditService
from captive_portal.services.voucher_service import VoucherCollisionError, VoucherService

logger = logging.getLogger("captive_portal")

router = APIRouter(prefix="/admin/vouchers", tags=["admin-ui-vouchers"])
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@router.get("/", response_class=HTMLResponse)
async def get_vouchers(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_id: Annotated[UUID, Depends(require_admin)],
    csrf: Annotated[CSRFProtection, Depends(get_csrf_protection)],
) -> HTMLResponse:
    """Display voucher list and creation form.

    Args:
        request: Incoming HTTP request.
        session: Database session.
        admin_id: Authenticated admin user ID.
        csrf: CSRF protection instance.

    Returns:
        HTML response with vouchers template.
    """
    existing_token = csrf.get_token_from_request(request)
    need_csrf_cookie = existing_token is None
    csrf_token: str = existing_token if existing_token is not None else csrf.generate_token()

    new_code = request.query_params.get("new_code")
    success_message = request.query_params.get("success")
    error_message = request.query_params.get("error")

    stmt: Any = select(Voucher).order_by(col(Voucher.created_utc).desc()).limit(500)
    vouchers = list(cast(list[Voucher], session.exec(stmt).all()))

    response = templates.TemplateResponse(
        request=request,
        name="admin/vouchers.html",
        context={
            "vouchers": vouchers,
            "csrf_token": csrf_token,
            "new_code": new_code,
            "success_message": success_message,
            "error_message": error_message,
        },
    )
    if need_csrf_cookie:
        csrf.set_csrf_cookie(response, csrf_token)
    return response


@router.post("/create")
async def create_voucher(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_id: Annotated[UUID, Depends(require_admin)],
    csrf: Annotated[CSRFProtection, Depends(get_csrf_protection)],
) -> RedirectResponse:
    """Create a new voucher with specified duration.

    Args:
        request: Incoming HTTP request.
        session: Database session.
        admin_id: Authenticated admin user ID.
        csrf: CSRF protection instance.

    Returns:
        303 redirect to vouchers page with new_code or error message.
    """
    root = request.scope.get("root_path", "")

    # Validate CSRF
    try:
        await csrf.validate_token(request)
    except HTTPException:
        logger.warning("CSRF validation failed for voucher create")
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Invalid+CSRF+token",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Parse form data
    form = await request.form()
    duration_raw = form.get("duration_minutes", "")
    booking_ref_raw = form.get("booking_ref", "")
    booking_ref: str | None
    if booking_ref_raw:
        booking_ref_str = str(booking_ref_raw).strip()
        booking_ref = booking_ref_str or None
    else:
        booking_ref = None

    # Validate duration
    try:
        duration = int(duration_raw)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        logger.warning("Invalid duration value '%s' for voucher create", duration_raw)
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Duration+must+be+between+1+and+43200+minutes",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if duration < 1 or duration > 43200:
        logger.warning("Duration out of range (%d) for voucher create", duration)
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Duration+must+be+between+1+and+43200+minutes",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Trim and validate booking_ref length
    if booking_ref and len(booking_ref) > 128:
        logger.warning(
            "Booking reference too long (%d chars) for voucher create",
            len(booking_ref),
        )
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Booking+reference+must+be+128+characters+or+less",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Create voucher
    voucher_service = VoucherService(session=session, voucher_repo=VoucherRepository(session))
    try:
        voucher = await voucher_service.create(duration_minutes=duration, booking_ref=booking_ref)
    except VoucherCollisionError:
        logger.warning("Voucher code collision during create")
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Failed+to+generate+unique+voucher+code",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Audit log
    audit_service = AuditService(session)
    await audit_service.log_admin_action(
        admin_id=admin_id,
        action="voucher.create",
        target_type="voucher",
        target_id=voucher.code,
        metadata={"duration_minutes": duration, "booking_ref": booking_ref},
    )

    return RedirectResponse(
        url=f"{root}/admin/vouchers/?new_code={voucher.code}&success=Voucher+created+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )
