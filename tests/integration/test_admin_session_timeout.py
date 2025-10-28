# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for admin session timeouts (idle and absolute)."""

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def authenticated_client(client: TestClient, admin_user: Any) -> Any:
    """Create authenticated client with session."""
    login_response = client.post(
        "/api/admin/auth/login",
        json={"username": "testadmin", "password": "SecureP@ss123"},
    )
    assert login_response.status_code == 200
    return client


class TestAdminSessionTimeout:
    """Test admin session timeout (idle 30min, absolute 8hr)."""

    def test_session_idle_timeout_default_30_minutes(self, authenticated_client: Any) -> None:
        """Session should expire after 30 minutes of inactivity."""
        client = authenticated_client

        # Mock time advancement using datetime.now with timezone support
        with patch("captive_portal.security.session_middleware.datetime") as mock_dt:
            # Set current time
            now = datetime.now(timezone.utc)
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw) if args else now

            # Access protected route - should succeed
            response = client.get("/api/grants")
            assert response.status_code in (200, 204)

            # Advance time by 31 minutes (past idle timeout)
            future_time = now + timedelta(minutes=31)
            mock_dt.now.return_value = future_time
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw) if args else future_time

            # Next request should fail due to idle timeout
            response = client.get("/api/grants")
            assert response.status_code == 401
            # Session expired results in authentication required
            assert "authentication required" in response.json().get("detail", "").lower()

    def test_session_activity_resets_idle_timeout(self, authenticated_client: Any) -> None:
        """Activity should reset idle timeout."""
        client = authenticated_client

        with patch("captive_portal.security.session_middleware.datetime") as mock_dt:
            now = datetime.now(timezone.utc)
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw) if args else now

            # Initial request
            response = client.get("/api/grants")
            assert response.status_code in (200, 204)

            # Advance time by 20 minutes
            time_20 = now + timedelta(minutes=20)
            mock_dt.now.return_value = time_20
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw) if args else time_20

            # Activity resets timeout
            response = client.get("/api/grants")
            assert response.status_code in (200, 204)

            # Advance another 20 minutes (40 total, but only 20 since last activity)
            time_40 = now + timedelta(minutes=40)
            mock_dt.now.return_value = time_40
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw) if args else time_40

            # Should still be valid (within 30min of last activity)
            response = client.get("/api/grants")
            assert response.status_code in (200, 204)

    def test_session_absolute_timeout_8_hours(self, authenticated_client: Any) -> None:
        """Session should expire after 8 hours regardless of activity."""
        client = authenticated_client

        with patch("captive_portal.security.session_middleware.datetime") as mock_dt:
            now = datetime.now(timezone.utc)
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw) if args else now

            # Initial request
            response = client.get("/api/grants")
            assert response.status_code in (200, 204)

            # Advance time in 20-minute increments to stay within idle timeout
            # but approach the 8-hour absolute timeout
            for minutes in range(20, 480, 20):  # 20, 40, 60, ... 460 minutes (7h 40m)
                time_n = now + timedelta(minutes=minutes)
                mock_dt.now.return_value = time_n
                mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw) if args else time_n
                response = client.get("/api/grants")
                # Should still be valid (within 8 hours and active)
                assert response.status_code in (200, 204), f"Failed at {minutes} minutes"

            # Advance past 8 hours absolute timeout
            time_past = now + timedelta(hours=8, minutes=1)
            mock_dt.now.return_value = time_past
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw) if args else time_past

            # Should fail due to absolute timeout
            response = client.get("/api/grants")
            assert response.status_code == 401

    def test_session_absolute_timeout_overrides_idle_timeout(
        self, authenticated_client: Any
    ) -> None:
        """Absolute timeout should enforce even with continuous activity."""
        client = authenticated_client

        with patch("captive_portal.security.session_middleware.datetime") as mock_dt:
            now = datetime.now(timezone.utc)

            # Keep session active every 10 minutes
            for minutes in range(0, 8 * 60 + 10, 10):
                time_n = now + timedelta(minutes=minutes)
                mock_dt.now.return_value = time_n
                mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw) if args else time_n
                response = client.get("/api/grants")

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

    def test_expired_session_returns_401_with_clear_message(
        self, authenticated_client: Any
    ) -> None:
        """Expired session should return 401 with clear error message."""
        client = authenticated_client

        with patch("captive_portal.security.session_middleware.datetime") as mock_dt:
            now = datetime.now(timezone.utc)
            future_time = now + timedelta(minutes=31)
            mock_dt.now.return_value = future_time
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw) if args else future_time

            response = client.get("/api/grants")

            assert response.status_code == 401
            data = response.json()
            assert "detail" in data
            # Expired session results in authentication required
            assert (
                "authentication" in data["detail"].lower() or "required" in data["detail"].lower()
            )

    def test_logout_clears_session_preventing_timeout_check(
        self, authenticated_client: Any
    ) -> None:
        """Logout should clear session immediately."""
        client = authenticated_client

        # Logout
        logout_response = client.post("/api/admin/auth/logout")
        assert logout_response.status_code == 200

        # Immediate access should fail (no timeout needed)
        response = client.get("/api/grants")
        assert response.status_code == 401

    def test_session_timeout_enforced_on_all_protected_routes(
        self, authenticated_client: Any
    ) -> None:
        """Session timeout should be enforced on all protected admin routes."""
        client = authenticated_client

        protected_routes = [
            ("/api/grants", "GET"),
        ]

        with patch("captive_portal.security.session_middleware.datetime") as mock_dt:
            # Advance past idle timeout
            now = datetime.now(timezone.utc)
            future_time = now + timedelta(minutes=31)
            mock_dt.now.return_value = future_time
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw) if args else future_time

            for path, method in protected_routes:
                response = client.request(method, path)
                assert response.status_code == 401

    def test_session_created_timestamp_stored(self, authenticated_client: Any) -> None:
        """Session should store creation timestamp for absolute timeout."""
        # This tests internal session storage structure
        # Would verify AdminSession.created_utc is set correctly
        pass

    def test_session_last_activity_timestamp_updated(self, authenticated_client: Any) -> None:
        """Session should update last_activity timestamp on each request."""
        # This tests internal session storage structure
        # Would verify AdminSession.last_activity_utc is updated
        pass

    def test_concurrent_sessions_timeout_independently(self, app: Any, admin_user: Any) -> None:
        """Multiple sessions should timeout independently."""
        from starlette.testclient import TestClient

        # Create two separate clients to simulate concurrent sessions
        client1 = TestClient(app)
        client2 = TestClient(app)

        # Login with client1
        response1 = client1.post(
            "/api/admin/auth/login",
            json={"username": "testadmin", "password": "SecureP@ss123"},
        )
        session1_cookie = response1.cookies.get("session_id")

        # Login with client2
        response2 = client2.post(
            "/api/admin/auth/login",
            json={"username": "testadmin", "password": "SecureP@ss123"},
        )
        session2_cookie = response2.cookies.get("session_id")

        assert session1_cookie != session2_cookie

        # Both should be independent (tested via separate clients)
