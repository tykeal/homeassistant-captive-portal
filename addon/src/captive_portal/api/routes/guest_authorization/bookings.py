# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Booking authorization decision helpers for guest flows."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, NoReturn

from fastapi import HTTPException, Request, status
from sqlmodel import Session, select

from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.models.rental_control_event import RentalControlEvent
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

from .context import AuthorizationDecisionResult, GuestDecisionContext

_logger = logging.getLogger("captive_portal.guest")


@dataclass(frozen=True, slots=True)
class BookingGrantInput:
    """Immutable inputs used to create a booking access grant."""

    mac_address: str
    validation_result: CodeValidationResult
    integration: HAIntegrationConfig
    booking_identifier: str
    start_utc: datetime
    effective_end: datetime
    now: datetime


@dataclass(frozen=True, slots=True)
class BookingAuditContext:
    """Immutable context shared by booking error audit entries."""

    audit_service: AuditService
    request: Request
    client_ip: str
    mac_address: str
    validation_result: CodeValidationResult


@dataclass(frozen=True, slots=True)
class BookingAuditFailure:
    """Variable metadata for a booking error audit entry."""

    error: str
    outcome: str
    detail: str
    target_type: str | None = None


@dataclass(frozen=True, slots=True)
class _BookingMatch:
    """Matched booking event and integration."""

    event: RentalControlEvent
    integration: HAIntegrationConfig


@dataclass(frozen=True, slots=True)
class _BookingWindow:
    """Prepared booking window bounds for grant creation."""

    start_utc: datetime
    effective_end: datetime
    now: datetime


def _vlan_meta(vlan_result: Any) -> dict[str, Any]:
    """Build current VLAN audit metadata from a validation result."""
    return {
        "vlan_allowed": vlan_result.allowed,
        "vlan_reason": vlan_result.reason,
        "vlan_device_vid": vlan_result.device_vid,
        "vlan_allowed_vlans": vlan_result.allowed_vlans,
    }


