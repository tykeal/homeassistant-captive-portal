# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Admin UI routes for voucher management (list, create, revoke, delete).

Provides HTML pages for viewing vouchers with redemption status and
creating new vouchers using the Post/Redirect/Get (PRG) pattern.
"""

from __future__ import annotations

import logging
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, NamedTuple, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, col, select

from captive_portal.models.voucher import Voucher, VoucherStatus
from captive_portal.persistence.database import get_session
from captive_portal.persistence.repositories import VoucherRepository
from captive_portal.security.csrf import CSRFProtection, get_csrf_protection
from captive_portal.security.session_middleware import require_admin
from captive_portal.services.audit_service import AuditService
from captive_portal.services.voucher_service import (
    VoucherCollisionError,
    VoucherExpiredError,
    VoucherNotFoundError,
    VoucherRedeemedError,
    VoucherService,
)

logger = logging.getLogger("captive_portal")

router = APIRouter(prefix="/admin/vouchers", tags=["admin-ui-vouchers"])
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


class VoucherActions(NamedTuple):
    """Pre-computed action eligibility for a voucher."""

    can_revoke: bool
    can_delete: bool


@dataclass
class BulkResult:
    """Summary of a bulk operation outcome."""

    action: str
    success_count: int = 0
    skip_reasons: dict[str, int] = field(default_factory=dict)


def format_bulk_message(result: BulkResult) -> tuple[str, str]:
    """Format bulk operation result into feedback message and query param key."""
    total_skipped = sum(result.skip_reasons.values())

    if result.success_count > 0 and total_skipped == 0:
        msg = f"{result.action.title()} {result.success_count} vouchers successfully"
        return msg, "success"
    elif result.success_count > 0 and total_skipped > 0:
        skip_parts = [f"{count} {reason}" for reason, count in result.skip_reasons.items()]
        skip_detail = ", ".join(skip_parts)
        msg = (
            f"{result.action.title()} {result.success_count} vouchers, "
            f"skipped {total_skipped} ({skip_detail})"
        )
        return msg, "success"
    else:
        skip_parts = [f"{count} {reason}" for reason, count in result.skip_reasons.items()]
        skip_detail = ", ".join(skip_parts)
        msg = f"No vouchers {result.action} — {total_skipped} skipped ({skip_detail})"
        return msg, "error"


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

    now = datetime.now(timezone.utc)
    voucher_actions: dict[str, VoucherActions] = {}
    for voucher in vouchers:
        if voucher.is_activated_for_expiry:
            expires = voucher.expires_utc
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            is_expired = now > expires
        else:
            is_expired = False
        can_revoke = voucher.status != VoucherStatus.REVOKED and not is_expired
        can_delete = voucher.redeemed_count == 0
        voucher_actions[voucher.code] = VoucherActions(can_revoke=can_revoke, can_delete=can_delete)

    response = templates.TemplateResponse(
        request=request,
        name="admin/vouchers.html",
        context={
            "vouchers": vouchers,
            "voucher_actions": voucher_actions,
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


@router.post("/revoke/{code}")
async def revoke_voucher(
    request: Request,
    code: str,
    session: Annotated[Session, Depends(get_session)],
    admin_id: Annotated[UUID, Depends(require_admin)],
    csrf: Annotated[CSRFProtection, Depends(get_csrf_protection)],
) -> RedirectResponse:
    """Revoke a voucher (idempotent for already-revoked)."""
    root = request.scope.get("root_path", "")
    try:
        await csrf.validate_token(request)
    except HTTPException:
        logger.warning("CSRF validation failed for voucher revoke %s", code)
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Invalid+CSRF+token",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    voucher_service = VoucherService(session=session, voucher_repo=VoucherRepository(session))
    try:
        await voucher_service.revoke(code)
    except VoucherNotFoundError:
        logger.warning("Voucher not found for revoke: %s", code)
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Voucher+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except VoucherExpiredError:
        logger.warning("Cannot revoke expired voucher: %s", code)
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Cannot+revoke+an+expired+voucher",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    audit_service = AuditService(session)
    await audit_service.log_admin_action(
        admin_id=admin_id, action="voucher.revoke", target_type="voucher", target_id=code
    )
    success_message = urllib.parse.quote_plus(f"Voucher {code} revoked successfully")
    return RedirectResponse(
        url=f"{root}/admin/vouchers/?success={success_message}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/delete/{code}")
async def delete_voucher(
    request: Request,
    code: str,
    session: Annotated[Session, Depends(get_session)],
    admin_id: Annotated[UUID, Depends(require_admin)],
    csrf: Annotated[CSRFProtection, Depends(get_csrf_protection)],
) -> RedirectResponse:
    """Permanently delete a voucher that has never been redeemed."""
    root = request.scope.get("root_path", "")
    try:
        await csrf.validate_token(request)
    except HTTPException:
        logger.warning("CSRF validation failed for voucher delete %s", code)
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Invalid+CSRF+token",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    voucher_service = VoucherService(session=session, voucher_repo=VoucherRepository(session))
    try:
        meta = await voucher_service.delete(code)
    except VoucherNotFoundError:
        logger.warning("Voucher not found for delete: %s", code)
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Voucher+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except VoucherRedeemedError:
        logger.warning("Cannot delete redeemed voucher: %s", code)
        error_message = f"Cannot delete voucher {code} — it has been redeemed"
        encoded_error = urllib.parse.quote_plus(error_message)
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error={encoded_error}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    audit_service = AuditService(session)
    await audit_service.log_admin_action(
        admin_id=admin_id,
        action="voucher.delete",
        target_type="voucher",
        target_id=code,
        metadata=meta,
    )
    success_message = urllib.parse.quote_plus(f"Voucher {code} deleted successfully")
    return RedirectResponse(
        url=f"{root}/admin/vouchers/?success={success_message}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/bulk-revoke")
async def bulk_revoke_vouchers(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_id: Annotated[UUID, Depends(require_admin)],
    csrf: Annotated[CSRFProtection, Depends(get_csrf_protection)],
) -> RedirectResponse:
    """Revoke multiple selected vouchers."""
    root = request.scope.get("root_path", "")
    try:
        await csrf.validate_token(request)
    except HTTPException:
        logger.warning("CSRF validation failed for bulk voucher revoke")
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Invalid+CSRF+token",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    form = await request.form()
    codes = form.getlist("codes")
    if not codes:
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=No+vouchers+selected",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    voucher_service = VoucherService(session=session, voucher_repo=VoucherRepository(session))
    audit_service = AuditService(session)
    voucher_repo = voucher_service.voucher_repo
    result = BulkResult(action="revoked")
    for code_val in codes:
        code = str(code_val)
        existing = voucher_repo.get_by_code(code)
        if existing and existing.status == VoucherStatus.REVOKED:
            result.skip_reasons["already revoked"] = (
                result.skip_reasons.get("already revoked", 0) + 1
            )
            continue
        try:
            await voucher_service.revoke(code)
            result.success_count += 1
            await audit_service.log_admin_action(
                admin_id=admin_id, action="voucher.revoke", target_type="voucher", target_id=code
            )
        except VoucherExpiredError:
            result.skip_reasons["expired"] = result.skip_reasons.get("expired", 0) + 1
        except VoucherNotFoundError:
            result.skip_reasons["not found"] = result.skip_reasons.get("not found", 0) + 1
    msg, param_key = format_bulk_message(result)
    encoded_msg = urllib.parse.quote_plus(msg)
    return RedirectResponse(
        url=f"{root}/admin/vouchers/?{param_key}={encoded_msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/bulk-delete")
async def bulk_delete_vouchers(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_id: Annotated[UUID, Depends(require_admin)],
    csrf: Annotated[CSRFProtection, Depends(get_csrf_protection)],
) -> RedirectResponse:
    """Delete multiple selected vouchers."""
    root = request.scope.get("root_path", "")
    try:
        await csrf.validate_token(request)
    except HTTPException:
        logger.warning("CSRF validation failed for bulk voucher delete")
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Invalid+CSRF+token",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    form = await request.form()
    codes = form.getlist("codes")
    if not codes:
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=No+vouchers+selected",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    voucher_service = VoucherService(session=session, voucher_repo=VoucherRepository(session))
    audit_service = AuditService(session)
    result = BulkResult(action="deleted")
    for code_val in codes:
        code = str(code_val)
        try:
            meta = await voucher_service.delete(code)
            result.success_count += 1
            await audit_service.log_admin_action(
                admin_id=admin_id,
                action="voucher.delete",
                target_type="voucher",
                target_id=code,
                metadata=meta,
            )
        except VoucherRedeemedError:
            result.skip_reasons["already redeemed"] = (
                result.skip_reasons.get("already redeemed", 0) + 1
            )
        except VoucherNotFoundError:
            result.skip_reasons["not found"] = result.skip_reasons.get("not found", 0) + 1
    msg, param_key = format_bulk_message(result)
    encoded_msg = urllib.parse.quote_plus(msg)
    return RedirectResponse(
        url=f"{root}/admin/vouchers/?{param_key}={encoded_msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
