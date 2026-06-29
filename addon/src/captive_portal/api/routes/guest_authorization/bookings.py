# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Booking authorization decision helpers for guest flows."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request, status
from sqlmodel import Session, select

from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.persistence.repositories import AccessGrantRepository
from captive_portal.services.audit_service import AuditService
from captive_portal.services.booking_code_validator import (
    BookingCodeValidator,
    BookingNotFoundError,
    BookingOutsideWindowError,
    DuplicateGrantError,
    IntegrationUnavailableError,
)
from captive_portal.services.unified_code_service import CodeType, CodeValidationResult
from captive_portal.services.vlan_validation_service import VlanValidationService
from captive_portal.utils.time_utils import ceil_to_minute, floor_to_minute

from .context import AuthorizationDecisionResult

_logger = logging.getLogger("captive_portal.guest")


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


def _aware_utc(value: datetime) -> datetime:
    """Return a timezone-aware UTC datetime using current conversion rules.

    Args:
        value: Datetime from a booking event.

    Returns:
        The original aware datetime or a UTC-aware replacement.
    """
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _check_booking_window(
    start_utc: datetime,
    end_utc: datetime,
    grace_minutes: int,
    now: datetime,
) -> datetime:
    """Validate booking time bounds and return effective end time.

    Args:
        start_utc: Booking start in UTC.
        end_utc: Booking end in UTC.
        grace_minutes: Integration checkout grace minutes.
        now: Single timestamp shared by the booking decision.

    Returns:
        End time plus checkout grace.

    Raises:
        BookingOutsideWindowError: When the request is outside the allowed window.
    """
    early_checkin_window = start_utc - timedelta(minutes=60)
    if now < early_checkin_window:
        raise BookingOutsideWindowError(
            f"Your booking begins on {start_utc.strftime('%Y-%m-%d at %H:%M')} UTC. "
            "Early check-in is available 60 minutes before this time."
        )

    effective_end = end_utc + timedelta(minutes=grace_minutes)
    if now > effective_end:
        raise BookingOutsideWindowError(
            f"Your booking ended on {end_utc.strftime('%Y-%m-%d at %H:%M')} UTC."
        )
    return effective_end


def _create_booking_grant(
    *,
    session: Session,
    mac_address: str,
    validation_result: CodeValidationResult,
    integration: HAIntegrationConfig,
    booking_identifier: str,
    start_utc: datetime,
    effective_end: datetime,
    now: datetime,
) -> AccessGrant:
    """Create and persist a booking access grant using current field rules.

    Args:
        session: SQLModel session.
        mac_address: Validated MAC address.
        validation_result: Validated booking code.
        integration: Matched Home Assistant integration.
        booking_identifier: Case-preserved matched booking identifier.
        start_utc: Booking start in UTC.
        effective_end: Booking end plus grace period.
        now: Single timestamp shared by the booking decision.

    Returns:
        Persisted pending access grant.
    """
    grant = AccessGrant(
        mac=mac_address,
        device_id=mac_address,
        booking_ref=booking_identifier,
        user_input_code=validation_result.original_code,
        integration_id=integration.integration_id,
        start_utc=floor_to_minute(max(now, start_utc)),
        end_utc=ceil_to_minute(effective_end),
        status=GrantStatus.PENDING,
    )
    grant_repo = AccessGrantRepository(session)
    grant_repo.add(grant)
    session.commit()
    session.refresh(grant)
    return grant


def _ensure_no_duplicate_grant(
    *,
    session: Session,
    mac_address: str,
    normalized_code: str,
) -> None:
    """Preserve current duplicate active booking grant detection.

    Args:
        session: SQLModel session.
        mac_address: Validated MAC address.
        normalized_code: Normalized booking code.

    Raises:
        DuplicateGrantError: When a duplicate active grant exists.
    """
    grant_repo = AccessGrantRepository(session)
    existing_grants = grant_repo.find_active_by_mac(mac_address)
    for existing in existing_grants:
        if existing.booking_ref and existing.booking_ref.lower() == normalized_code.lower():
            raise DuplicateGrantError("You already have an active access grant for this booking.")


