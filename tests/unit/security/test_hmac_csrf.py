# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for HMAC-signed CSRF token protection."""

from __future__ import annotations

import base64
import hashlib
import hmac as hmac_mod
import time
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from captive_portal.security.hmac_csrf import (
    HMACCSRFConfig,
    HMACCSRFProtection,
)


def _make_request(
    *,
    form_data: Optional[dict[str, str]] = None,
    headers: Optional[dict[str, str]] = None,
) -> AsyncMock:
    """Build a mock Request with optional form data and headers.

    Args:
        form_data: Key/value pairs returned by ``await request.form()``.
        headers: HTTP headers.

    Returns:
        Mock request object compatible with HMACCSRFProtection.
    """
    request = AsyncMock()
    hdrs = headers or {}
    if form_data is not None and "content-type" not in hdrs:
        hdrs["content-type"] = "application/x-www-form-urlencoded"
    request.headers = hdrs

    # Set url.hostname/port to None so validation falls back to
    # Host header parsing (which handles IPv6 correctly).
    url_mock = AsyncMock()
    url_mock.hostname = None
    url_mock.port = None
    request.url = url_mock

    async def _form() -> dict[str, str]:
        """Return form data."""
        return form_data or {}

    request.form = _form
    return request


class TestGenerateToken:
    """Tests for HMACCSRFProtection.generate_token."""

    def test_returns_string(self) -> None:
        """Token is a non-empty string."""
        csrf = HMACCSRFProtection()
        token = csrf.generate_token()
        assert isinstance(token, str)
        assert len(token) > 0

    def test_unique_tokens(self) -> None:
        """Two consecutive calls produce different tokens."""
        csrf = HMACCSRFProtection()
        assert csrf.generate_token() != csrf.generate_token()

    def test_token_is_base64url(self) -> None:
        """Token can be decoded as base64url."""
        csrf = HMACCSRFProtection()
        token = csrf.generate_token()
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        assert "." in decoded