def _aware_utc(value: datetime) -> datetime:
    """Return a timezone-aware UTC datetime using current conversion rules."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _check_booking_window(
    start_utc: datetime,
    end_utc: datetime,
    grace_minutes: int,
    now: datetime,
) -> datetime:
    """Validate booking time bounds and return effective end time."""
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
    grant_input: BookingGrantInput,
) -> AccessGrant:
    """Create and persist a booking access grant using current field rules."""
    grant = AccessGrant(
        mac=grant_input.mac_address,
        device_id=grant_input.mac_address,
        booking_ref=grant_input.booking_identifier,
        user_input_code=grant_input.validation_result.original_code,
        integration_id=grant_input.integration.integration_id,
        start_utc=floor_to_minute(max(grant_input.now, grant_input.start_utc)),
        end_utc=ceil_to_minute(grant_input.effective_end),
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
    """Preserve current duplicate active booking grant detection."""
    grant_repo = AccessGrantRepository(session)
    existing_grants = grant_repo.find_active_by_mac(mac_address)
    for existing in existing_grants:
        if existing.booking_ref and existing.booking_ref.lower() == normalized_code.lower():
            raise DuplicateGrantError("You already have an active access grant for this booking.")


def _find_booking_match(session: Session, normalized_code: str) -> _BookingMatch:
    """Find the booking event and integration using current lookup order."""
    booking_validator = BookingCodeValidator(session)
    all_integrations = list(session.exec(select(HAIntegrationConfig)).all())
    if not all_integrations:
        raise IntegrationUnavailableError("No rental control integration configured")

    event, integration = booking_validator.find_across_integrations(normalized_code)
    if not event or not integration:
        raise BookingNotFoundError("Booking not found")
    return _BookingMatch(event=event, integration=integration)


def _log_booking_found(request: Request, match: _BookingMatch) -> None:
    """Emit the current debug log for matched bookings."""
    if getattr(request.app.state, "debug_guest_portal", False):
        _logger.debug(
            "%s /authorize step=booking_found  event=%r  integration=%r",
            request.method,
            match.event.slot_code,
            match.integration.integration_id,
        )


async def _validate_booking_vlan(
    *,
    decision_context: GuestDecisionContext,
    validation_result: CodeValidationResult,
    integration: HAIntegrationConfig,
) -> dict[str, Any]:
    """Validate booking VLAN access and audit current denial metadata."""
    vlan_result = VlanValidationService().validate_booking_vlan(
        decision_context.vid,
        integration,
    )
    vlan_meta = _vlan_meta(vlan_result)
    if vlan_result.allowed:
        return vlan_meta

    await decision_context.audit_service.log(
        actor=f"guest@{decision_context.client_ip}",
        action="guest.authorize",
        outcome="denied",
        target_type="booking",
        target_id=validation_result.normalized_code,
        meta={
            "client_ip": decision_context.client_ip,
            "mac": decision_context.mac_address,
            "error": "vlan_check_failed",
            **vlan_meta,
        },
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="This code is not valid for your network.",
    )


def _prepare_booking_window(match: _BookingMatch) -> _BookingWindow:
    """Prepare booking window times using current grace-period rules."""
    now = datetime.now(timezone.utc)
    start_utc = _aware_utc(match.event.start_utc)
    end_utc = _aware_utc(match.event.end_utc)
    effective_end = _check_booking_window(
        start_utc,
        end_utc,
        match.integration.checkout_grace_minutes,
        now,
    )
    return _BookingWindow(start_utc=start_utc, effective_end=effective_end, now=now)


def _booking_audit_context(
    validation_result: CodeValidationResult,
    decision_context: GuestDecisionContext,
) -> BookingAuditContext:
    """Build booking error audit context from shared decision inputs."""
    return BookingAuditContext(
        audit_service=decision_context.audit_service,
        request=decision_context.request,
        client_ip=decision_context.client_ip,
        mac_address=decision_context.mac_address,
        validation_result=validation_result,
    )


def _booking_grant_input(
    *,
    validation_result: CodeValidationResult,
    decision_context: GuestDecisionContext,
    match: _BookingMatch,
    window: _BookingWindow,
) -> BookingGrantInput:
    """Build booking grant input with current identifier preservation."""
    booking_identifier = getattr(match.event, match.integration.identifier_attr.value)
    return BookingGrantInput(
        mac_address=decision_context.mac_address,
        validation_result=validation_result,
        integration=match.integration,
        booking_identifier=booking_identifier,
        start_utc=window.start_utc,
        effective_end=window.effective_end,
        now=window.now,
    )


def _log_grant_created(request: Request, grant: AccessGrant) -> None:
    """Emit the current debug log for created booking grants."""
    if getattr(request.app.state, "debug_guest_portal", False):
        _logger.debug(
            "%s /authorize step=grant_created  grant_id=%s  mac=%s",
            request.method,
            grant.id,
            grant.mac,
        )


async def _raise_booking_http_error(
    *,
    audit_context: BookingAuditContext,
    failure: BookingAuditFailure,
    status_code: int,
    exc: Exception,
) -> NoReturn:
    """Audit a booking helper exception and raise its HTTP mapping."""
    await _audit_booking_error(audit_context=audit_context, failure=failure)
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc


async def authorize_booking(
    *,
    validation_result: CodeValidationResult,
    session: Session,
    decision_context: GuestDecisionContext,
) -> AuthorizationDecisionResult:
    """Execute the booking branch of guest authorization."""
    audit_context = _booking_audit_context(validation_result, decision_context)
    try:
        match = _find_booking_match(session, validation_result.normalized_code)
        _log_booking_found(decision_context.request, match)
        vlan_meta = await _validate_booking_vlan(
            decision_context=decision_context,
            validation_result=validation_result,
            integration=match.integration,
        )
        window = _prepare_booking_window(match)
        _ensure_no_duplicate_grant(
            session=session,
            mac_address=decision_context.mac_address,
            normalized_code=validation_result.normalized_code,
        )
        grant = _create_booking_grant(
            session=session,
            grant_input=_booking_grant_input(
                validation_result=validation_result,
                decision_context=decision_context,
                match=match,
                window=window,
            ),
        )
    except BookingNotFoundError as exc:
        await _raise_booking_http_error(
            audit_context=audit_context,
            failure=BookingAuditFailure("booking_not_found", "denied", str(exc), "booking"),
            status_code=status.HTTP_404_NOT_FOUND,
            exc=exc,
        )
    except BookingOutsideWindowError as exc:
        await _raise_booking_http_error(
            audit_context=audit_context,
            failure=BookingAuditFailure("booking_outside_window", "denied", str(exc), "booking"),
            status_code=status.HTTP_403_FORBIDDEN,
            exc=exc,
        )
    except DuplicateGrantError as exc:
        await _raise_booking_http_error(
            audit_context=audit_context,
            failure=BookingAuditFailure("duplicate_grant", "denied", str(exc), "booking"),
            status_code=status.HTTP_409_CONFLICT,
            exc=exc,
        )
    except IntegrationUnavailableError as exc:
        await _raise_booking_http_error(
            audit_context=audit_context,
            failure=BookingAuditFailure("integration_unavailable", "error", str(exc)),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            exc=exc,
        )

    _log_grant_created(decision_context.request, grant)
    return AuthorizationDecisionResult(
        grant=grant,
        code_type=CodeType.BOOKING,
        target_type="booking",
        target_id=validation_result.normalized_code,
        vlan_meta=vlan_meta,
    )


async def _audit_booking_error(
    *,
    audit_context: BookingAuditContext,
    failure: BookingAuditFailure,
) -> None:
    """Audit a booking authorization error using current metadata."""
    kwargs: dict[str, Any] = {}
    if failure.target_type is not None:
        kwargs["target_type"] = failure.target_type
        kwargs["target_id"] = audit_context.validation_result.normalized_code
    await audit_context.audit_service.log(
        actor=f"guest@{audit_context.client_ip}",
        action="guest.authorize",
        outcome=failure.outcome,
        meta={
            "client_ip": audit_context.client_ip,
            "mac": audit_context.mac_address,
            "user_agent": audit_context.request.headers.get("User-Agent", "unknown"),
            "error": failure.error,
            "detail": failure.detail,
        },
        **kwargs,
    )
