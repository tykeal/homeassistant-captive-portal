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

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from captive_portal._version import __version__
from captive_portal.api.routes import booking_authorize
from captive_portal.config.settings import AppSettings
from captive_portal.guest_debug import DebugLoggingMiddleware as _DebugLoggingMiddleware
from captive_portal.persistence.database import (
    create_db_engine,
    dispose_engine,
    init_db,
)
from captive_portal.guest_routes import (
    configure_guest_middleware,
    mount_guest_static,
    register_guest_routes_and_handlers,
)

__all__ = ["_DebugLoggingMiddleware", "create_guest_app", "templates"]

logger = logging.getLogger("captive_portal.guest")

# Package-relative paths for static and template assets
_THEMES_DIR = Path(__file__).resolve().parent / "web" / "themes"
_TEMPLATES_DIR = Path(__file__).resolve().parent / "web" / "templates"

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.autoescape = True
templates.env.globals["app_version"] = __version__


async def _run_config_migration(settings: AppSettings, engine: Any) -> None:
    """Run YAML→DB migration (non-fatal).

    Args:
        settings: Application settings.
        engine: SQLAlchemy engine.
    """
    from captive_portal.services.config_migration import migrate_yaml_to_db

    from sqlmodel import Session

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
        logger.warning(
            "Config migration skipped (non-fatal): %s",
            exc,
            exc_info=True,
        )
    finally:
        migration_session.close()


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
        log_cfg = settings.to_log_config()
        if not logging.getLogger().handlers:
            logging.basicConfig(**log_cfg)

        settings.log_effective(logger)

        settings.validate_db_path()

        try:
            engine = create_db_engine(f"sqlite:///{settings.db_path}")
            init_db(engine)
            await _run_config_migration(settings, engine)
            booking_authorize.set_db_engine(engine)
            logger.info("Guest listener database initialized at %s", settings.db_path)
        except Exception:
            dispose_engine()
            raise

        # Configure Omada controller integration (from DB)
        from captive_portal.config.omada_config import build_omada_config
        from captive_portal.models.omada_config import OmadaConfig as _OmadaConfig

        from sqlmodel import Session as _Session, select as _select

        _omada_sess = _Session(engine)
        try:
            from typing import Any as _Any

            _stmt: _Any = _select(_OmadaConfig).where(_OmadaConfig.id == 1)
            _db_omada: _OmadaConfig | None = _omada_sess.exec(_stmt).first()
            if _db_omada and (_db_omada.omada_configured or _db_omada.openapi_configured):
                app.state.omada_config = await build_omada_config(_db_omada, logger)
            else:
                app.state.omada_config = None
        finally:
            _omada_sess.close()

        # Load guest_external_url from DB (PortalConfig)
        from captive_portal.models.portal_config import PortalConfig as _PortalConfig

        _portal_sess = _Session(engine)
        try:
            _pstmt: _Any = _select(_PortalConfig).where(_PortalConfig.id == 1)
            _portal: _PortalConfig | None = _portal_sess.exec(_pstmt).first()
            guest_url = _portal.guest_external_url if _portal else ""
            app.state.guest_external_url = guest_url
            if not guest_url:
                logger.warning(
                    "guest_external_url is not configured. "
                    "Captive portal detection redirects will use "
                    "relative paths. Configure guest_external_url "
                    "via the web UI for correct redirect URLs."
                )
        finally:
            _portal_sess.close()

        if app.state.omada_config:
            logger.info("Omada controller configured.")
        else:
            logger.info("Omada controller not configured — controller calls will be skipped")

        yield

        dispose_engine()
        logger.info("Guest listener database connections closed.")

    return lifespan


def create_guest_app(settings: AppSettings | None = None) -> FastAPI:
    """Create and configure the guest-only FastAPI application.

    This factory produces a FastAPI app that registers **only** guest,
    captive-detection, and health routers. Admin routes are never
    imported and are therefore unreachable on the guest listener.

    Args:
        settings: Optional application settings. When ``None``,
            ``AppSettings.load()`` is called to resolve configuration.

    Returns:
        Configured FastAPI application with guest routes only.
    """
    if settings is None:
        settings = AppSettings.load()

    app = FastAPI(
        title="Captive Portal Guest Access — Guest Listener",
        docs_url=None,
        redoc_url=None,
        lifespan=_make_guest_lifespan(settings),
    )

    app.state.guest_external_url = ""
    app.state.debug_guest_portal = settings.debug_guest_portal

    configure_guest_middleware(app, settings)
    mount_guest_static(app, _THEMES_DIR)
    register_guest_routes_and_handlers(app)

    return app
