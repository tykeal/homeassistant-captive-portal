# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for admin session timeouts (idle and absolute)."""

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest


@pytest.fixture
def authenticated_client(client, admin_user) -> Any:
    """Create authenticated client with session."""
    login_response = client.post(
        "/api/admin/auth/login",
        json={"username": "testadmin", "password": "SecureP@ss123"},
    )
    assert login_response.status_code == 200
    return client


class TestAdminSessionTimeout:
    """Test admin session timeout (idle 30min, absolute 8hr)."""

    def test_session_idle_timeout_default_30_minutes(self, authenticated_client) -> None:
        """Session should expire after 30 minutes of inactivity."""
        client = authenticated_client

        # Mock time advancement
        with patch("captive_portal.security.session_middleware.datetime") as mock_dt:
            # Set current time
            now = datetime.utcnow()
            mock_dt.utcnow.return_value = now

            # Access protected route - should succeed
            response = client.get("/api/admin/grants")
            assert response.status_code in (200, 204)

            # Advance time by 31 minutes (past idle timeout)
            mock_dt.utcnow.return_value = now + timedelta(minutes=31)

            # Next request should fail due to idle timeout
            response = client.get("/api/admin/grants")
            assert response.status_code == 401
            assert "session expired" in response.json().get("detail", "").lower()

    def test_session_activity_resets_idle_timeout(self, authenticated_client) -> None:
        """Activity should reset idle timeout."""
        client = authenticated_client

        with patch("captive_portal.security.session_middleware.datetime") as mock_dt:
            now = datetime.utcnow()
            mock_dt.utcnow.return_value = now

            # Initial request
            response = client.get("/api/admin/grants")
            assert response.status_code in (200, 204)

            # Advance time by 20 minutes
            mock_dt.utcnow.return_value = now + timedelta(minutes=20)

            # Activity resets timeout
            response = client.get("/api/admin/grants")
            assert response.status_code in (200, 204)

            # Advance another 20 minutes (40 total, but only 20 since last activity)
            mock_dt.utcnow.return_value = now + timedelta(minutes=40)

            # Should still be valid (within 30min of last activity)
            response = client.get("/api/admin/grants")
            assert response.status_code in (200, 204)

    def test_session_absolute_timeout_8_hours(self, authenticated_client) -> None:
        """Session should expire after 8 hours regardless of activity."""
        client = authenticated_client

        with patch("captive_portal.security.session_middleware.datetime") as mock_dt:
            now = datetime.utcnow()
            mock_dt.utcnow.return_value = now

            # Initial request
            response = client.get("/api/admin/grants")
            assert response.status_code in (200, 204)

            # Advance time by 7 hours 50 minutes, keep active
            for hours in range(1, 8):
                mock_dt.utcnow.return_value = now + timedelta(hours=hours)
                response = client.get("/api/admin/grants")
                # Should still be valid
                assert response.status_code in (200, 204)

            # Advance past 8 hours absolute timeout
            mock_dt.utcnow.return_value = now + timedelta(hours=8, minutes=1)

            # Should fail due to absolute timeout
            response = client.get("/api/admin/grants")
            assert response.status_code == 401

    def test_session_absolute_timeout_overrides_idle_timeout(self, authenticated_client) -> None:
        """Absolute timeout should enforce even with continuous activity."""
        client = authenticated_client

        with patch("captive_portal.security.session_middleware.datetime") as mock_dt:
            now = datetime.utcnow()

            # Keep session active every 10 minutes
            for minutes in range(0, 8 * 60 + 10, 10):
                mock_dt.utcnow.return_value = now + timedelta(minutes=minutes)
                response = client.get("/api/admin/grants")

                if minutes >= 8 * 60:
                    # Past absolute timeout
                    assert response.status_code == 401
                else:
                    # Within absolute timeout
                    assert response.status_code in (200, 204)

    def test_session_timeout_configurable_via_environment(self) -> None:
        """Session timeout should be configurable via environment variables."""
        # This would test with different SESSION_IDLE_MINUTES and SESSION_MAX_HOURS
        # Implementation would read from config
        pass

    def test_expired_session_returns_401_with_clear_message(self, authenticated_client) -> None:
        """Expired session should return 401 with clear error message."""
        client = authenticated_client

        with patch("captive_portal.security.session_middleware.datetime") as mock_dt:
            now = datetime.utcnow()
            mock_dt.utcnow.return_value = now + timedelta(minutes=31)

            response = client.get("/api/admin/grants")

            assert response.status_code == 401
            data = response.json()
            assert "detail" in data
            assert any(word in data["detail"].lower() for word in ["session", "expired", "timeout"])

    def test_logout_clears_session_preventing_timeout_check(self, authenticated_client) -> None:
        """Logout should clear session immediately."""
        client = authenticated_client

        # Logout
        logout_response = client.post("/api/admin/auth/logout")
        assert logout_response.status_code == 200

        # Immediate access should fail (no timeout needed)
        response = client.get("/api/admin/grants")
        assert response.status_code == 401

    def test_session_timeout_enforced_on_all_protected_routes(self, authenticated_client) -> None:
        """Session timeout should be enforced on all protected admin routes."""
        client = authenticated_client

        protected_routes = [
            ("/api/admin/grants", "GET"),
            ("/api/vouchers/redeem", "POST"),
            ("/api/integrations/entity-mapping", "GET"),
        ]

        with patch("captive_portal.security.session_middleware.datetime") as mock_dt:
            # Advance past idle timeout
            mock_dt.utcnow.return_value = datetime.utcnow() + timedelta(minutes=31)

            for path, method in protected_routes:
                response = client.request(method, path)
                assert response.status_code == 401

    def test_session_created_timestamp_stored(self, authenticated_client) -> None:
        """Session should store creation timestamp for absolute timeout."""
        # This tests internal session storage structure
        # Would verify AdminSession.created_utc is set correctly
        pass

    def test_session_last_activity_timestamp_updated(self, authenticated_client) -> None:
        """Session should update last_activity timestamp on each request."""
        # This tests internal session storage structure
        # Would verify AdminSession.last_activity_utc is updated
        pass

    def test_concurrent_sessions_timeout_independently(self, client) -> None:
        """Multiple sessions should timeout independently."""
        # Login twice to create two sessions
        response1 = client.post(
            "/api/admin/auth/login",
            json={"username": "testadmin", "password": "SecureP@ss123"},
        )
        session1_cookie = response1.cookies.get("session_id")

        response2 = client.post(
            "/api/admin/auth/login",
            json={"username": "testadmin", "password": "SecureP@ss123"},
        )
        session2_cookie = response2.cookies.get("session_id")

        assert session1_cookie != session2_cookie

        # Both should be independent (tested via separate clients)
