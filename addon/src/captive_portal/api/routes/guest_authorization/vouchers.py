# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Voucher authorization decision helpers for guest flows."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status
from sqlmodel import Session

from captive_portal.services.audit_service import AuditService
from captive_portal.services.unified_code_service import CodeType, CodeValidationResult
from captive_portal.services.vlan_validation_service import VlanValidationService
from captive_portal.services.voucher_service import (
    VoucherDeviceLimitError,
    VoucherRedemptionError,
    VoucherService,
)

from .context import AuthorizationDecisionResult


def _vlan_meta(vlan_result: Any) -> dict[str, Any]:
    """Build current VLAN audit metadata from a validation result.

    Args:
        vlan_result: VLAN validation result object.

    Returns:
        Metadata keys currently written to audit logs.
    """
    return {
        "vlan_allowed": vlan_result.allowed,
        "vlan_reason": vlan_result.reason,
        "vlan_device_vid": vlan_result.device_vid,
        "vlan_allowed_vlans": vlan_result.allowed_vlans,
    }


async def authorize_voucher(
    *,
    validation_result: CodeValidationResult,
    session: Session,
    audit_service: AuditService,
    request: Request,
    client_ip: str,
    mac_address: str,
    vid: str | None,
) -> AuthorizationDecisionResult:
    """Execute the voucher branch of guest authorization.

    Args:
        validation_result: Validated voucher code.
        session: SQLModel session.
        audit_service: Audit log writer.
        request: Incoming FastAPI request.
        client_ip: Resolved client IP address.
        mac_address: Validated MAC address.
        vid: Submitted VLAN identifier.

    Returns:
        Voucher decision result containing the redeemed grant.

    Raises:
        HTTPException: For current voucher denial paths.
    """
    voucher_service = VoucherService(session)
    vlan_meta: dict[str, Any] = {}
    try:
        voucher_for_vlan = voucher_service.voucher_repo.get_by_code(
            validation_result.normalized_code
        )
        if voucher_for_vlan:
            vlan_result = VlanValidationService().validate_voucher_vlan(vid, voucher_for_vlan)
            vlan_meta = _vlan_meta(vlan_result)
            if not vlan_result.allowed:
                await audit_service.log(
                    actor=f"guest@{client_ip}",
                    action="guest.authorize",
                    outcome="denied",
                    target_type="voucher",
                    target_id=validation_result.normalized_code,
                    meta={
                        "client_ip": client_ip,
                        "mac": mac_address,
                        "error": "vlan_check_failed",
                        **vlan_meta,
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This code is not valid for your network.",
                )

        grant = await voucher_service.redeem(
            code=validation_result.normalized_code,
            mac=mac_address,
        )
    except VoucherDeviceLimitError:
        await audit_service.log(
            actor=f"guest@{client_ip}",
            action="guest.authorize",
            outcome="denied",
            target_type="voucher",
            target_id=validation_result.normalized_code,
            meta={
                "client_ip": client_ip,
                "mac": mac_address,
                "user_agent": request.headers.get("User-Agent", "unknown"),
                "error": "voucher_device_limit",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This code has reached its maximum number of devices.",
        ) from None
    except VoucherRedemptionError as exc:
        await audit_service.log(
            actor=f"guest@{client_ip}",
            action="guest.authorize",
            outcome="denied",
            target_type="voucher",
            target_id=validation_result.normalized_code,
            meta={
                "client_ip": client_ip,
                "mac": mac_address,
                "user_agent": request.headers.get("User-Agent", "unknown"),
                "error": "voucher_redemption_failed",
                "detail": str(exc),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(exc),
        ) from exc

    return AuthorizationDecisionResult(
        grant=grant,
        code_type=CodeType.VOUCHER,
        target_type="voucher",
        target_id=validation_result.normalized_code,
        vlan_meta=vlan_meta,
    )
