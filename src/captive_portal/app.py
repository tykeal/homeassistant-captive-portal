# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""App factory and minimal health endpoint (Phase 0 placeholder)."""
from fastapi import FastAPI, Depends
from .security import ROLE_ACTIONS  # type: ignore
from .middleware import rbac_enforcer  # type: ignore
import logging

logger = logging.getLogger("captive_portal")


def create_app() -> FastAPI:
    app = FastAPI(title="Captive Portal Guest Access")

    @app.get("/health", tags=["internal"])  # basic health for addon
    async def health():  # pragma: no cover - trivial
        return {"status": "ok"}

    # Example protected listing endpoint placeholder (no real data yet)
    @app.get("/grants", tags=["grants"])
    async def list_grants(_=Depends(lambda action="grants.list": rbac_enforcer)):  # noqa: B008
        return {"items": []}

    return app

# convenience instance for uvicorn - optional usage
app = create_app()
