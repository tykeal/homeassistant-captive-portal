# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for HADiscoveryError exception hierarchy (T006)."""

import pytest


class TestHADiscoveryErrorBase:
    """Tests for the base HADiscoveryError exception."""

    def test_base_error_carries_user_message(self) -> None:
        """HADiscoveryError stores user_message attribute."""
        from captive_portal.integrations.ha_errors import HADiscoveryError

        err = HADiscoveryError(user_message="Something went wrong")
        assert err.user_message == "Something went wrong"

    def test_base_error_carries_detail(self) -> None:
        """HADiscoveryError stores detail attribute with diagnostics."""
        from captive_portal.integrations.ha_errors import HADiscoveryError

        err = HADiscoveryError(
            user_message="Connection failed",
            detail="httpx.ConnectError: [Errno 111] Connection refused",
        )
        assert err.detail == "httpx.ConnectError: [Errno 111] Connection refused"

    def test_base_error_detail_defaults_to_empty(self) -> None:
        """HADiscoveryError detail defaults to empty string."""
        from captive_portal.integrations.ha_errors import HADiscoveryError

        err = HADiscoveryError(user_message="Oops")
        assert err.detail == ""

    def test_str_returns_user_message_only(self) -> None:
        """str(HADiscoveryError) returns only user_message, not detail."""
        from captive_portal.integrations.ha_errors import HADiscoveryError

        err = HADiscoveryError(
            user_message="Safe message",
            detail="SECRET: token=abc123",
        )
        result = str(err)
        assert result == "Safe message"
        assert "SECRET" not in result
        assert "abc123" not in result

    def test_base_error_is_exception(self) -> None:
        """HADiscoveryError inherits from Exception."""
        from captive_portal.integrations.ha_errors import HADiscoveryError

        assert issubclass(HADiscoveryError, Exception)

    def test_base_error_can_be_raised_and_caught(self) -> None:
        """HADiscoveryError can be raised and caught as Exception."""
        from captive_portal.integrations.ha_errors import HADiscoveryError

        with pytest.raises(HADiscoveryError, match="test message"):
            raise HADiscoveryError(user_message="test message")


class TestHAConnectionError:
    """Tests for HAConnectionError subclass."""

    def test_inherits_from_base(self) -> None:
        """HAConnectionError is a subclass of HADiscoveryError."""
        from captive_portal.integrations.ha_errors import (
            HAConnectionError,
            HADiscoveryError,
        )

        assert issubclass(HAConnectionError, HADiscoveryError)

    def test_can_be_caught_as_base(self) -> None:
        """HAConnectionError can be caught as HADiscoveryError."""
        from captive_portal.integrations.ha_errors import (
            HAConnectionError,
            HADiscoveryError,
        )

        with pytest.raises(HADiscoveryError):
            raise HAConnectionError(
                user_message="Cannot connect to Home Assistant",
                detail="ConnectError: refused",
            )

    def test_str_returns_safe_message(self) -> None:
        """str(HAConnectionError) returns only user_message."""
        from captive_portal.integrations.ha_errors import HAConnectionError

        err = HAConnectionError(
            user_message="Cannot connect",
            detail="host=192.168.1.100 port=8123",
        )
        assert str(err) == "Cannot connect"


class TestHAAuthenticationError:
    """Tests for HAAuthenticationError subclass (HTTP 401)."""

    def test_inherits_from_base(self) -> None:
        """HAAuthenticationError is a subclass of HADiscoveryError."""
        from captive_portal.integrations.ha_errors import (
            HAAuthenticationError,
            HADiscoveryError,
        )

        assert issubclass(HAAuthenticationError, HADiscoveryError)

    def test_can_be_caught_as_base(self) -> None:
        """HAAuthenticationError can be caught as HADiscoveryError."""
        from captive_portal.integrations.ha_errors import (
            HAAuthenticationError,
            HADiscoveryError,
        )

        with pytest.raises(HADiscoveryError):
            raise HAAuthenticationError(user_message="Invalid token")

    def test_str_returns_safe_message(self) -> None:
        """str(HAAuthenticationError) returns only user_message."""
        from captive_portal.integrations.ha_errors import HAAuthenticationError

        err = HAAuthenticationError(
            user_message="Authentication failed",
            detail="Bearer token=eyJ...",
        )
        assert str(err) == "Authentication failed"
        assert "eyJ" not in str(err)


class TestHATimeoutError:
    """Tests for HATimeoutError subclass."""

    def test_inherits_from_base(self) -> None:
        """HATimeoutError is a subclass of HADiscoveryError."""
        from captive_portal.integrations.ha_errors import (
            HADiscoveryError,
            HATimeoutError,
        )

        assert issubclass(HATimeoutError, HADiscoveryError)

    def test_can_be_caught_as_base(self) -> None:
        """HATimeoutError can be caught as HADiscoveryError."""
        from captive_portal.integrations.ha_errors import (
            HADiscoveryError,
            HATimeoutError,
        )

        with pytest.raises(HADiscoveryError):
            raise HATimeoutError(user_message="Request timed out")

    def test_str_returns_safe_message(self) -> None:
        """str(HATimeoutError) returns only user_message."""
        from captive_portal.integrations.ha_errors import HATimeoutError

        err = HATimeoutError(
            user_message="Timed out",
            detail="ReadTimeout after 10s to http://supervisor/core/api/states",
        )
        assert str(err) == "Timed out"
        assert "supervisor" not in str(err)


class TestHAServerError:
    """Tests for HAServerError subclass (HTTP 5xx)."""

    def test_inherits_from_base(self) -> None:
        """HAServerError is a subclass of HADiscoveryError."""
        from captive_portal.integrations.ha_errors import (
            HADiscoveryError,
            HAServerError,
        )

        assert issubclass(HAServerError, HADiscoveryError)

    def test_can_be_caught_as_base(self) -> None:
        """HAServerError can be caught as HADiscoveryError."""
        from captive_portal.integrations.ha_errors import (
            HADiscoveryError,
            HAServerError,
        )

        with pytest.raises(HADiscoveryError):
            raise HAServerError(user_message="Home Assistant server error")

    def test_str_returns_safe_message(self) -> None:
        """str(HAServerError) returns only user_message."""
        from captive_portal.integrations.ha_errors import HAServerError

        err = HAServerError(
            user_message="Server error",
            detail="HTTP 502: Bad Gateway from http://supervisor/core/api",
        )
        assert str(err) == "Server error"
        assert "502" not in str(err)
