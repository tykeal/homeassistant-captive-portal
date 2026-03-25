# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Health, readiness, and liveness API routes.

Container probe mapping:
  - livenessProbe:  GET /api/live   (process alive)
  - readinessProbe: GET /api/ready  (DB + dependencies ok)
  - startupProbe:   GET /api/health (general health)
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, text

from captive_portal.persistence.database import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["health"])


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    timestamp: datetime


class ReadinessResponse(BaseModel):
    """Readiness check response with component status."""

    status: str
    timestamp: datetime
    checks: dict[str, str]


class LivenessResponse(BaseModel):
    """Liveness check response."""

    status: str
    timestamp: datetime


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint.

    Returns:
        Health status and timestamp
    """
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/ready", response_model=ReadinessResponse)
async def readiness_check(
    response: Response,
    session: Session = Depends(get_session),
) -> ReadinessResponse:
    """Readiness probe – verifies DB connectivity.

    Kubernetes / container orchestrators should use this to decide
    whether to route traffic to the instance. Returns 503 when
    dependencies are unavailable.

    Returns:
        Readiness status with individual component checks
    """
    checks: dict[str, str] = {}
    overall = "ok"

    # Check database connectivity
    try:
        result = session.execute(text("SELECT 1"))
        result.close()
        checks["database"] = "ok"
    except SQLAlchemyError:
        logger.warning("Readiness check: database unavailable", exc_info=True)
        checks["database"] = "unavailable"
        overall = "degraded"

    if overall != "ok":
        response.status_code = 503

    return ReadinessResponse(
        status=overall,
        timestamp=datetime.now(timezone.utc),
        checks=checks,
    )


@router.get("/live", response_model=LivenessResponse)
async def liveness_check() -> LivenessResponse:
    """Liveness probe – confirms the process is alive.

    Kubernetes / container orchestrators should use this to decide
    whether to restart the container.

    Returns:
        Liveness status and timestamp
    """
    return LivenessResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc),
    )
