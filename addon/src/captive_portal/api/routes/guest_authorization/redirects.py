# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Redirect and retry URL helpers for guest authorization."""

from __future__ import annotations

import urllib.parse
from uuid import UUID

from fastapi import Request, status
from fastapi.responses import RedirectResponse

from captive_portal.services.redirect_validator import RedirectValidator

from .context import GuestOmadaParams


def build_retry_query(params: GuestOmadaParams) -> str:
    """Build the current URL-encoded retry query string.

    Args:
        params: Captured Omada and redirect parameters.

    Returns:
        Encoded retry query string, or an empty string.
    """
    retry_params = params.retry_params()
    return urllib.parse.urlencode(retry_params) if retry_params else ""


def safe_redirect_destination(
    request: Request,
    continue_url: str | None,
    redirect_validator: RedirectValidator,
) -> str:
    """Choose the current safe success redirect destination.

    Args:
        request: Incoming FastAPI request.
        continue_url: Candidate success redirect.
        redirect_validator: Open-redirect validator.

    Returns:
        Safe continue URL or root-path-aware guest welcome fallback.
    """
    if continue_url and redirect_validator.is_safe(continue_url):
        return continue_url
    return f"{request.scope.get('root_path', '')}/guest/welcome"


def success_redirect(url: str, grant_id: UUID) -> RedirectResponse:
    """Create the current successful authorization redirect response.

    Args:
        url: Redirect destination.
        grant_id: Generated access grant ID to store in cookie.

    Returns:
        Redirect response with current headers and cookie attributes.
    """
    response = RedirectResponse(
        url=url,
        status_code=status.HTTP_303_SEE_OTHER,
    )
    response.headers["Referrer-Policy"] = "strict-origin"
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        key="grant_id",
        value=str(grant_id),
        httponly=True,
        samesite="strict",
        max_age=3600,
    )
    return response
