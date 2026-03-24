# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Admin-only API documentation endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse

from captive_portal.security.session_middleware import require_admin

router = APIRouter(prefix="/admin", tags=["documentation"])


@router.get("/docs", response_class=HTMLResponse, include_in_schema=False)
async def swagger_ui(
    request: Request,
    admin_id: UUID = Depends(require_admin),
) -> HTMLResponse:
    """Serve Swagger UI for API documentation.

    Admin authentication required.

    Args:
        request: FastAPI request
        admin_id: Admin user ID from authentication

    Returns:
        Swagger UI HTML page
    """
    return get_swagger_ui_html(
        openapi_url=str(request.app.openapi_url),
        title=f"{request.app.title} - Swagger UI",
        swagger_favicon_url="",
    )


@router.get("/redoc", response_class=HTMLResponse, include_in_schema=False)
async def redoc(
    request: Request,
    admin_id: UUID = Depends(require_admin),
) -> HTMLResponse:
    """Serve ReDoc for API documentation.

    Admin authentication required.

    Args:
        request: FastAPI request
        admin_id: Admin user ID from authentication

    Returns:
        ReDoc HTML page
    """
    return get_redoc_html(
        openapi_url=str(request.app.openapi_url),
        title=f"{request.app.title} - ReDoc",
        redoc_favicon_url="",
    )
