# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""App factory with AppSettings integration and lifespan management."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable

from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from captive_portal.config.settings import AppSettings
from captive_portal.integrations.ha_client import HAClient
from captive_portal.integrations.ha_poller import HAPoller
from captive_portal.integrations.rental_control_service import RentalControlService
from captive_portal.persistence.database import (
    create_db_engine,
    dispose_engine,
    init_db,
)
from captive_portal.persistence.repositories import RentalControlEventRepository
from captive_portal.security.session_middleware import (
    SessionMiddleware,
)
from captive_portal.web.middleware.security_headers import SecurityHeadersMiddleware

logger = logging.getLogger("captive_portal")

# Package-relative paths for static assets
_THEMES_DIR = Path(__file__).resolve().parent / "web" / "themes"


async def _run_config_migration(settings: AppSettings, engine: Any) -> None:
    """Run YAML→DB migration (non-fatal).

    Args:
        settings: Application settings.
        engine: SQLAlchemy engine.
    """
    from captive_portal.services.config_migration import migrate_yaml_to_db

    migration_session = Session(engine)
    try:
        result = await migrate_yaml_to_db(settings, migration_session)
        if result.omada_migrated:
            logger.info("Config migration: Omada settings migrated from YAML to DB.")
        if result.session_fields_migrated > 0:
            logger.info(
                "Config migration: %d session fields migrated.",
                result.session_fields_migrated,
            )
        if result.guest_url_migrated:
            logger.info("Config migration: guest_external_url migrated.")
    except Exception as exc:
        logger.warning("Config migration skipped (non-fatal): %s", exc)
    finally:
        migration_session.close()


async def _load_omada_config(settings: AppSettings, engine: Any) -> dict[str, Any] | None:
    """Load Omada config from DB, falling back to AppSettings.

    Args:
        settings: Application settings.
        engine: SQLAlchemy engine.

    Returns:
        Omada config dict or None.
    """
    from captive_portal.config.omada_config import build_omada_config
    from captive_portal.models.omada_config import OmadaConfig

    try:
        omada_session = Session(engine)
        try:
            from sqlmodel import select as _select

            _stmt: Any = _select(OmadaConfig).where(OmadaConfig.id == 1)
            db_omada: OmadaConfig | None = omada_session.exec(_stmt).first()
            if db_omada and db_omada.omada_configured:
                return await build_omada_config(db_omada, logger)
            return await build_omada_config(settings, logger)
        finally:
            omada_session.close()
    except Exception:
        return await build_omada_config(settings, logger)


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

        # Run one-time YAML→DB migration
        await _run_config_migration(settings, engine)

        # Create HA client for API communication
        ha_client = HAClient(settings.ha_base_url, settings.ha_token)
        app.state.ha_client = ha_client
        logger.info("HAClient initialized for %s", settings.ha_base_url)

        # Configure Omada controller integration (prefer DB config)
        app.state.omada_config = await _load_omada_config(settings, engine)

        if app.state.omada_config:
            logger.info("Omada controller configured.")
        else:
            logger.info("Omada controller not configured — controller calls will be skipped")

        # Start background poller for Rental Control event sync
        poller_session = Session(engine)
        event_repo = RentalControlEventRepository(poller_session)
        rental_service = RentalControlService(
            ha_client=ha_client,
            event_repo=event_repo,
        )
        ha_poller = HAPoller(
            ha_client=ha_client,
            rental_service=rental_service,
        )
        ha_poller_task = asyncio.create_task(ha_poller.start())
        app.state.ha_poller = ha_poller
        app.state.ha_poller_task = ha_poller_task
        app.state.poller_session = poller_session
        logger.info("HA poller started for Rental Control event sync")

        yield

        # --- Shutdown ---
        await app.state.ha_poller.stop()
        app.state.ha_poller_task.cancel()
        try:
            await app.state.ha_poller_task
        except asyncio.CancelledError:
            pass
        logger.info("HA poller stopped.")
        app.state.poller_session.close()
        await app.state.ha_client.close()
        logger.info("HAClient closed.")
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

    # Store debug toggle in app state for guest portal routes
    app.state.debug_guest_portal = settings.debug_guest_portal

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
        integrations,
        integrations_ui,
        omada_settings_ui,
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
    app.include_router(integrations.router)
    app.include_router(omada_settings_ui.router)
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
