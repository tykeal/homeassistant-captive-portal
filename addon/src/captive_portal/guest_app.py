# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Guest-only FastAPI app factory.

Creates a stripped-down FastAPI application that serves **only** guest,
captive-detection, and health routes.  Admin routes are never imported
and therefore unreachable by design.

This module is the entry point for the guest listener's uvicorn process
(``captive_portal.guest_app:create_guest_app``).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, Request, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from captive_portal.config.settings import AppSettings
from captive_portal.persistence.database import (
    create_db_engine,
    dispose_engine,
    init_db,
)
from captive_portal.web.middleware.security_headers import SecurityHeadersMiddleware

logger = logging.getLogger("captive_portal.guest")

# Package-relative paths for static assets
_THEMES_DIR = Path(__file__).resolve().parent / "web" / "themes"

# Guest-specific Content-Security-Policy (stricter than ingress: no framing)
_GUEST_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "object-src 'none'"
)


def _make_guest_lifespan(
    settings: AppSettings,
) -> Callable[..., Any]:
    """Build a lifespan context manager bound to *settings*.

    Args:
        settings: Application settings to apply on startup.

    Returns:
        An async context manager suitable for ``FastAPI(lifespan=...)``.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Manage guest application startup and shutdown.

        Args:
            app: The FastAPI application instance.

        Yields:
            Control to the application after startup completes.
        """
        # --- Startup ---
        log_cfg = settings.to_log_config()
        if not logging.getLogger().handlers:
            logging.basicConfig(**log_cfg)

        settings.log_effective(logger)

        settings.validate_db_path()

        try:
            engine = create_db_engine(f"sqlite:///{settings.db_path}")
            init_db(engine)
            logger.info("Guest listener database initialized at %s", settings.db_path)
        except Exception:
            dispose_engine()
            raise

        yield

        # --- Shutdown ---
        dispose_engine()
        logger.info("Guest listener database connections closed.")

    return lifespan


def create_guest_app(settings: AppSettings | None = None) -> FastAPI:
    """Create and configure the guest-only FastAPI application.

    This factory produces a FastAPI app that registers **only** guest,
    captive-detection, and health routers.  Admin routes are never
    imported and are therefore unreachable on the guest listener.

    Args:
        settings: Optional application settings.  When ``None``,
            ``AppSettings.load()`` is called to resolve configuration.

    Returns:
        Configured FastAPI application with guest routes only.
    """
    if settings is None:
        settings = AppSettings.load()

    if not settings.guest_external_url:
        logger.warning(
            "guest_external_url is not configured. "
            "Captive portal detection redirects will use relative paths. "
            "Set guest_external_url in addon options or via the CP_GUEST_EXTERNAL_URL "
            "environment variable for correct redirect URLs."
        )

    app = FastAPI(
        title="Captive Portal Guest Access — Guest Listener",
        docs_url=None,
        redoc_url=None,
        lifespan=_make_guest_lifespan(settings),
    )

    # Store guest external URL in app state for route handlers
    app.state.guest_external_url = settings.guest_external_url

    # Security headers middleware — stricter policy for guest listener
    app.add_middleware(
        SecurityHeadersMiddleware,
        frame_options="DENY",
        csp=_GUEST_CSP,
    )

    # NO SessionMiddleware — guest routes do not use admin sessions

    # Mount static files for themes
    if _THEMES_DIR.is_dir():
        app.mount(
            "/static/themes",
            StaticFiles(directory=str(_THEMES_DIR)),
            name="themes",
        )
    else:
        msg = (
            "Static themes directory '%s' not found; "
            "templates expect assets under '/static/themes'. "
            "Verify that static theme files are included in the deployment."
        )
        raise RuntimeError(msg % _THEMES_DIR)

    # Register ONLY guest, captive-detection, and health routers
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

    # Root redirect: GET / → /guest/authorize (not admin portal-settings)
    @app.get("/")
    async def guest_root_redirect(request: Request) -> RedirectResponse:
        """Redirect root to guest authorization page.

        Args:
            request: Incoming HTTP request.

        Returns:
            303 redirect to the guest authorization page.
        """
        return RedirectResponse(
            url="/guest/authorize",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return app
