# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""App factory and minimal health endpoint (Phase 0 placeholder)."""

import logging
from typing import Any, Callable

from fastapi import Depends, FastAPI, Request

from captive_portal.security.session_middleware import (
    SessionConfig,
    SessionMiddleware,
)
from captive_portal.web.middleware.security_headers import SecurityHeadersMiddleware

logger = logging.getLogger("captive_portal")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application with health and placeholder endpoints
    """
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
    )

    # Initialize shared session store and config
    from captive_portal.security.session_middleware import SessionStore

    session_config = SessionConfig()
    session_store = SessionStore()
    # Store both in app state for access by routes
    app.state.session_config = session_config
    app.state.session_store = session_store

    # Add security headers middleware (outermost)
    app.add_middleware(SecurityHeadersMiddleware)

    # Add session middleware with shared store
    app.add_middleware(SessionMiddleware, config=session_config, store=session_store)

    # Register routes
    from captive_portal.api.routes import (
        admin_accounts,
        admin_auth,
        audit_config,
        captive_detect,
        docs,
        grants,
        guest_portal,
        health,
        integrations_ui,
        portal_config,
        portal_settings_ui,
        vouchers,
    )
    from captive_portal import middleware

    app.include_router(admin_accounts.router)
    app.include_router(admin_auth.router)
    app.include_router(audit_config.router)
    app.include_router(captive_detect.router)
    app.include_router(docs.router)
    app.include_router(grants.router)
    app.include_router(guest_portal.router)
    app.include_router(health.router)
    app.include_router(portal_config.router)
    app.include_router(portal_settings_ui.router)
    app.include_router(vouchers.router)
    app.include_router(integrations_ui.router)

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


# convenience instance for uvicorn - optional usage
app = create_app()
