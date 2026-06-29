# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""GET form rendering helpers for guest authorization."""

from __future__ import annotations

import logging
from typing import cast

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from captive_portal.security.hmac_csrf import HMACCSRFProtection

from .context import GuestOmadaParams
from .errors import add_security_headers

_logger = logging.getLogger("captive_portal.guest")


def is_get_submission(code: str | None, csrf_token: str | None) -> bool:
    """Return whether the GET request should enter authorization flow.

    Args:
        code: Submitted code query value.
        csrf_token: Submitted CSRF token query value.

    Returns:
        True only when both values are non-empty.
    """
    return bool(code) and bool(csrf_token)


def redacted_query_params(request: Request) -> dict[str, str]:
    """Return query parameters with sensitive guest values redacted.

    Args:
        request: Incoming FastAPI request.

    Returns:
        Query parameters suitable for debug logging.
    """
    return {
        key: ("[REDACTED]" if key in {"code", "csrf_token"} else value)
        for key, value in request.query_params.items()
    }


def effective_continue_url(request: Request, params: GuestOmadaParams) -> str:
    """Select the current effective continue URL for the form.

    Args:
        request: Incoming FastAPI request.
        params: Captured Omada and redirect parameters.

    Returns:
        Continue URL using current continue, redirectUrl, then welcome fallback order.
    """
    return (
        params.continue_url
        or params.redirect_url
        or (f"{request.scope.get('root_path', '')}/guest/welcome")
    )


def log_get_submission_debug(request: Request) -> None:
    """Emit current debug log details for GET submissions.

    Args:
        request: Incoming FastAPI request.
    """
    _logger.debug(
        "GET %s (submission) query_params=%s",
        request.url.path,
        redacted_query_params(request),
    )


def log_form_debug(request: Request, params: GuestOmadaParams) -> None:
    """Emit current debug log details for GET form rendering.

    Args:
        request: Incoming FastAPI request.
        params: Captured Omada and redirect parameters.
    """
    form_action = f"{request.scope.get('root_path', '')}/guest/authorize"
    _logger.debug(
        "GET %s query_params=%s omada_params=%s",
        request.url.path,
        redacted_query_params(request),
        params.template_params(),
    )
    _logger.debug(
        "GET %s form_action=%s  User-Agent=%s",
        request.url.path,
        form_action,
        request.headers.get("user-agent", ""),
    )
    _logger.debug(
        "GET %s route_csp=%s",
        request.url.path,
        add_security_headers(HTMLResponse("")).headers.get("Content-Security-Policy", ""),
    )


def render_authorize_form(
    *,
    request: Request,
    templates: Jinja2Templates,
    csrf: HMACCSRFProtection,
    params: GuestOmadaParams,
) -> HTMLResponse:
    """Render the current guest authorization form response.

    Args:
        request: Incoming FastAPI request.
        templates: Configured Jinja2 template loader.
        csrf: Guest CSRF token generator.
        params: Captured Omada and redirect parameters.

    Returns:
        Template response with guest route security headers applied.
    """
    response = templates.TemplateResponse(
        request=request,
        name="guest/authorize.html",
        context={
            "continue_url": effective_continue_url(request, params),
            "csrf_token": csrf.generate_token(),
            "omada_params": params.template_params(),
        },
    )
    return cast(HTMLResponse, add_security_headers(response))
