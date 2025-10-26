# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""App factory and minimal health endpoint (Phase 0 placeholder)."""

from typing import Any, Callable
from fastapi import FastAPI, Depends
from . import middleware
import logging

logger = logging.getLogger("captive_portal")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application with health and placeholder endpoints
    """
    app = FastAPI(title="Captive Portal Guest Access")

    @app.get("/health", tags=["internal"])  # basic health for addon
    async def health() -> dict[str, str]:  # pragma: no cover - trivial
        """Health check endpoint.

        Returns:
            Status dictionary
        """
        return {"status": "ok"}

    # Example protected listing endpoint placeholder (no real data yet)
    from fastapi import Request  # local import inside factory

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