class TestValidateToken:
    """Tests for HMACCSRFProtection.validate_token."""

    @pytest.mark.asyncio
    async def test_valid_token(self) -> None:
        """A freshly generated token validates successfully."""
        csrf = HMACCSRFProtection()
        token = csrf.generate_token()
        request = _make_request(form_data={"csrf_token": token})
        await csrf.validate_token(request)

    @pytest.mark.asyncio
    async def test_expired_token(self) -> None:
        """Token older than max_age_seconds is rejected."""
        config = HMACCSRFConfig(max_age_seconds=60)
        csrf = HMACCSRFProtection(config)

        with patch("captive_portal.security.hmac_csrf.time") as mock_time:
            mock_time.time.return_value = 1000.0
            token = csrf.generate_token()

            mock_time.time.return_value = 1061.0
            request = _make_request(
                form_data={"csrf_token": token},
            )
            with pytest.raises(HTTPException) as exc_info:
                await csrf.validate_token(request)
            assert exc_info.value.status_code == 403
            assert "expired" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_tampered_signature(self) -> None:
        """Modified signature is rejected."""
        csrf = HMACCSRFProtection()
        token = csrf.generate_token()

        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        payload, _sig = decoded.rsplit(".", 1)
        tampered = f"{payload}.{'a' * 64}"
        bad_token = base64.urlsafe_b64encode(
            tampered.encode(),
        ).decode()

        request = _make_request(form_data={"csrf_token": bad_token})
        with pytest.raises(HTTPException) as exc_info:
            await csrf.validate_token(request)
        assert exc_info.value.status_code == 403
        assert "signature" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_tampered_payload(self) -> None:
        """Modified payload (nonce changed) is rejected."""
        csrf = HMACCSRFProtection()
        token = csrf.generate_token()

        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        _payload, sig = decoded.rsplit(".", 1)
        tampered = f"tamperednonce:{int(time.time())}.{sig}"
        bad_token = base64.urlsafe_b64encode(
            tampered.encode(),
        ).decode()

        request = _make_request(form_data={"csrf_token": bad_token})
        with pytest.raises(HTTPException) as exc_info:
            await csrf.validate_token(request)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_missing_token(self) -> None:
        """No token in request raises 403."""
        csrf = HMACCSRFProtection()
        request = _make_request(form_data={})
        with pytest.raises(HTTPException) as exc_info:
            await csrf.validate_token(request)
        assert exc_info.value.status_code == 403
        assert "missing" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_malformed_base64(self) -> None:
        """Garbage base64 input raises 403."""
        csrf = HMACCSRFProtection()
        request = _make_request(
            form_data={"csrf_token": "not-valid-base64!!!"},
        )
        with pytest.raises(HTTPException) as exc_info:
            await csrf.validate_token(request)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_wrong_secret(self) -> None:
        """Token signed with different secret is rejected."""
        csrf1 = HMACCSRFProtection(
            HMACCSRFConfig(secret_key="secret-one"),
        )
        csrf2 = HMACCSRFProtection(
            HMACCSRFConfig(secret_key="secret-two"),
        )
        token = csrf1.generate_token()
        request = _make_request(form_data={"csrf_token": token})
        with pytest.raises(HTTPException) as exc_info:
            await csrf2.validate_token(request)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_validate_from_header(self) -> None:
        """Token in X-CSRF-Token header validates."""
        csrf = HMACCSRFProtection()
        token = csrf.generate_token()
        request = _make_request(
            headers={"X-CSRF-Token": token},
        )
        await csrf.validate_token(request)

    @pytest.mark.asyncio
    async def test_malformed_token_no_dot(self) -> None:
        """Token without dot separator raises 403."""
        csrf = HMACCSRFProtection()
        bad_token = base64.urlsafe_b64encode(
            b"nodothere",
        ).decode()
        request = _make_request(
            form_data={"csrf_token": bad_token},
        )
        with pytest.raises(HTTPException) as exc_info:
            await csrf.validate_token(request)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_future_timestamp_rejected(self) -> None:
        """Token with future timestamp (negative age) is rejected."""
        config = HMACCSRFConfig(secret_key="test-key")
        csrf = HMACCSRFProtection(config)

        future_ts = str(int(time.time()) + 3600)
        nonce = "a" * 32
        payload = f"{nonce}:{future_ts}"
        sig = hmac_mod.new(
            b"test-key",
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        raw = f"{payload}.{sig}"
        token = base64.urlsafe_b64encode(raw.encode()).decode()

        request = _make_request(form_data={"csrf_token": token})
        with pytest.raises(HTTPException) as exc_info:
            await csrf.validate_token(request)
        assert exc_info.value.status_code == 403
        assert "expired" in str(exc_info.value.detail).lower()


class TestCustomConfig:
    """Tests for custom HMACCSRFConfig values."""

    def test_custom_max_age(self) -> None:
        """Custom max_age_seconds is stored in config."""
        config = HMACCSRFConfig(max_age_seconds=30)
        csrf = HMACCSRFProtection(config)
        assert csrf.config.max_age_seconds == 30

    @pytest.mark.asyncio
    async def test_custom_form_field_name(self) -> None:
        """Custom form field name is used for extraction."""
        config = HMACCSRFConfig(form_field_name="my_token")
        csrf = HMACCSRFProtection(config)
        token = csrf.generate_token()
        request = _make_request(form_data={"my_token": token})
        await csrf.validate_token(request)

    @pytest.mark.asyncio
    async def test_custom_header_name(self) -> None:
        """Custom header name is used for extraction."""
        config = HMACCSRFConfig(header_name="X-My-Token")
        csrf = HMACCSRFProtection(config)
        token = csrf.generate_token()
        request = _make_request(headers={"X-My-Token": token})
        await csrf.validate_token(request)

    def test_default_secret_is_random(self) -> None:
        """Default config generates a unique secret each time."""
        c1 = HMACCSRFConfig()
        c2 = HMACCSRFConfig()
        assert c1.secret_key != c2.secret_key


class TestOriginValidation:
    """Tests for Origin/Referer header validation."""

    @pytest.mark.asyncio
    async def test_missing_origin_and_referer_allowed(self) -> None:
        """Request without Origin or Referer is allowed."""
        csrf = HMACCSRFProtection()
        token = csrf.generate_token()
        request = _make_request(form_data={"csrf_token": token})
        await csrf.validate_token(request)

    @pytest.mark.asyncio
    async def test_matching_origin_allowed(self) -> None:
        """Request with matching Origin header is allowed."""
        csrf = HMACCSRFProtection()
        token = csrf.generate_token()
        request = _make_request(
            form_data={"csrf_token": token},
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "origin": "http://portal.local",
                "host": "portal.local",
            },
        )
        await csrf.validate_token(request)

    @pytest.mark.asyncio
    async def test_mismatched_origin_rejected(self) -> None:
        """Request with mismatched Origin header is rejected."""
        csrf = HMACCSRFProtection()
        token = csrf.generate_token()
        request = _make_request(
            form_data={"csrf_token": token},
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "origin": "http://evil.example.com",
                "host": "portal.local",
            },
        )
        with pytest.raises(HTTPException) as exc_info:
            await csrf.validate_token(request)
        assert exc_info.value.status_code == 403
        assert "origin" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_matching_referer_allowed(self) -> None:
        """Request with matching Referer header is allowed."""
        csrf = HMACCSRFProtection()
        token = csrf.generate_token()
        request = _make_request(
            form_data={"csrf_token": token},
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "referer": "http://portal.local/guest/authorize",
                "host": "portal.local",
            },
        )
        await csrf.validate_token(request)

    @pytest.mark.asyncio
    async def test_mismatched_referer_rejected(self) -> None:
        """Request with mismatched Referer header is rejected."""
        csrf = HMACCSRFProtection()
        token = csrf.generate_token()
        request = _make_request(
            form_data={"csrf_token": token},
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "referer": "http://evil.example.com/attack",
                "host": "portal.local",
            },
        )
        with pytest.raises(HTTPException) as exc_info:
            await csrf.validate_token(request)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_origin_check_disabled(self) -> None:
        """Origin check can be disabled via config."""
        config = HMACCSRFConfig(check_origin=False)
        csrf = HMACCSRFProtection(config)
        token = csrf.generate_token()
        request = _make_request(
            form_data={"csrf_token": token},
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "origin": "http://evil.example.com",
                "host": "portal.local",
            },
        )
        await csrf.validate_token(request)

    @pytest.mark.asyncio
    async def test_default_port_normalization(self) -> None:
        """Origin with default port matches Host without port."""
        csrf = HMACCSRFProtection()
        token = csrf.generate_token()
        request = _make_request(
            form_data={"csrf_token": token},
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "origin": "http://portal.local:80",
                "host": "portal.local",
            },
        )
        await csrf.validate_token(request)

    @pytest.mark.asyncio
    async def test_host_with_port_matches_origin(self) -> None:
        """Host header with default port matches Origin without port."""
        csrf = HMACCSRFProtection()
        token = csrf.generate_token()
        request = _make_request(
            form_data={"csrf_token": token},
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "origin": "http://portal.local",
                "host": "portal.local:80",
            },
        )
        await csrf.validate_token(request)

    @pytest.mark.asyncio
    async def test_https_default_port_normalization(self) -> None:
        """HTTPS origin on port 443 matches Host without port."""
        csrf = HMACCSRFProtection()
        token = csrf.generate_token()
        request = _make_request(
            form_data={"csrf_token": token},
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "origin": "https://portal.local:443",
                "host": "portal.local",
            },
        )
        await csrf.validate_token(request)

    @pytest.mark.asyncio
    async def test_http_443_not_stripped(self) -> None:
        """Port 443 on http scheme is NOT treated as default."""
        csrf = HMACCSRFProtection()
        token = csrf.generate_token()
        request = _make_request(
            form_data={"csrf_token": token},
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "origin": "http://portal.local:443",
                "host": "portal.local",
            },
        )
        with pytest.raises(HTTPException) as exc_info:
            await csrf.validate_token(request)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_case_insensitive_origin(self) -> None:
        """Origin comparison is case-insensitive."""
        csrf = HMACCSRFProtection()
        token = csrf.generate_token()
        request = _make_request(
            form_data={"csrf_token": token},
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "origin": "http://Portal.Local",
                "host": "portal.local",
            },
        )
        await csrf.validate_token(request)

    @pytest.mark.asyncio
    async def test_ipv6_host_not_misread_as_port(self) -> None:
        """IPv6 Host header is not misinterpreted as hostname:port."""
        csrf = HMACCSRFProtection()
        token = csrf.generate_token()
        request = _make_request(
            form_data={"csrf_token": token},
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "origin": "http://[::1]:8099",
                "host": "[::1]:8099",
            },
        )
        await csrf.validate_token(request)

    @pytest.mark.asyncio
    async def test_bare_ipv6_host_allowed(self) -> None:
        """Bare (unbracketed) IPv6 Host like ::1 is parsed correctly."""
        config = HMACCSRFConfig(check_origin=False)
        csrf = HMACCSRFProtection(config)
        token = csrf.generate_token()
        request = _make_request(
            form_data={"csrf_token": token},
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "host": "::1",
            },
        )
        # No origin/referer so check is skipped; just verifying
        # _parse_host_header doesn't crash on bare IPv6.
        await csrf.validate_token(request)
