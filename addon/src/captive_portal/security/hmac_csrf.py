# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""HMAC-signed CSRF tokens for cookie-restricted environments.

Provides stateless CSRF protection that works in iOS Captive Network
Assistant (CNA) and other restricted WebViews where cookies are not
reliably persisted between GET and POST requests.

The token embeds a random nonce and UTC timestamp, signed with
HMAC-SHA256.  Validation verifies the signature and checks the
timestamp falls within a configurable expiry window.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

from fastapi import HTTPException, Request, status


def _default_secret() -> str:
    """Generate a default per-process secret key."""
    return secrets.token_hex(32)


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
    """

    secret_key: str = field(default_factory=_default_secret)
    form_field_name: str = "csrf_token"
    header_name: str = "X-CSRF-Token"
    max_age_seconds: int = 900  # 15 minutes


class HMACCSRFProtection:
    """CSRF protection using HMAC-signed tokens.

    Unlike the double-submit cookie pattern, this approach embeds the
    token only in the HTML form.  The server validates the token by
    verifying its HMAC signature and checking the embedded timestamp.
    No cookie round-trip is required.
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
        the HMAC signature, and checks the timestamp is within the
        configured expiry window.

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

    async def _extract_request_token(self, request: Request) -> Optional[str]:
        """Extract CSRF token from form field or header.

        Args:
            request: Incoming HTTP request.

        Returns:
            Token string or None if not found.
        """
        header_token = request.headers.get(self.config.header_name)
        if header_token:
            return header_token

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

        return None
