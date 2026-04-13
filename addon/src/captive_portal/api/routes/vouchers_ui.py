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
from captive_portal.persistence.repositories import (
    AccessGrantRepository,
    VoucherRepository,
)
from captive_portal.security.csrf import CSRFProtection, get_csrf_protection
from captive_portal.security.session_middleware import require_admin
from captive_portal.services.audit_service import AuditService
from captive_portal.services.voucher_purge_service import VoucherPurgeService
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


def _parse_vlan_form_input(raw: str | None) -> list[int] | None:
    """Parse comma-separated VLAN IDs from form input.

    Args:
        raw: Raw form input string (e.g. "50, 51, 52") or None.

    Returns:
        Sorted list of valid VLAN IDs, or None if input is empty.

    Raises:
        ValueError: If any VLAN ID is invalid.
    """
    if not raw or not str(raw).strip():
        return None
    vlans = sorted(set(int(v.strip()) for v in str(raw).split(",") if v.strip()))
    for vid in vlans:
        if vid < 1 or vid > 4094:
            raise ValueError(f"Invalid VLAN ID: {vid}")
    return vlans


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


@dataclass
class BulkCreateParams:
    """Parsed and validated parameters for bulk voucher creation."""

    count: int
    duration: int
    max_devices: int
    allowed_vlans: list[int] | None
    booking_ref: str | None


