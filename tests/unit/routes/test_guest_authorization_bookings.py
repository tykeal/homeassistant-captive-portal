# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for guest booking authorization helper boundaries."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast

from fastapi import Request

from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.services.audit_service import AuditService
from captive_portal.services.unified_code_service import CodeType, CodeValidationResult


def _booking_validation_result() -> CodeValidationResult:
    """Return a validated booking-code fixture for helper-boundary tests."""
    return CodeValidationResult(
        code_type=CodeType.BOOKING,
        normalized_code="Booking-123",
        original_code="Booking-123",
    )


def test_booking_grant_input_is_frozen_and_slotted() -> None:
    """Grant input preserves exact booking grant construction values."""
    from captive_portal.api.routes.guest_authorization.bookings import BookingGrantInput

    validation_result = _booking_validation_result()
    integration = HAIntegrationConfig(integration_id="rental-control")
    start_utc = datetime(2026, 6, 29, 15, 12, 30, tzinfo=timezone.utc)
    effective_end = datetime(2026, 6, 30, 10, 5, 10, tzinfo=timezone.utc)
    now = datetime(2026, 6, 29, 16, 1, 45, tzinfo=timezone.utc)

    grant_input = BookingGrantInput(
        mac_address="AA:BB:CC:DD:EE:FF",
        validation_result=validation_result,
        integration=integration,
        booking_identifier="CaseSensitive",
        start_utc=start_utc,
        effective_end=effective_end,
        now=now,
    )

    assert grant_input.mac_address == "AA:BB:CC:DD:EE:FF"
    assert grant_input.validation_result is validation_result
    assert grant_input.integration is integration
    assert grant_input.booking_identifier == "CaseSensitive"
    assert grant_input.start_utc is start_utc
    assert grant_input.effective_end is effective_end
    assert grant_input.now is now
    assert not hasattr(grant_input, "__dict__")

    try:
        grant_input.booking_identifier = "changed"
    except FrozenInstanceError:
        pass
    else:  # pragma: no cover - should fail before implementation
        raise AssertionError("BookingGrantInput must be frozen")


def test_booking_audit_inputs_are_frozen_and_slotted() -> None:
    """Audit inputs preserve exact booking denial metadata values."""
    from captive_portal.api.routes.guest_authorization.bookings import (
        BookingAuditContext,
        BookingAuditFailure,
    )

    validation_result = _booking_validation_result()
    request = cast(Request, SimpleNamespace(headers={"User-Agent": "pytest"}))
    audit_service = cast(AuditService, object())

    audit_context = BookingAuditContext(
        audit_service=audit_service,
        request=request,
        client_ip="192.0.2.10",
        mac_address="AA:BB:CC:DD:EE:FF",
        validation_result=validation_result,
    )
    audit_failure = BookingAuditFailure(
        error="booking_not_found",
        outcome="denied",
        detail="Booking not found",
        target_type="booking",
    )

    assert audit_context.audit_service is audit_service
    assert audit_context.request is request
    assert audit_context.client_ip == "192.0.2.10"
    assert audit_context.mac_address == "AA:BB:CC:DD:EE:FF"
    assert audit_context.validation_result is validation_result
    assert audit_failure.error == "booking_not_found"
    assert audit_failure.outcome == "denied"
    assert audit_failure.detail == "Booking not found"
    assert audit_failure.target_type == "booking"
    assert not hasattr(audit_context, "__dict__")
    assert not hasattr(audit_failure, "__dict__")

    for target, field, value in (
        (audit_context, "client_ip", "198.51.100.10"),
        (audit_failure, "detail", "changed"),
    ):
        try:
            setattr(target, field, value)
        except FrozenInstanceError:
            pass
        else:  # pragma: no cover - should fail before implementation
            raise AssertionError(f"{type(target).__name__} must be frozen")