async def authorize_booking(
    *,
    validation_result: CodeValidationResult,
    session: Session,
    audit_service: AuditService,
    request: Request,
    client_ip: str,
    mac_address: str,
    vid: str | None,
) -> AuthorizationDecisionResult:
    """Execute the booking branch of guest authorization.

    Args:
        validation_result: Validated booking code.
        session: SQLModel session.
        audit_service: Audit log writer.
        request: Incoming FastAPI request.
        client_ip: Resolved client IP address.
        mac_address: Validated MAC address.
        vid: Submitted VLAN identifier.

    Returns:
        Booking decision result containing the pending grant.

    Raises:
        HTTPException: For current booking denial paths.
    """
    try:
        booking_validator = BookingCodeValidator(session)
        all_integrations = list(session.exec(select(HAIntegrationConfig)).all())
        if not all_integrations:
            raise IntegrationUnavailableError("No rental control integration configured")

        event, integration = booking_validator.find_across_integrations(
            validation_result.normalized_code
        )
        if not event or not integration:
            raise BookingNotFoundError("Booking not found")

        if getattr(request.app.state, "debug_guest_portal", False):
            _logger.debug(
                "%s /authorize step=booking_found  event=%r  integration=%r",
                request.method,
                event.slot_code if event else None,
                integration.integration_id if integration else None,
            )

        vlan_result = VlanValidationService().validate_booking_vlan(vid, integration)
        vlan_meta = _vlan_meta(vlan_result)
        if not vlan_result.allowed:
            await audit_service.log(
                actor=f"guest@{client_ip}",
                action="guest.authorize",
                outcome="denied",
                target_type="booking",
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

        now = datetime.now(timezone.utc)
        start_utc = _aware_utc(event.start_utc)
        end_utc = _aware_utc(event.end_utc)
        effective_end = _check_booking_window(
            start_utc,
            end_utc,
            integration.checkout_grace_minutes,
            now,
        )
        _ensure_no_duplicate_grant(
            session=session,
            mac_address=mac_address,
            normalized_code=validation_result.normalized_code,
        )
        booking_identifier = getattr(event, integration.identifier_attr.value)
        grant = _create_booking_grant(
            session=session,
            mac_address=mac_address,
            validation_result=validation_result,
            integration=integration,
            booking_identifier=booking_identifier,
            start_utc=start_utc,
            effective_end=effective_end,
            now=now,
        )
    except BookingNotFoundError as exc:
        await _audit_booking_error(
            audit_service=audit_service,
            request=request,
            client_ip=client_ip,
            mac_address=mac_address,
            validation_result=validation_result,
            error="booking_not_found",
            outcome="denied",
            detail=str(exc),
            target_type="booking",
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BookingOutsideWindowError as exc:
        await _audit_booking_error(
            audit_service=audit_service,
            request=request,
            client_ip=client_ip,
            mac_address=mac_address,
            validation_result=validation_result,
            error="booking_outside_window",
            outcome="denied",
            detail=str(exc),
            target_type="booking",
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except DuplicateGrantError as exc:
        await _audit_booking_error(
            audit_service=audit_service,
            request=request,
            client_ip=client_ip,
            mac_address=mac_address,
            validation_result=validation_result,
            error="duplicate_grant",
            outcome="denied",
            detail=str(exc),
            target_type="booking",
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntegrationUnavailableError as exc:
        await _audit_booking_error(
            audit_service=audit_service,
            request=request,
            client_ip=client_ip,
            mac_address=mac_address,
            validation_result=validation_result,
            error="integration_unavailable",
            outcome="error",
            detail=str(exc),
            target_type=None,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    if getattr(request.app.state, "debug_guest_portal", False):
        _logger.debug(
            "%s /authorize step=grant_created  grant_id=%s  mac=%s",
            request.method,
            grant.id,
            grant.mac,
        )
    return AuthorizationDecisionResult(
        grant=grant,
        code_type=CodeType.BOOKING,
        target_type="booking",
        target_id=validation_result.normalized_code,
        vlan_meta=vlan_meta,
    )


async def _audit_booking_error(
    *,
    audit_service: AuditService,
    request: Request,
    client_ip: str,
    mac_address: str,
    validation_result: CodeValidationResult,
    error: str,
    outcome: str,
    detail: str,
    target_type: str | None,
) -> None:
    """Audit a booking authorization error using current metadata.

    Args:
        audit_service: Audit log writer.
        request: Incoming FastAPI request.
        client_ip: Resolved client IP address.
        mac_address: Validated MAC address.
        validation_result: Validated booking code.
        error: Stable error metadata value.
        outcome: Audit outcome.
        detail: Diagnostic detail string.
        target_type: Optional audit target type.
    """
    kwargs: dict[str, Any] = {}
    if target_type is not None:
        kwargs["target_type"] = target_type
        kwargs["target_id"] = validation_result.normalized_code
    await audit_service.log(
        actor=f"guest@{client_ip}",
        action="guest.authorize",
        outcome=outcome,
        meta={
            "client_ip": client_ip,
            "mac": mac_address,
            "user_agent": request.headers.get("User-Agent", "unknown"),
            "error": error,
            "detail": detail,
        },
        **kwargs,
    )
