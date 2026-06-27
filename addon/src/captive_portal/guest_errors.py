# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Guest listener exception handler registration."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException

from captive_portal._version import __version__

_TEMPLATES_DIR = Path(__file__).resolve().parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.autoescape = True
templates.env.globals["app_version"] = __version__

_FRIENDLY_MESSAGES = {
    400: "There was a problem with your request.",
    403: "Access is not available at this time.",
    404: "The requested resource was not found.",
    409: "This device has already been authorized.",
    410: "This code has expired or is no longer valid.",
    429: "Too many attempts. Please wait a moment and try again.",
    500: "An internal error occurred.",
    502: "WiFi authorization could not be completed. Please try again or contact the host.",
    503: "The service is temporarily unavailable. Please try again later.",
}


def register_guest_exception_handlers(app: FastAPI) -> None:
    """Register guest-friendly HTML exception handlers on *app*.

    Args:
        app: Guest FastAPI application.
    """

    @app.exception_handler(HTTPException)
    async def guest_http_exception_handler(
        request: Request,
        exc: HTTPException,
    ) -> HTMLResponse:
        """Render a friendly HTML error page for guest portal errors.

        Args:
            request: Incoming HTTP request.
            exc: The HTTPException that was raised.

        Returns:
            HTMLResponse with the rendered error template.
        """
        error_message = str(exc.detail)
        friendly_title = _FRIENDLY_MESSAGES.get(
            exc.status_code,
            "Something went wrong",
        )

        retry_query = getattr(request.state, "retry_query", "")
        rp = request.scope.get("root_path", "")
        retry_url = f"{rp}/guest/authorize"
        if retry_query:
            retry_url += f"?{retry_query}"

        return templates.TemplateResponse(
            request=request,
            name="guest/error.html",
            context={
                "error_message": error_message,
                "error_title": friendly_title,
                "status_code": exc.status_code,
                "retry_url": retry_url,
            },
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def guest_validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> HTMLResponse:
        """Render friendly HTML for request validation errors.

        Args:
            request: Incoming HTTP request.
            exc: The RequestValidationError that was raised.

        Returns:
            HTMLResponse with the rendered error template.
        """
        del exc
        return templates.TemplateResponse(
            request=request,
            name="guest/error.html",
            context={
                "error_message": "There was a problem with your request.",
                "error_title": "There was a problem with your request.",
                "status_code": 422,
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
