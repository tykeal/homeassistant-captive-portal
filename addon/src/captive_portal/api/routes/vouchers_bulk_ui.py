# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Bulk voucher admin UI routes."""

from __future__ import annotations

import logging
import urllib.parse
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from captive_portal.api.routes.admin_redirects import safe_admin_redirect
from captive_portal.api.routes.vouchers_common import (
    BulkResult,
    format_bulk_message,
    parse_bulk_create_form,
)
from captive_portal.models.voucher import VoucherStatus
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
router = APIRouter()


@router.post("/bulk-create")
async def bulk_create_vouchers(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_id: Annotated[UUID, Depends(require_admin)],
    csrf: Annotated[CSRFProtection, Depends(get_csrf_protection)],
) -> RedirectResponse:
    """Create multiple vouchers with shared parameters.

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
        logger.warning("CSRF validation failed for bulk voucher create")
        return safe_admin_redirect(root, "/admin/vouchers/?error=Invalid+CSRF+token")

    form = await request.form()
    parsed = parse_bulk_create_form(form, root)
    if isinstance(parsed, RedirectResponse):
        return parsed

    voucher_service = VoucherService(session=session, voucher_repo=VoucherRepository(session))
    audit_service = AuditService(session)
    created_codes: list[str] = []

    for _ in range(parsed.count):
        try:
            voucher = await voucher_service.create(
                duration_minutes=parsed.duration,
                booking_ref=parsed.booking_ref,
                allowed_vlans=parsed.allowed_vlans,
                max_devices=parsed.max_devices,
            )
            created_codes.append(voucher.code)
        except VoucherCollisionError:
            logger.warning("Voucher code collision during bulk create")
            break

    if created_codes:
        for code in created_codes:
            await audit_service.log_admin_action(
                admin_id=admin_id,
                action="voucher.create",
                target_type="voucher",
                target_id=code,
                metadata={
                    "duration_minutes": parsed.duration,
                    "booking_ref": parsed.booking_ref,
                    "max_devices": parsed.max_devices,
                    "bulk": parsed.count > 1,
                },
            )

    if len(created_codes) == parsed.count:
        if parsed.count == 1:
            return safe_admin_redirect(
                root,
                f"/admin/vouchers/?new_code={created_codes[0]}&success="
                "Voucher+created+successfully",
            )
        msg = urllib.parse.quote_plus(f"Created {parsed.count} vouchers successfully")
        return safe_admin_redirect(root, f"/admin/vouchers/?success={msg}")
    if created_codes:
        msg = urllib.parse.quote_plus(
            f"Created {len(created_codes)} of {parsed.count} vouchers (collision on remaining)"
        )
        return safe_admin_redirect(root, f"/admin/vouchers/?success={msg}")
    return safe_admin_redirect(
        root,
        "/admin/vouchers/?error=Failed+to+generate+unique+voucher+codes",
    )


@router.post("/bulk-revoke")
async def bulk_revoke_vouchers(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_id: Annotated[UUID, Depends(require_admin)],
    csrf: Annotated[CSRFProtection, Depends(get_csrf_protection)],
) -> RedirectResponse:
    """Revoke multiple selected vouchers.

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
        logger.warning("CSRF validation failed for bulk voucher revoke")
        return safe_admin_redirect(root, "/admin/vouchers/?error=Invalid+CSRF+token")
    form = await request.form()
    codes = form.getlist("codes")
    if not codes:
        return safe_admin_redirect(root, "/admin/vouchers/?error=No+vouchers+selected")
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
    return safe_admin_redirect(root, f"/admin/vouchers/?{param_key}={encoded_msg}")


@router.post("/bulk-delete")
async def bulk_delete_vouchers(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_id: Annotated[UUID, Depends(require_admin)],
    csrf: Annotated[CSRFProtection, Depends(get_csrf_protection)],
) -> RedirectResponse:
    """Delete multiple selected vouchers.

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
        logger.warning("CSRF validation failed for bulk voucher delete")
        return safe_admin_redirect(root, "/admin/vouchers/?error=Invalid+CSRF+token")
    form = await request.form()
    codes = form.getlist("codes")
    if not codes:
        return safe_admin_redirect(root, "/admin/vouchers/?error=No+vouchers+selected")
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
    return safe_admin_redirect(root, f"/admin/vouchers/?{param_key}={encoded_msg}")
