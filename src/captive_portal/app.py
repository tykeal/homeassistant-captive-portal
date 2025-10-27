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

logger = logging.getLogger("captive_portal")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application with health and placeholder endpoints
    """
    app = FastAPI(title="Captive Portal Guest Access")

    # Initialize session middleware
    session_config = SessionConfig()
    session_middleware = SessionMiddleware(app, config=session_config)
    app.add_middleware(SessionMiddleware, config=session_config)
    app.state.session_middleware = session_middleware

    # Register routes
    from captive_portal.api.routes import admin_auth, grants, health, vouchers
    from captive_portal import middleware

    app.include_router(admin_auth.router)
    app.include_router(grants.router)
    app.include_router(health.router)
    app.include_router(vouchers.router)

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
