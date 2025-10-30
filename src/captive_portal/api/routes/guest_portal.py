# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Guest portal routes for authorization and welcome pages."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from captive_portal.security.rate_limiter import RateLimiter
from captive_portal.services.redirect_validator import RedirectValidator
from captive_portal.services.unified_code_service import UnifiedCodeService

router = APIRouter(prefix="/guest", tags=["guest"])
templates = Jinja2Templates(directory="src/captive_portal/web/templates")


@router.get("/authorize", response_class=HTMLResponse)
async def show_authorize_form(
    request: Request,
    continue_url: Annotated[Optional[str], Query(alias="continue")] = None,
) -> HTMLResponse:
    """Display guest authorization form.

    Args:
        request: FastAPI request object
        continue_url: Optional redirect destination after successful authorization

    Returns:
        HTMLResponse: Rendered authorization form
    """
    return templates.TemplateResponse(
        request=request,
        name="guest/authorize.html",
        context={
            "continue_url": continue_url or "/guest/welcome",
        },
    )


@router.post("/authorize")
async def handle_authorization(
    request: Request,
    code: Annotated[str, Form()],
    continue_url: Annotated[Optional[str], Form(alias="continue")] = None,
    rate_limiter: RateLimiter = Depends(),
    unified_code_service: UnifiedCodeService = Depends(),
    redirect_validator: RedirectValidator = Depends(),
) -> RedirectResponse:
    """Process guest authorization code submission.

    Args:
        request: FastAPI request object
        code: Authorization code (voucher or booking code)
        continue_url: Optional redirect destination
        rate_limiter: Rate limiting service
        unified_code_service: Code validation and grant creation service
        redirect_validator: Redirect URL validation service

    Returns:
        RedirectResponse: Redirect to success page or original destination

    Raises:
        HTTPException: 429 if rate limit exceeded, 400/404/409/410 for validation errors
    """
    client_ip = request.client.host if request.client else "unknown"

    # Check rate limit
    if not rate_limiter.is_allowed(client_ip):
        retry_after = rate_limiter.get_retry_after_seconds(client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authorization attempts. Please try again later.",
            headers={"Retry-After": str(retry_after or 60)},
        )

    # Validate code format
    try:
        validation_result = await unified_code_service.validate_code(code)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    # TODO: Process validated code and create access grant
    # For now, just validate the code type
    _ = validation_result  # Used for future grant creation

    # Validate and determine redirect destination
    if continue_url and redirect_validator.is_safe(continue_url):
        redirect_url = continue_url
    else:
        redirect_url = "/guest/welcome"

    # Success - redirect
    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    # TODO: Set authorization cookie/header for controller integration
    return response


@router.get("/welcome", response_class=HTMLResponse)
async def show_welcome(request: Request) -> HTMLResponse:
    """Display post-authorization welcome page.

    Args:
        request: FastAPI request object

    Returns:
        HTMLResponse: Rendered welcome page
    """
    return templates.TemplateResponse(
        request=request,
        name="guest/welcome.html",
    )


@router.get("/error", response_class=HTMLResponse)
async def show_error(
    request: Request,
    message: Annotated[Optional[str], Query()] = None,
) -> HTMLResponse:
    """Display guest error page.

    Args:
        request: FastAPI request object
        message: Optional error message to display

    Returns:
        HTMLResponse: Rendered error page
    """
    return templates.TemplateResponse(
        request=request,
        name="guest/error.html",
        context={
            "error_message": message or "An error occurred. Please try again.",
        },
    )
