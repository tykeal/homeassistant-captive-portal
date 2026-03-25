# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""
CSRF (Cross-Site Request Forgery) protection for admin forms.

Implements double-submit cookie pattern (D14):
- Stateless token validation
- Cookie + form field comparison
- 32-byte random tokens
- Constant-time comparison
"""

import secrets
from typing import Literal, Optional

from fastapi import HTTPException, Request, Response, status
from pydantic import BaseModel


class CSRFConfig(BaseModel):
    """CSRF protection configuration."""

    cookie_name: str = "csrftoken"
    form_field_name: str = "csrf_token"
    header_name: str = "X-CSRF-Token"
    cookie_secure: bool = True
    cookie_httponly: bool = False
    cookie_samesite: Literal["strict", "lax", "none"] = "strict"
    token_length: int = 32


class CSRFProtection:
    """CSRF protection using double-submit cookie pattern."""

    def __init__(self, config: Optional[CSRFConfig] = None):
        """Initialize CSRF protection."""
        self.config = config or CSRFConfig()

    def generate_token(self) -> str:
        """Generate a new CSRF token (32 bytes, base64-encoded)."""
        return secrets.token_urlsafe(self.config.token_length)

    async def validate_token(self, request: Request) -> None:
        """
        Validate CSRF token from request.

        Raises HTTPException 403 if validation fails.
        Compares cookie value with form field or header (constant-time).
        """
        cookie_token = request.cookies.get(self.config.cookie_name)
        if not cookie_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token missing from cookies",
            )

        request_token = await self._extract_request_token(request)
        if not request_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"CSRF token missing from form field '{self.config.form_field_name}' or header '{self.config.header_name}'",
            )

        if not secrets.compare_digest(cookie_token, request_token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token validation failed",
            )

    async def _extract_request_token(self, request: Request) -> Optional[str]:
        """Extract CSRF token from form field or header."""
        # Check header first (simpler)
        header_token = request.headers.get(self.config.header_name)
        if header_token:
            return header_token

        # Try to get from form data if content type is form-encoded
        content_type = request.headers.get("content-type", "")
        if (
            "application/x-www-form-urlencoded" in content_type
            or "multipart/form-data" in content_type
        ):
            try:
                form = await request.form()
                token = form.get(self.config.form_field_name)
                # Ensure we only return strings, not UploadFile objects
                if isinstance(token, str):
                    return token
            except Exception:
                pass

        return None

    def set_csrf_cookie(self, response: Response, token: str) -> None:
        """Set CSRF token in cookie."""
        response.set_cookie(
            key=self.config.cookie_name,
            value=token,
            httponly=self.config.cookie_httponly,
            secure=self.config.cookie_secure,
            samesite=self.config.cookie_samesite,
        )

    def get_token_from_request(self, request: Request) -> Optional[str]:
        """Get existing CSRF token from request cookie."""
        return request.cookies.get(self.config.cookie_name)


def get_csrf_protection() -> CSRFProtection:
    """FastAPI dependency for CSRF protection."""
    return CSRFProtection()
