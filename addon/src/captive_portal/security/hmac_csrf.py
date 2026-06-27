# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""HMAC-signed CSRF tokens for cookie-restricted environments.

Provides stateless CSRF protection that works in iOS Captive Network
Assistant (CNA) and other restricted WebViews where cookies are not
reliably persisted between GET and POST requests.

The token embeds a random nonce and UTC timestamp, signed with
HMAC-SHA256.  Validation verifies the signature, checks the timestamp
falls within a configurable expiry window, and validates the Origin or
Referer header to prevent cross-site replay.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

from fastapi import HTTPException, Request, status

_logger = logging.getLogger(__name__)


def _default_secret() -> str:
    """Generate a default per-process secret key."""
    return secrets.token_hex(32)


def _parse_host_header(host: str) -> tuple[str, int | None]:
    """Parse a Host header into (hostname, port).

    Handles IPv6 bracketed notation like ``[::1]:8099`` and plain
    ``hostname:port``.

    Args:
        host: Raw Host header value.

    Returns:
        Tuple of (lowercase hostname, port or None).
    """
    host = host.strip().lower()
    if not host:
        return ("", None)

    # Bracketed IPv6: [::1] or [::1]:8099
    if host.startswith("["):
        bracket_end = host.find("]")
        if bracket_end == -1:
            return (host, None)
        hostname = host[1:bracket_end]
        rest = host[bracket_end + 1 :]
        if rest.startswith(":"):
            try:
                return (hostname, int(rest[1:]))
            except ValueError:
                return (hostname, None)
        return (hostname, None)

    # Plain host or host:port — only treat last colon as port
    # separator if there's exactly one colon (i.e. not an IPv6
    # literal).  Bare IPv6 addresses like ::1 contain multiple
    # colons and should be returned as-is.
    if ":" in host:
        if host.count(":") > 1:
            # Bare (unbracketed) IPv6 literal
            return (host, None)
        head, _, tail = host.rpartition(":")
        try:
            return (head, int(tail))
        except ValueError:
            return (host, None)

    return (host, None)


@dataclass
class HMACCSRFConfig:
    """Configuration for HMAC-signed CSRF tokens.

    Attributes:
        secret_key: HMAC signing key. Defaults to a random
            per-process value (safe for single-process deployments).
        form_field_name: Name of the hidden form field carrying
            the token.
        header_name: Alternative HTTP header for AJAX requests.
        max_age_seconds: Maximum token age before expiry.
        check_origin: Whether to validate Origin/Referer headers.
    """

    secret_key: str = field(default_factory=_default_secret)
    form_field_name: str = "csrf_token"
    header_name: str = "X-CSRF-Token"
    max_age_seconds: int = 900  # 15 minutes
    check_origin: bool = True


