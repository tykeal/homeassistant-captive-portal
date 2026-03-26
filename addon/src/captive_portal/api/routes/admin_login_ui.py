# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Admin login page route.

Serves the login HTML form at ``/admin/login``.  This endpoint does
**not** require authentication so that first-time users arriving via
Home Assistant ingress are presented with a login form instead of a
JSON 401 error.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/admin", tags=["admin-ui-login"])
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@router.get("/login", response_class=HTMLResponse, response_model=None)
async def admin_login_page(request: Request) -> HTMLResponse | RedirectResponse:
    """Serve the admin login form.

    If the user already has a valid session the handler redirects to
    the portal-settings page instead of showing the login form again.

    Args:
        request: Incoming HTTP request.

    Returns:
        Login HTML page, or 303 redirect when already authenticated.
    """
    admin_id = getattr(request.state, "admin_id", None)
    if admin_id:
        root = request.scope.get("root_path", "")
        return RedirectResponse(
            url=f"{root}/admin/portal-settings/",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return templates.TemplateResponse(
        request=request,
        name="admin/login.html",
    )
