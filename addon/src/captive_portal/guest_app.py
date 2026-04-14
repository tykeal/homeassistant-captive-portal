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
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException

from captive_portal.api.routes import booking_authorize
from captive_portal.config.settings import AppSettings
from captive_portal.persistence.database import (
    create_db_engine,
    dispose_engine,
    init_db,
)
from captive_portal.web.middleware.security_headers import SecurityHeadersMiddleware

logger = logging.getLogger("captive_portal.guest")

# Package-relative paths for static and template assets
_THEMES_DIR = Path(__file__).resolve().parent / "web" / "themes"
_TEMPLATES_DIR = Path(__file__).resolve().parent / "web" / "templates"

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.autoescape = True

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
            booking_authorize.set_db_engine(engine)
            logger.info("Guest listener database initialized at %s", settings.db_path)
        except Exception:
            dispose_engine()
            raise

        # Configure Omada controller integration (prefer DB config)
        from captive_portal.config.omada_config import build_omada_config
        from captive_portal.models.omada_config import OmadaConfig as _OmadaConfig

        from sqlmodel import Session as _Session, select as _select

        _omada_sess = _Session(engine)
        try:
            from typing import Any as _Any

            _stmt: _Any = _select(_OmadaConfig).where(_OmadaConfig.id == 1)
            _db_omada: _OmadaConfig | None = _omada_sess.exec(_stmt).first()
            if _db_omada and _db_omada.omada_configured:
                app.state.omada_config = await build_omada_config(_db_omada, logger)
            else:
                app.state.omada_config = await build_omada_config(settings, logger)
        finally:
            _omada_sess.close()

        if app.state.omada_config:
            logger.info("Omada controller configured.")
        else:
            logger.info("Omada controller not configured — controller calls will be skipped")

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

    # Store debug toggle in app state for route handlers
    app.state.debug_guest_portal = settings.debug_guest_portal

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

        Uses the configured guest_external_url when available so the
        redirect works correctly even behind DNS interception.

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

    # Custom exception handler: render error.html instead of JSON
    _friendly_messages = {
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

    @app.exception_handler(HTTPException)
    async def guest_http_exception_handler(
        request: Request,
        exc: HTTPException,
    ) -> HTMLResponse:
        """Render friendly HTML error page for guest portal errors.

        Maps HTTP status codes to user-friendly titles and renders
        the guest error template instead of returning raw JSON.

        Args:
            request: Incoming HTTP request.
            exc: The HTTPException that was raised.

        Returns:
            HTMLResponse with the rendered error template.
        """
        error_message = str(exc.detail)
        friendly_title = _friendly_messages.get(
            exc.status_code,
            "Something went wrong",
        )

        # Build retry URL preserving original Omada query params
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

        Catches FastAPI 422 validation errors (missing/invalid query
        or form parameters) and renders the guest error template.

        Args:
            request: Incoming HTTP request.
            exc: The RequestValidationError that was raised.

        Returns:
            HTMLResponse with the rendered error template.
        """
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

    return app