class HMACCSRFProtection:
    """CSRF protection using HMAC-signed tokens.

    Unlike the double-submit cookie pattern, this approach embeds the
    token only in the HTML form.  The server validates the token by
    verifying its HMAC signature and checking the embedded timestamp.
    No cookie round-trip is required.

    When ``check_origin`` is enabled (default), the ``Origin`` or
    ``Referer`` header is validated to ensure the POST originates
    from the same host that served the form.  This prevents
    cross-site token replay.
    """

    def __init__(self, config: Optional[HMACCSRFConfig] = None) -> None:
        """Initialize HMAC CSRF protection.

        Args:
            config: Optional configuration overrides.
        """
        self.config = config or HMACCSRFConfig()

    def generate_token(self) -> str:
        """Generate a signed CSRF token.

        Returns:
            Base64url-encoded token containing nonce, timestamp,
            and HMAC signature.
        """
        nonce = secrets.token_hex(16)
        timestamp = str(int(time.time()))
        payload = f"{nonce}:{timestamp}"
        signature = hmac.new(
            self.config.secret_key.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        token = f"{payload}.{signature}"
        return base64.urlsafe_b64encode(token.encode()).decode()

    async def validate_token(self, request: Request) -> None:
        """Validate CSRF token from the request.

        Extracts the token from the form field or header, verifies
        the HMAC signature, checks the timestamp is within the
        configured expiry window, and validates the Origin/Referer
        header when ``check_origin`` is enabled.

        Args:
            request: Incoming HTTP request.

        Raises:
            HTTPException: 403 if validation fails.
        """
        raw_token = await self._extract_request_token(request)
        if not raw_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token missing",
            )

        if self.config.check_origin:
            self._validate_origin(request)

        try:
            decoded = base64.urlsafe_b64decode(
                raw_token.encode(),
            ).decode()
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid CSRF token encoding",
            )

        parts = decoded.rsplit(".", 1)
        if len(parts) != 2:  # noqa: PLR2004
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Malformed CSRF token",
            )

        payload, provided_sig = parts

        expected_sig = hmac.new(
            self.config.secret_key.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(provided_sig, expected_sig):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token signature invalid",
            )

        # Verify timestamp
        payload_parts = payload.split(":")
        if len(payload_parts) != 2:  # noqa: PLR2004
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Malformed CSRF token payload",
            )

        try:
            token_time = int(payload_parts[1])
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid CSRF token timestamp",
            )

        age = int(time.time()) - token_time
        if age < 0 or age > self.config.max_age_seconds:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token expired",
            )

    def _validate_origin(self, request: Request) -> None:
        """Verify the request Origin or Referer matches the server host.

        iOS CNA and some WebViews may omit these headers, so a
        missing header is allowed — only a *mismatched* header is
        rejected.  Comparison normalises hostnames to lowercase and
        strips default ports based on scheme (80 for HTTP, 443 for
        HTTPS).

        Args:
            request: Incoming HTTP request.

        Raises:
            HTTPException: 403 if the origin does not match.
        """
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")

        if not origin and not referer:
            # Headers absent — allow (CNA may strip them)
            return

        source_url = origin if origin else referer
        if source_url is None:  # pragma: no cover – defensive
            return

        parsed = urlparse(source_url)
        source_hostname = (parsed.hostname or "").lower()
        source_port = parsed.port
        source_scheme = (parsed.scheme or "").lower()

        # Resolve request hostname and port.  Prefer structured URL
        # attributes to avoid mis-parsing IPv6 Host headers like
        # "[::1]:8099".
        url_hostname = getattr(request.url, "hostname", None)
        url_port = getattr(request.url, "port", None)

        if url_hostname:
            request_hostname = url_hostname.lower()
            request_port: int | None = url_port
        else:
            request_hostname, request_port = _parse_host_header(
                request.headers.get("host", ""),
            )

        # Strip the default port for the source scheme so that
        # http://host:80 matches http://host.
        _scheme_default: dict[str, int] = {"http": 80, "https": 443}
        default_port = _scheme_default.get(source_scheme)
        if default_port is not None:
            if source_port == default_port:
                source_port = None
            if request_port == default_port:
                request_port = None

        if source_hostname != request_hostname or source_port != request_port:
            _logger.warning(
                "CSRF origin mismatch: source=%s host=%s",
                source_url,
                request.headers.get("host", ""),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF origin validation failed",
            )

    async def _extract_request_token(self, request: Request) -> Optional[str]:
        """Extract CSRF token from header, form body, or query string.

        The query-string path is restricted to GET requests and exists
        as a workaround for captive-portal gateways that drop POST
        bodies, forcing form submission via GET.

        Args:
            request: Incoming HTTP request.

        Returns:
            Token string or None if not found.
        """
        # 1. Check header (always)
        header_token = request.headers.get(self.config.header_name)
        if header_token:
            return header_token

        # 2. Check form body (content-type gated, any method)
        content_type = request.headers.get("content-type", "")
        if (
            "application/x-www-form-urlencoded" in content_type
            or "multipart/form-data" in content_type
        ):
            try:
                form = await request.form()
                token = form.get(self.config.form_field_name)
                if isinstance(token, str):
                    return token
            except Exception:
                pass

        # 3. Check query params for GET (captive portal workaround)
        if request.method == "GET":
            token = request.query_params.get(
                self.config.form_field_name,
            )
            if isinstance(token, str):
                return token

        return None