def _parse_bulk_create_form(
    form: Any,
    root: str,
) -> BulkCreateParams | RedirectResponse:
    """Parse and validate bulk-create form fields.

    Args:
        form: Submitted form data.
        root: Root path prefix for redirect URLs.

    Returns:
        Parsed parameters or a redirect response on validation error.
    """
    count_raw = form.get("count", "")
    try:
        count = int(count_raw)
    except (ValueError, TypeError):
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Count+must+be+a+positive+integer",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if count < 1 or count > 100:
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Count+must+be+between+1+and+100",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    duration_raw = form.get("duration_minutes", "")
    try:
        duration = int(duration_raw)
    except (ValueError, TypeError):
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Duration+must+be+between+1+and+43200+minutes",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if duration < 1 or duration > 43200:
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Duration+must+be+between+1+and+43200+minutes",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    max_devices_raw = form.get("max_devices", "1")
    try:
        max_devices = int(max_devices_raw)
    except (ValueError, TypeError):
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Max+devices+must+be+a+positive+integer",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if max_devices < 1:
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Max+devices+must+be+at+least+1",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    allowed_vlans_raw = form.get("allowed_vlans", "")
    try:
        parsed_vlans = _parse_vlan_form_input(str(allowed_vlans_raw) if allowed_vlans_raw else None)
    except ValueError:
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Invalid+VLAN+input",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    booking_ref_raw = form.get("booking_ref", "")
    booking_ref: str | None
    if booking_ref_raw:
        booking_ref_str = str(booking_ref_raw).strip()
        booking_ref = booking_ref_str or None
    else:
        booking_ref = None

    if booking_ref and len(booking_ref) > 128:
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Booking+reference+must+be+128+characters+or+less",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return BulkCreateParams(
        count=count,
        duration=duration,
        max_devices=max_devices,
        allowed_vlans=parsed_vlans,
        booking_ref=booking_ref,
    )


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
    purge_preview_count = request.query_params.get("purge_preview_count")
    purge_preview_days = request.query_params.get("purge_preview_days")
    info_message = request.query_params.get("info")

    stmt: Any = select(Voucher).order_by(col(Voucher.created_utc).desc()).limit(500)
    vouchers = list(cast(list[Voucher], session.exec(stmt).all()))

    # Lazily persist EXPIRED status for stale ACTIVE vouchers.
    # flush() inside the service keeps loaded objects valid;
    # commit after the response is built to avoid N+1 refreshes.
    voucher_repo = VoucherRepository(session)
    grant_repo = AccessGrantRepository(session)
    voucher_service = VoucherService(session=session, voucher_repo=voucher_repo)
    expired_count = voucher_service.expire_stale_vouchers(vouchers)

    # Auto-purge terminal vouchers past retention period (30 days).
    audit_service = AuditService(session)
    purge_service = VoucherPurgeService(
        voucher_repo=voucher_repo,
        grant_repo=grant_repo,
        audit_service=audit_service,
    )
    purged_count = await purge_service.auto_purge()

    # If vouchers were purged, re-query to get the updated list.
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

    # Batch-query active device counts for every voucher in the list
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
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Invalid+CSRF+token",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    form = await request.form()
    parsed = _parse_bulk_create_form(form, root)
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
                    "bulk": True,
                },
            )

    if len(created_codes) == parsed.count:
        if parsed.count == 1:
            return RedirectResponse(
                url=f"{root}/admin/vouchers/?new_code={created_codes[0]}&success=Voucher+created+successfully",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        msg = urllib.parse.quote_plus(f"Created {parsed.count} vouchers successfully")
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?success={msg}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    elif created_codes:
        msg = urllib.parse.quote_plus(
            f"Created {len(created_codes)} of {parsed.count} vouchers (collision on remaining)"
        )
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?success={msg}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    else:
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Failed+to+generate+unique+voucher+codes",
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


@router.post("/purge-preview")
async def purge_preview(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_id: Annotated[UUID, Depends(require_admin)],
    csrf: Annotated[CSRFProtection, Depends(get_csrf_protection)],
) -> RedirectResponse:
    """Preview the count of vouchers eligible for purge.

    Validates the ``min_age_days`` form field, counts eligible vouchers,
    and redirects to the vouchers page with preview parameters in the
    query string for rendering the confirmation banner.

    Args:
        request: Incoming HTTP request.
        session: Database session.
        admin_id: Authenticated admin user ID.
        csrf: CSRF protection instance.

    Returns:
        303 redirect to vouchers page with purge preview or error.
    """
    root = request.scope.get("root_path", "")

    try:
        await csrf.validate_token(request)
    except HTTPException:
        logger.warning("CSRF validation failed for purge preview")
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error=Invalid+CSRF+token",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    form = await request.form()
    min_age_raw = form.get("min_age_days", "")

    try:
        min_age_days = int(min_age_raw)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error="
            + urllib.parse.quote_plus("Age threshold must be a non-negative integer."),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if min_age_days < 0:
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error="
            + urllib.parse.quote_plus("Age threshold must be a non-negative integer."),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    voucher_repo = VoucherRepository(session)
    grant_repo = AccessGrantRepository(session)
    audit_service = AuditService(session)
    purge_service = VoucherPurgeService(
        voucher_repo=voucher_repo,
        grant_repo=grant_repo,
        audit_service=audit_service,
    )

    count = await purge_service.count_purgeable(min_age_days)

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

    Validates the ``min_age_days`` form field, executes the purge
    operation (nullifying grant references, deleting vouchers, and
    logging to the audit trail), and redirects with a success message.

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

    form = await request.form()
    min_age_raw = form.get("min_age_days", "")

    try:
        min_age_days = int(min_age_raw)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error="
            + urllib.parse.quote_plus("Age threshold must be a non-negative integer."),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if min_age_days < 0:
        return RedirectResponse(
            url=f"{root}/admin/vouchers/?error="
            + urllib.parse.quote_plus("Age threshold must be a non-negative integer."),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Resolve admin username for audit trail
    from captive_portal.persistence.repositories import AdminUserRepository

    admin_repo = AdminUserRepository(session)
    admin_user_obj = admin_repo.get_by_id(admin_id)
    actor = admin_user_obj.username if admin_user_obj else str(admin_id)

    voucher_repo = VoucherRepository(session)
    grant_repo = AccessGrantRepository(session)
    audit_service = AuditService(session)
    purge_service = VoucherPurgeService(
        voucher_repo=voucher_repo,
        grant_repo=grant_repo,
        audit_service=audit_service,
    )

    purged_count = await purge_service.manual_purge(min_age_days, actor=actor)

    success_msg = urllib.parse.quote_plus(f"Purged {purged_count} vouchers")
    return RedirectResponse(
        url=f"{root}/admin/vouchers/?success={success_msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
