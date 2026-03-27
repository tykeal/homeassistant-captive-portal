# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Admin UI route for HTML-based logout with browser redirect.

Destroys the current admin session (if any) directly via the session
store, clears the session cookie, and issues a browser-friendly 303
redirect to the login page. CSRF-exempt per FR-019.
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

    # Access session store and config once
    session_store = request.app.state.session_store
    session_config = request.app.state.session_config

    if session_id:
        session_store.delete(session_id)
        logger.info("Admin session destroyed via HTML logout")
    else:
        # Fallback: delete by raw cookie value if present
        cookie_session_id = request.cookies.get(session_config.cookie_name)
        if cookie_session_id:
            session_store.delete(cookie_session_id)
            logger.info("Admin session destroyed via HTML logout (cookie fallback)")

    # Clear session cookie regardless
    response.delete_cookie(key=session_config.cookie_name)

    return response
