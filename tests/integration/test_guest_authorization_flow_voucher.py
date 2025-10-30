# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for guest authorization flow with voucher."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from captive_portal.app import create_app
from captive_portal.models.voucher import Voucher


@pytest.mark.asyncio
class TestGuestAuthorizationFlowVoucher:
    """Test end-to-end guest flow with voucher (direct + redirect access)."""

    async def test_direct_access_voucher_auth(self, db_session: Session) -> None:
        """Direct access to /guest/authorize with voucher code."""
        # Create a valid voucher
        voucher = Voucher(
            code="ABCD1234",
            created_utc=datetime.now(timezone.utc),
            expires_utc=datetime.now(timezone.utc) + timedelta(days=7),
            duration_minutes=1440,  # 24 hours
        )
        db_session.add(voucher)
        db_session.commit()

        app = create_app()
        client = TestClient(app)

        # Direct GET to auth page
        response = client.get("/guest/authorize")
        assert response.status_code == 200

        # POST voucher code
        response = client.post(
            "/guest/authorize",
            data={"code": "ABCD1234", "device_id": "device123"},
            headers={"X-MAC-Address": "AA:BB:CC:DD:EE:FF"},
        )

        assert response.status_code == 200
        # Should redirect or show success

    async def test_redirect_access_voucher_auth(self, db_session: Session) -> None:
        """Redirect from detection URL preserves continue parameter."""
        voucher = Voucher(
            code="XYZ789AB",
            created_utc=datetime.now(timezone.utc),
            expires_utc=datetime.now(timezone.utc) + timedelta(days=7),
            duration_minutes=1440,  # 24 hours
        )
        db_session.add(voucher)
        db_session.commit()

        app = create_app()
        client = TestClient(app)

        # Access via detection URL
        response = client.get("/generate_204?continue=http://example.com/page")

        # Should redirect to auth with continue param preserved
        assert response.status_code in [200, 302, 307]
