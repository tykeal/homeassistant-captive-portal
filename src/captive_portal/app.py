# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""App factory and minimal health endpoint (Phase 0 placeholder)."""
from fastapi import FastAPI
import logging

logger = logging.getLogger("captive_portal")


def create_app() -> FastAPI:
    app = FastAPI(title="Captive Portal Guest Access")

    @app.get("/health", tags=["internal"])  # basic health for addon
    async def health():  # pragma: no cover - trivial
        return {"status": "ok"}

    return app

# convenience instance for uvicorn - optional usage
app = create_app()
