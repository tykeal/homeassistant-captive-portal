# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Guest listener route and middleware registration helpers."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from captive_portal.config.settings import AppSettings
from captive_portal.guest_debug import DebugLoggingMiddleware
from captive_portal.guest_errors import register_guest_exception_handlers
from captive_portal.web.middleware.security_headers import SecurityHeadersMiddleware

_GUEST_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "base-uri 'self'; "
    "frame-ancestors 'self'; "
    "object-src 'none'"
)


def configure_guest_middleware(app: FastAPI, settings: AppSettings) -> None:
    """Install guest listener middleware.

    Args:
        app: Guest FastAPI application.
        settings: Application settings.
    """
    app.add_middleware(
        SecurityHeadersMiddleware,
        frame_options="SAMEORIGIN",
        csp=_GUEST_CSP,
    )
    app.add_middleware(
        DebugLoggingMiddleware,
        debug_enabled=settings.debug_guest_portal,
    )


def mount_guest_static(app: FastAPI, themes_dir: Path) -> None:
    """Mount guest static theme assets.

    Args:
        app: Guest FastAPI application.
        themes_dir: Path-like object for the themes directory.

    Raises:
        RuntimeError: If the theme directory is missing.
    """
    if themes_dir.is_dir():
        app.mount(
            "/static/themes",
            StaticFiles(directory=str(themes_dir)),
            name="themes",
        )
        return

    msg = (
        "Static themes directory '%s' not found; "
        "templates expect assets under '/static/themes'. "
        "Verify that static theme files are included in the deployment."
    )
    raise RuntimeError(msg % themes_dir)


def include_guest_routers(app: FastAPI) -> None:
    """Register only guest-safe routers on *app*.

    Args:
        app: Guest FastAPI application.
    """
    from captive_portal.api.routes import (
        booking_authorize,
        captive_detect,
        guest_portal,
        health,
    )

    app.include_router(captive_detect.router)
    app.include_router(guest_portal.router)
    app.include_router(booking_authorize.router)
    app.include_router(health.router)


def register_guest_root_redirect(app: FastAPI) -> None:
    """Register the guest root redirect route.

    Args:
        app: Guest FastAPI application.
    """

    @app.get("/")
    async def guest_root_redirect(request: Request) -> RedirectResponse:
        """Redirect root to guest authorization page.

        Args:
            request: Incoming HTTP request.

        Returns:
            303 redirect to the guest authorization page.
        """
        guest_url: str = getattr(request.app.state, "guest_external_url", "")
        base = guest_url if guest_url else ""
        return RedirectResponse(
            url=f"{base}/guest/authorize",
            status_code=status.HTTP_303_SEE_OTHER,
        )


def register_guest_routes_and_handlers(app: FastAPI) -> None:
    """Register guest routes and exception handlers on *app*.

    Args:
        app: Guest FastAPI application.
    """
    include_guest_routers(app)
    register_guest_root_redirect(app)
    register_guest_exception_handlers(app)
