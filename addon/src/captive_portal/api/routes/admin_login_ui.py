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

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from captive_portal._version import __version__
from captive_portal.api.routes.admin_redirects import safe_admin_redirect

router = APIRouter(prefix="/admin", tags=["admin-ui-login"])
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.globals["app_version"] = __version__


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
        return safe_admin_redirect(root, "/admin/portal-settings/")

    return templates.TemplateResponse(
        request=request,
        name="admin/login.html",
    )
