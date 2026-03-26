# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""App factory with AppSettings integration and lifespan management."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable

from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from captive_portal.config.settings import AppSettings
from captive_portal.persistence.database import (
    create_db_engine,
    dispose_engine,
    init_db,
)
from captive_portal.security.session_middleware import (
    SessionMiddleware,
)
from captive_portal.web.middleware.security_headers import SecurityHeadersMiddleware

logger = logging.getLogger("captive_portal")

# Package-relative paths for static assets
_THEMES_DIR = Path(__file__).resolve().parent / "web" / "themes"


def _make_lifespan(
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
        """Manage application startup and shutdown.

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

        # Validate database path before initializing SQLite engine so that
        # configuration errors (e.g., missing /data directory) surface with
        # a clear message instead of an opaque database error.
        settings.validate_db_path()

        try:
            engine = create_db_engine(f"sqlite:///{settings.db_path}")
            init_db(engine)
            logger.info("Database initialized at %s", settings.db_path)
        except Exception:
            dispose_engine()
            raise

        yield

        # --- Shutdown ---
        dispose_engine()
        logger.info("Database connections closed.")

    return lifespan


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        settings: Optional application settings. When ``None``,
            ``AppSettings.load()`` is called to resolve configuration
            from addon options, environment variables, and defaults.

    Returns:
        Configured FastAPI application with all routes and middleware.
    """
    if settings is None:
        settings = AppSettings.load()

    app = FastAPI(
        title="Captive Portal Guest Access",
        description="""
        A captive portal system that integrates with Home Assistant Rental Control
        integrations to provide time-limited WiFi access for short-term rental guests.

        ## Features

        * **Guest Portal**: Self-service WiFi authorization using booking codes
        * **Voucher System**: Admin-generated vouchers for additional guests/devices
        * **Admin Interface**: Manage access grants, vouchers, and portal configuration
        * **Rental Control Integration**: Automatic booking synchronization from Home Assistant
        * **TP-Link Omada Controller**: Native integration for client authorization/revocation
        * **Audit Logging**: Complete audit trail of all access operations

        ## Authentication

        * **Admin endpoints** (`/admin/*`): Require session-based authentication
        * **Guest endpoints** (`/portal/*`): Rate-limited, CSRF-protected
        * **Health/Detection endpoints**: Unauthenticated public access
        """,
        version="0.1.0",
        contact={
            "name": "Andrew Grimberg",
            "email": "tykeal@bardicgrove.org",
        },
        license_info={
            "name": "Apache-2.0",
            "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
        },
        # Disable public docs - admin-only docs available at /admin/docs and /admin/redoc
        docs_url=None,
        redoc_url=None,
        lifespan=_make_lifespan(settings),
    )

    # Initialize shared session store and config from settings
    from captive_portal.security.session_middleware import SessionStore

    session_config = settings.to_session_config()
    session_store = SessionStore()
    # Store both in app state for access by routes
    app.state.session_config = session_config
    app.state.session_store = session_store

    # Add security headers middleware (outermost)
    app.add_middleware(SecurityHeadersMiddleware)

    # Add session middleware with shared store
    app.add_middleware(SessionMiddleware, config=session_config, store=session_store)

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

    # Register routes
    from captive_portal.api.routes import (
        admin_accounts,
        admin_auth,
        admin_login_ui,
        admin_logout_ui,
        audit_config,
        captive_detect,
        dashboard_ui,
        docs,
        grants,
        grants_ui,
        guest_portal,
        health,
        integrations_ui,
        portal_config,
        portal_settings_ui,
        vouchers,
        vouchers_ui,
    )
    from captive_portal import middleware

    app.include_router(admin_accounts.router)
    app.include_router(admin_auth.router)
    app.include_router(admin_login_ui.router)
    app.include_router(admin_logout_ui.router)
    app.include_router(audit_config.router)
    app.include_router(captive_detect.router)
    app.include_router(dashboard_ui.router)
    app.include_router(docs.router)
    app.include_router(grants.router)
    app.include_router(grants_ui.router)
    app.include_router(guest_portal.router)
    app.include_router(health.router)
    app.include_router(portal_config.router)
    app.include_router(portal_settings_ui.router)
    app.include_router(vouchers.router)
    app.include_router(vouchers_ui.router)
    app.include_router(integrations_ui.router)

    # HA ingress opens "/" — redirect to the admin login page so
    # unauthenticated users see a login form instead of a 401 error.
    @app.get("/")
    async def root_redirect(request: Request) -> RedirectResponse:
        """Redirect the root path to the admin login page.

        Home Assistant ingress opens the sidebar panel at ``/`` which has
        no handler.  This redirect sends the user to the admin login
        page, respecting the ingress ``root_path``.  Authenticated
        users are forwarded to portal-settings by the login route.

        Args:
            request: Incoming HTTP request.

        Returns:
            303 redirect to the admin login page.
        """
        root = request.scope.get("root_path", "")
        return RedirectResponse(
            url=f"{root}/admin/login",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Example protected listing endpoint placeholder (no real data yet)

    def enforce(action: str) -> Callable[..., Any]:
        """Create RBAC enforcement dependency.

        Args:
            action: Action to enforce (e.g., 'grants.list')

        Returns:
            Dependency callable
        """

        async def _dep(request: Request) -> None:
            """Enforce RBAC for request.

            Args:
                request: FastAPI request
            """
            await middleware.rbac_enforcer(request, action)

        return _dep

    @app.get("/grants", tags=["grants"])
    async def list_grants(
        _: None = Depends(enforce("grants.list")),  # noqa: B008
    ) -> dict[str, list[Any]]:
        """List access grants (placeholder).

        Returns:
            Dictionary with empty items list
        """
        return {"items": []}

    return app
