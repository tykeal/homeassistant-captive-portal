# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Admin UI route for the dashboard overview page.

Displays aggregated statistics and recent activity feed for
administrators.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from captive_portal.persistence.database import get_session
from captive_portal.security.csrf import CSRFProtection, get_csrf_protection
from captive_portal.security.session_middleware import require_admin
from captive_portal.services.dashboard_service import (
    ActivityLogEntry,
    DashboardService,
    DashboardStats,
)

logger = logging.getLogger("captive_portal")

router = APIRouter(prefix="/admin", tags=["admin-ui-dashboard"])
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@router.get("/dashboard/", response_class=HTMLResponse)
async def get_dashboard(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_id: Annotated[UUID, Depends(require_admin)],
    csrf: Annotated[CSRFProtection, Depends(get_csrf_protection)],
) -> HTMLResponse:
    """Display the admin dashboard with statistics and recent activity.

    Args:
        request: Incoming HTTP request.
        session: Database session.
        admin_id: Authenticated admin user ID.
        csrf: CSRF protection instance.

    Returns:
        HTML response with dashboard template.
    """
    existing_token = csrf.get_token_from_request(request)
    need_csrf_cookie = existing_token is None
    csrf_token: str = existing_token if existing_token is not None else csrf.generate_token()

    service = DashboardService(session)

    try:
        stats = service.get_stats()
    except Exception:
        logger.exception("Failed to load dashboard statistics")
        stats = DashboardStats(
            active_grants=0,
            pending_grants=0,
            available_vouchers=0,
            integrations=0,
        )

    try:
        recent_logs: list[ActivityLogEntry] = service.get_recent_activity()
    except Exception:
        logger.exception("Failed to load recent activity")
        recent_logs = []

    response = templates.TemplateResponse(
        request=request,
        name="admin/dashboard.html",
        context={
            "stats": stats,
            "recent_logs": recent_logs,
            "csrf_token": csrf_token,
        },
    )
    if need_csrf_cookie:
        csrf.set_csrf_cookie(response, csrf_token)
    return response
