# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Admin UI route for HTML-based logout with browser redirect.

Invokes the existing JSON logout handler to destroy the session,
then issues a browser-friendly 303 redirect to the login page.
CSRF-exempt per FR-019.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, status
from fastapi.responses import RedirectResponse

logger = logging.getLogger("captive_portal")

router = APIRouter(prefix="/admin", tags=["admin-ui-logout"])


@router.post("/logout")
async def admin_logout(request: Request) -> RedirectResponse:
    """Terminate admin session and redirect to login page.

    This route is CSRF-exempt (FR-019). It destroys the current
    session (if any) and always redirects to the login page,
    treating both "session destroyed" and "no active session"
    as success.

    Args:
        request: Incoming HTTP request.

    Returns:
        303 redirect to the admin login page.
    """
    root = request.scope.get("root_path", "")
    session_id = getattr(request.state, "session_id", None)

    response = RedirectResponse(
        url=f"{root}/admin/login",
        status_code=status.HTTP_303_SEE_OTHER,
    )

    if session_id:
        # Destroy session from store
        session_store = request.app.state.session_store
        session_store.delete(session_id)
        logger.info("Admin session destroyed via HTML logout")

    # Clear session cookie regardless
    session_config = request.app.state.session_config
    response.delete_cookie(key=session_config.cookie_name)

    return response
