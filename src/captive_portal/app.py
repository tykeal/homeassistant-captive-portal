# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""App factory and minimal health endpoint (Phase 0 placeholder)."""
from fastapi import FastAPI, Depends
from . import security  # type: ignore
from . import middleware  # type: ignore
import logging

logger = logging.getLogger("captive_portal")


def create_app() -> FastAPI:
    app = FastAPI(title="Captive Portal Guest Access")

    @app.get("/health", tags=["internal"])  # basic health for addon
    async def health():  # pragma: no cover - trivial
        return {"status": "ok"}

    # Example protected listing endpoint placeholder (no real data yet)
    from fastapi import Request  # local import inside factory
    def enforce(action: str):
        async def _dep(request: Request):  # type: ignore
            await middleware.rbac_enforcer(request, action)
        return _dep

    @app.get("/grants", tags=["grants"])
    async def list_grants(_=Depends(enforce("grants.list"))):  # noqa: B008
        return {"items": []}

    return app

# convenience instance for uvicorn - optional usage
app = create_app()
