# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Admin UI routes for voucher management (list, create, revoke, delete).

Provides HTML pages for viewing vouchers with redemption status and
creating new vouchers using the Post/Redirect/Get (PRG) pattern.
"""

from __future__ import annotations

import logging
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, col, select

from captive_portal._version import __version__
from captive_portal.api.routes.admin_redirects import safe_admin_redirect
from captive_portal.api.routes.vouchers_bulk_ui import (
    bulk_create_vouchers,
    bulk_delete_vouchers,
    bulk_revoke_vouchers,
    router as bulk_router,
)
from captive_portal.api.routes.vouchers_common import (
    BulkCreateParams,
    BulkResult,
    VoucherActions,
    format_bulk_message,
    parse_bulk_create_form,
    parse_vlan_form_input,
)
from captive_portal.api.routes.vouchers_purge_ui import (
    purge_confirm,
    purge_preview,
    router as purge_router,
)
from captive_portal.models.voucher import Voucher, VoucherStatus
from captive_portal.persistence.database import get_session
from captive_portal.persistence.repositories import (
    AccessGrantRepository,
    VoucherRepository,
)
from captive_portal.security.csrf import CSRFProtection, get_csrf_protection
from captive_portal.security.session_middleware import require_admin
from captive_portal.services.audit_service import AuditService
from captive_portal.services.voucher_purge_service import VoucherPurgeService
from captive_portal.services.voucher_service import (
    VoucherExpiredError,
    VoucherNotFoundError,
    VoucherRedeemedError,
    VoucherService,
)

__all__ = [
    "BulkCreateParams",
    "BulkResult",
    "VoucherActions",
    "_parse_bulk_create_form",
    "_parse_vlan_form_input",
    "bulk_create_vouchers",
    "bulk_delete_vouchers",
    "bulk_revoke_vouchers",
    "delete_voucher",
    "format_bulk_message",
    "get_vouchers",
    "purge_confirm",
    "purge_preview",
    "revoke_voucher",
    "router",
]

logger = logging.getLogger("captive_portal")

router = APIRouter(prefix="/admin/vouchers", tags=["admin-ui-vouchers"])
router.include_router(bulk_router, tags=["admin-ui-vouchers"])
router.include_router(purge_router, tags=["admin-ui-vouchers"])
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.globals["app_version"] = __version__

_parse_vlan_form_input = parse_vlan_form_input
_parse_bulk_create_form = parse_bulk_create_form


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
    del admin_id
    existing_token = csrf.get_token_from_request(request)
    need_csrf_cookie = existing_token is None
    csrf_token: str = existing_token if existing_token is not None else csrf.generate_token()

    new_code = request.query_params.get("new_code")
    success_message = request.query_params.get("success")
    error_message = request.query_params.get("error")
    purge_preview_count = request.query_params.get("purge_preview_count")
    purge_preview_days = request.query_params.get("purge_preview_days")
    info_message = request.query_params.get("info")

    stmt: Any = select(Voucher).order_by(col(Voucher.created_utc).desc()).limit(500)
    vouchers = list(cast(list[Voucher], session.exec(stmt).all()))

    voucher_repo = VoucherRepository(session)
    grant_repo = AccessGrantRepository(session)
    voucher_service = VoucherService(session=session, voucher_repo=voucher_repo)
    expired_count = voucher_service.expire_stale_vouchers(vouchers)

    audit_service = AuditService(session)
    purge_service = VoucherPurgeService(
        voucher_repo=voucher_repo,
        grant_repo=grant_repo,
        audit_service=audit_service,
    )
    purged_count = await purge_service.auto_purge()

    if purged_count > 0:
        vouchers = list(cast(list[Voucher], session.exec(stmt).all()))

    voucher_actions: dict[str, VoucherActions] = {}
    now = datetime.now(timezone.utc)
    for voucher in vouchers:
        if voucher.status in (VoucherStatus.REVOKED, VoucherStatus.EXPIRED):
            can_revoke = False
        elif voucher.is_activated_for_expiry:
            expires = voucher.expires_utc
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            can_revoke = now <= expires
        else:
            can_revoke = True
        can_delete = voucher.redeemed_count == 0
        voucher_actions[voucher.code] = VoucherActions(can_revoke=can_revoke, can_delete=can_delete)

    all_codes = [v.code for v in vouchers]
    active_device_counts: dict[str, int] = (
        grant_repo.count_active_by_voucher_codes(all_codes) if all_codes else {}
    )

    response = templates.TemplateResponse(
        request=request,
        name="admin/vouchers.html",
        context={
            "vouchers": vouchers,
            "voucher_actions": voucher_actions,
            "active_device_counts": active_device_counts,
            "csrf_token": csrf_token,
            "new_code": new_code,
            "success_message": success_message,
            "error_message": error_message,
            "info_message": info_message,
            "purge_preview_count": purge_preview_count,
            "purge_preview_days": purge_preview_days,
        },
    )
    if expired_count or purged_count:
        session.commit()
    if need_csrf_cookie:
        csrf.set_csrf_cookie(response, csrf_token)
    return response


@router.post("/revoke/{code}")
async def revoke_voucher(
    request: Request,
    code: str,
    session: Annotated[Session, Depends(get_session)],
    admin_id: Annotated[UUID, Depends(require_admin)],
    csrf: Annotated[CSRFProtection, Depends(get_csrf_protection)],
) -> RedirectResponse:
    """Revoke a voucher (idempotent for already-revoked).

    Args:
        request: Incoming HTTP request.
        code: Voucher code.
        session: Database session.
        admin_id: Authenticated admin user ID.
        csrf: CSRF protection instance.

    Returns:
        303 redirect with operation result.
    """
    root = request.scope.get("root_path", "")
    try:
        await csrf.validate_token(request)
    except HTTPException:
        logger.warning("CSRF validation failed for voucher revoke %s", code)
        return safe_admin_redirect(root, "/admin/vouchers/?error=Invalid+CSRF+token")
    voucher_service = VoucherService(session=session, voucher_repo=VoucherRepository(session))
    try:
        await voucher_service.revoke(code)
    except VoucherNotFoundError:
        logger.warning("Voucher not found for revoke: %s", code)
        return safe_admin_redirect(root, "/admin/vouchers/?error=Voucher+not+found")
    except VoucherExpiredError:
        logger.warning("Cannot revoke expired voucher: %s", code)
        return safe_admin_redirect(
            root,
            "/admin/vouchers/?error=Cannot+revoke+an+expired+voucher",
        )
    audit_service = AuditService(session)
    await audit_service.log_admin_action(
        admin_id=admin_id, action="voucher.revoke", target_type="voucher", target_id=code
    )
    success_message = urllib.parse.quote_plus(f"Voucher {code} revoked successfully")
    return safe_admin_redirect(root, f"/admin/vouchers/?success={success_message}")


@router.post("/delete/{code}")
async def delete_voucher(
    request: Request,
    code: str,
    session: Annotated[Session, Depends(get_session)],
    admin_id: Annotated[UUID, Depends(require_admin)],
    csrf: Annotated[CSRFProtection, Depends(get_csrf_protection)],
) -> RedirectResponse:
    """Permanently delete a voucher that has never been redeemed.

    Args:
        request: Incoming HTTP request.
        code: Voucher code.
        session: Database session.
        admin_id: Authenticated admin user ID.
        csrf: CSRF protection instance.

    Returns:
        303 redirect with operation result.
    """
    root = request.scope.get("root_path", "")
    try:
        await csrf.validate_token(request)
    except HTTPException:
        logger.warning("CSRF validation failed for voucher delete %s", code)
        return safe_admin_redirect(root, "/admin/vouchers/?error=Invalid+CSRF+token")
    voucher_service = VoucherService(session=session, voucher_repo=VoucherRepository(session))
    try:
        meta = await voucher_service.delete(code)
    except VoucherNotFoundError:
        logger.warning("Voucher not found for delete: %s", code)
        return safe_admin_redirect(root, "/admin/vouchers/?error=Voucher+not+found")
    except VoucherRedeemedError:
        logger.warning("Cannot delete redeemed voucher: %s", code)
        error_message = f"Cannot delete voucher {code} — it has been redeemed"
        encoded_error = urllib.parse.quote_plus(error_message)
        return safe_admin_redirect(root, f"/admin/vouchers/?error={encoded_error}")
    audit_service = AuditService(session)
    await audit_service.log_admin_action(
        admin_id=admin_id,
        action="voucher.delete",
        target_type="voucher",
        target_id=code,
        metadata=meta,
    )
    success_message = urllib.parse.quote_plus(f"Voucher {code} deleted successfully")
    return safe_admin_redirect(root, f"/admin/vouchers/?success={success_message}")
