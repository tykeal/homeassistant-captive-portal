# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Guard the device VLAN wiring into cross-integration booking lookup."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from captive_portal.api.routes import guest_portal
from captive_portal.models.ha_integration_config import (
    HAIntegrationConfig,
    IdentifierAttr,
)
from captive_portal.models.rental_control_event import RentalControlEvent
from captive_portal.services.booking_code_validator import BookingCodeValidator
from captive_portal.services.unified_code_service import CodeType, CodeValidationResult
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture()
def booking_session() -> Generator[Session, None, None]:
    """Provide a session holding two colliding booking codes."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        for integration_id, vlan, start_offset in (
            ("calendar.vlan_63", 63, timedelta(hours=-6)),
            ("calendar.vlan_61", 61, timedelta(minutes=-10)),
        ):
            session.add(
                HAIntegrationConfig(
                    integration_id=integration_id,
                    identifier_attr=IdentifierAttr.SLOT_CODE,
                    checkout_grace_minutes=15,
                    allowed_vlans=[vlan],
                )
            )
            session.add(
                RentalControlEvent(
                    integration_id=integration_id,
                    event_index=0,
                    slot_code="ABC123",
                    slot_name=f"Guest {vlan}",
                    last_four="1234",
                    start_utc=now + start_offset,
                    end_utc=now + timedelta(days=1),
                    raw_attributes="{}",
                )
            )
        session.commit()
        yield session


def _request() -> Any:
    """Build a minimal request stub for the authorization flow."""
    request = Mock()
    request.method = "GET"
    request.headers = {"User-Agent": "pytest"}
    request.state = Mock()
    request.app.state.debug_guest_portal = False
    request.client.host = "198.51.100.7"
    return request


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("device_vid", "expected_integration"),
    [("63", "calendar.vlan_63"), ("61", "calendar.vlan_61")],
)
async def test_authorization_passes_device_vid_to_lookup(
    booking_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    device_vid: str,
    expected_integration: str,
) -> None:
    """The route resolves colliding codes against the device VLAN."""
    monkeypatch.setattr(
        guest_portal._guest_csrf,
        "validate_token",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        guest_portal,
        "_extract_mac_address",
        lambda request, form_mac=None: "AA:BB:CC:DD:EE:FF",
    )

    selected: list[str] = []
    original = BookingCodeValidator.find_across_integrations

    def spy(self: BookingCodeValidator, user_input: str, device_vid: str | None = None) -> Any:
        """Record which integration the resolver selects."""
        event, integration = original(self, user_input, device_vid=device_vid)
        if integration is not None:
            selected.append(integration.integration_id)
        return event, integration

    monkeypatch.setattr(BookingCodeValidator, "find_across_integrations", spy)

    portal_config = Mock()
    portal_config.get_trusted_networks.return_value = []
    rate_limiter = Mock()
    rate_limiter.is_allowed.return_value = True
    unified_code_service = Mock()
    unified_code_service.validate_code = AsyncMock(
        return_value=CodeValidationResult(
            code_type=CodeType.BOOKING,
            normalized_code="ABC123",
            original_code="abc123",
        )
    )

    # The flow completes without a controller; the assertion below
    # targets which integration the lookup resolved.
    await guest_portal._process_authorization(
        request=_request(),
        code="abc123",
        continue_url=None,
        client_mac="AA-BB-CC-DD-EE-FF",
        site="site-1",
        gateway_mac="78-8C-B5-F9-7A-33",
        ap_mac=None,
        vid=device_vid,
        ssid_name=None,
        radio_id=None,
        rate_limiter=rate_limiter,
        unified_code_service=unified_code_service,
        redirect_validator=Mock(),
        session=booking_session,
        audit_service=Mock(log=AsyncMock()),
        portal_config=portal_config,
        omada_adapter=None,
    )

    # Without VLAN-aware matching the later-starting VLAN 61 booking
    # always won, so a VLAN 63 guest was denied with a misleading 403.
    assert selected == [expected_integration]
