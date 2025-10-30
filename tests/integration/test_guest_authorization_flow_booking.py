# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for guest authorization flow with booking code."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from captive_portal.app import create_app
from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.models.rental_control_event import RentalControlEvent


@pytest.mark.asyncio
class TestGuestAuthorizationFlowBooking:
    """Test end-to-end guest flow with booking code (direct + redirect)."""

    async def test_direct_access_booking_auth(self, db_session: Session) -> None:
        """Direct access to /guest/authorize with booking code."""
        # Setup integration and event
        config = HAIntegrationConfig(
            integration_id="rental1",
            auth_attribute="slot_code",
            checkout_grace_minutes=15,
        )
        db_session.add(config)

        now = datetime.now(timezone.utc)
        event = RentalControlEvent(
            integration_id="rental1",
            event_index=0,
            start_utc=now - timedelta(hours=1),
            end_utc=now + timedelta(hours=23),
            slot_code="1234",
            slot_name="Smith",
            last_four="5678",
            raw_attributes="{}",
        )
        db_session.add(event)
        db_session.commit()

        app = create_app()
        client = TestClient(app)

        # Direct GET to auth page
        response = client.get("/guest/authorize")
        assert response.status_code == 200

        # POST booking code
        response = client.post(
            "/guest/authorize",
            data={"code": "1234", "device_id": "device456"},
            headers={"X-MAC-Address": "AA:BB:CC:DD:EE:FF"},
        )

        assert response.status_code == 200

    async def test_redirect_access_booking_auth(self, db_session: Session) -> None:
        """Redirect from detection URL with booking code."""
        config = HAIntegrationConfig(
            integration_id="rental1",
            auth_attribute="slot_code",
            checkout_grace_minutes=15,
        )
        db_session.add(config)

        now = datetime.now(timezone.utc)
        event = RentalControlEvent(
            integration_id="rental1",
            event_index=0,
            start_utc=now - timedelta(hours=1),
            end_utc=now + timedelta(hours=23),
            slot_code="5678",
            slot_name="Doe",
            last_four="1234",
            raw_attributes="{}",
        )
        db_session.add(event)
        db_session.commit()

        app = create_app()
        client = TestClient(app)

        # Access via detection URL
        response = client.get("/hotspot-detect.html?continue=http://example.com/page")

        # Should redirect to auth
        assert response.status_code in [200, 302, 307]
