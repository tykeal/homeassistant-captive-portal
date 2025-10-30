# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Guest portal routes for authorization and welcome pages."""

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from captive_portal.persistence.database import get_session
from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.persistence.repositories import AccessGrantRepository
from captive_portal.security.csrf import CSRFConfig, CSRFProtection
from captive_portal.security.rate_limiter import RateLimiter
from captive_portal.services.audit_service import AuditService
from captive_portal.services.booking_code_validator import (
    BookingCodeValidator,
    BookingNotFoundError,
    BookingOutsideWindowError,
    DuplicateGrantError,
    IntegrationUnavailableError,
)
from captive_portal.services.redirect_validator import RedirectValidator
from captive_portal.services.unified_code_service import CodeType, UnifiedCodeService
from captive_portal.services.voucher_service import VoucherRedemptionError, VoucherService
from captive_portal.utils.network_utils import get_client_ip, validate_mac_address
from captive_portal.utils.time_utils import ceil_to_minute, floor_to_minute

router = APIRouter(prefix="/guest", tags=["guest"])
templates = Jinja2Templates(directory="src/captive_portal/web/templates")
templates.env.autoescape = True  # Explicitly enable auto-escaping for XSS protection

# Guest-specific CSRF configuration (lighter-weight since no session state)
_guest_csrf_config = CSRFConfig(
    cookie_name="guest_csrftoken",
    form_field_name="csrf_token",
    cookie_secure=False,  # Allow HTTP for captive portal use
    cookie_samesite="lax",  # Lax mode for redirect scenarios
)
_guest_csrf = CSRFProtection(_guest_csrf_config)


def get_audit_service(session: Session = Depends(get_session)) -> AuditService:
    """Dependency for creating AuditService.

    Args:
        session: Database session

    Returns:
        Configured AuditService instance
    """
    return AuditService(session)


def _add_security_headers(response: HTMLResponse) -> HTMLResponse:
    """Add security headers to guest responses.

    Implements defense-in-depth security controls:
    - Content-Security-Policy: Prevents XSS and injection attacks
    - X-Frame-Options: Prevents clickjacking
    - X-Content-Type-Options: Prevents MIME-sniffing
    - Referrer-Policy: Limits referrer information leakage

    Args:
        response: HTMLResponse to add headers to

    Returns:
        Same response with security headers added
    """
    # CSP allows inline styles (needed for our templates) but blocks inline scripts
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


def _sanitize_error_message(message: str | None) -> str:
    """Sanitize error message for safe display.

    Removes or escapes potentially dangerous characters while preserving
    readability. This provides defense-in-depth alongside Jinja2 auto-escaping.

    Args:
        message: Raw error message (may be user-controlled via query params)

    Returns:
        Sanitized message safe for template rendering
    """
    if not message:
        return "An error occurred. Please try again."

    # Limit length to prevent UI breaking
    if len(message) > 500:
        message = message[:500] + "..."

    # Strip any HTML tags (basic sanitization)
    # Jinja2 auto-escape will handle the rest
    import re

    message = re.sub(r"<[^>]*>", "", message)

    # If message becomes empty after sanitization, use default
    return message.strip() or "An error occurred. Please try again."


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
        HTMLResponse: Rendered authorization form with CSRF token
    """
    # Generate CSRF token
    csrf_token = _guest_csrf.generate_token()

    response = templates.TemplateResponse(
        request=request,
        name="guest/authorize.html",
        context={
            "continue_url": continue_url or "/guest/welcome",
            "csrf_token": csrf_token,
        },
    )

    # Set CSRF token in cookie
    _guest_csrf.set_csrf_cookie(response, csrf_token)

    # Add security headers
    return _add_security_headers(response)


def _extract_mac_address(request: Request) -> str:
    """Extract and validate MAC address from request.

    Checks common MAC address headers set by captive portal controllers,
    validates the format, and normalizes to uppercase colon-separated format.

    Args:
        request: FastAPI request object

    Returns:
        Validated and normalized MAC address (format: AA:BB:CC:DD:EE:FF)

    Raises:
        HTTPException: If MAC address cannot be determined or is invalid
    """
    mac = request.headers.get("X-MAC-Address")
    if not mac:
        # Fallback: check alternate header names used by various controllers
        mac = request.headers.get("X-Client-Mac") or request.headers.get("Client-MAC")

    if not mac:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to determine device MAC address. Please ensure you're connecting through the captive portal.",
        )

    # Validate and normalize MAC address format
    try:
        return validate_mac_address(mac)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid MAC address format: {e}",
        ) from e


@router.post("/authorize")
async def handle_authorization(
    request: Request,
    code: Annotated[str, Form()],
    continue_url: Annotated[Optional[str], Form(alias="continue")] = None,
    rate_limiter: RateLimiter = Depends(),
    unified_code_service: UnifiedCodeService = Depends(),
    redirect_validator: RedirectValidator = Depends(),
    session: Session = Depends(get_session),
    audit_service: AuditService = Depends(get_audit_service),
) -> RedirectResponse:
    """Process guest authorization code submission.

    Validates the authorization code, creates an access grant, and authorizes the
    client device on the network controller.

    Args:
        request: FastAPI request object
        code: Authorization code (voucher or booking code)
        continue_url: Optional redirect destination
        rate_limiter: Rate limiting service
        unified_code_service: Code validation and grant creation service
        redirect_validator: Redirect URL validation service
        session: Database session

    Returns:
        RedirectResponse: Redirect to success page or original destination

    Raises:
        HTTPException: 403 for CSRF validation, 429 if rate limit exceeded, 400/404/409/410 for validation errors
    """
    # Validate CSRF token
    await _guest_csrf.validate_token(request)

    # TODO: Make proxy trust configurable via settings
    # For now, trust proxies from private networks (10.x, 172.16-31.x, 192.168.x)
    trusted_networks = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
    client_ip = get_client_ip(request, trust_proxies=True, trusted_networks=trusted_networks)

    # Check rate limit
    if not rate_limiter.is_allowed(client_ip):
        retry_after = rate_limiter.get_retry_after_seconds(client_ip)

        # Log rate limit violation
        await audit_service.log(
            actor=f"guest@{client_ip}",
            action="guest.authorize",
            outcome="rate_limited",
            meta={
                "client_ip": client_ip,
                "user_agent": request.headers.get("User-Agent", "unknown"),
                "retry_after": retry_after,
            },
        )

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authorization attempts. Please try again later.",
            headers={"Retry-After": str(retry_after or 60)},
        )

    # Extract device MAC address
    try:
        mac_address = _extract_mac_address(request)
    except HTTPException as e:
        # Log MAC extraction failure
        await audit_service.log(
            actor=f"guest@{client_ip}",
            action="guest.authorize",
            outcome="error",
            meta={
                "client_ip": client_ip,
                "user_agent": request.headers.get("User-Agent", "unknown"),
                "error": "mac_extraction_failed",
                "detail": str(e.detail),
            },
        )
        raise

    # Validate code format and determine type
    try:
        validation_result = await unified_code_service.validate_code(code)
    except ValueError as e:
        # Log code validation failure
        await audit_service.log(
            actor=f"guest@{client_ip}",
            action="guest.authorize",
            outcome="denied",
            meta={
                "client_ip": client_ip,
                "mac": mac_address,
                "user_agent": request.headers.get("User-Agent", "unknown"),
                "error": "invalid_code_format",
                "detail": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    # Process code and create access grant based on type
    grant: AccessGrant
    try:
        if validation_result.code_type == CodeType.VOUCHER:
            # Redeem voucher
            voucher_service = VoucherService(session)
            grant = await voucher_service.redeem(
                code=validation_result.normalized_code,
                mac=mac_address,
            )
        elif validation_result.code_type == CodeType.BOOKING:
            # Validate booking code and create grant
            booking_validator = BookingCodeValidator(session)

            # Get integration config
            stmt: Any = select(HAIntegrationConfig).limit(1)
            integration: HAIntegrationConfig | None = session.exec(stmt).first()
            if not integration:
                raise IntegrationUnavailableError("No rental control integration configured")

            # Find matching event
            event = booking_validator.validate_code(validation_result.normalized_code, integration)
            if not event:
                raise BookingNotFoundError("Booking not found")

            # Check time window with grace period
            now = datetime.now(timezone.utc)
            grace_minutes = integration.checkout_grace_minutes

            # Ensure event times are timezone-aware
            start_utc = (
                event.start_utc
                if event.start_utc.tzinfo
                else event.start_utc.replace(tzinfo=timezone.utc)
            )
            end_utc = (
                event.end_utc
                if event.end_utc.tzinfo
                else event.end_utc.replace(tzinfo=timezone.utc)
            )

            # Allow early check-in up to 60 minutes before start
            early_checkin_window = start_utc - timedelta(minutes=60)
            if now < early_checkin_window:
                raise BookingOutsideWindowError(
                    f"Your booking begins on {start_utc.strftime('%Y-%m-%d at %H:%M')} UTC. Early check-in is available 60 minutes before this time."
                )

            # Check if after end + grace
            effective_end = end_utc + timedelta(minutes=grace_minutes)
            if now > effective_end:
                raise BookingOutsideWindowError(
                    f"Your booking ended on {end_utc.strftime('%Y-%m-%d at %H:%M')} UTC."
                )

            # Check for duplicate active grant for this booking
            grant_repo = AccessGrantRepository(session)
            existing_grants = grant_repo.find_active_by_mac(mac_address)
            for existing in existing_grants:
                if (
                    existing.booking_ref
                    and existing.booking_ref.lower() == validation_result.normalized_code.lower()
                ):
                    raise DuplicateGrantError(
                        "You already have an active access grant for this booking."
                    )

            # Create access grant with booking details
            grant_start = floor_to_minute(max(now, start_utc))
            grant_end = ceil_to_minute(effective_end)

            # Store original booking identifier with case preserved
            booking_identifier = getattr(event, integration.identifier_attr.value)

            grant = AccessGrant(
                mac=mac_address,
                device_id=mac_address,  # Use MAC as device_id for now
                booking_ref=booking_identifier,  # Store case-sensitive booking identifier
                user_input_code=validation_result.original_code,  # Store user's original input
                integration_id=integration.integration_id,  # Store which integration was used
                start_utc=grant_start,
                end_utc=grant_end,
                status=GrantStatus.PENDING,
            )

            grant_repo.add(grant)
            session.commit()
            session.refresh(grant)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid code type",
            )

    except VoucherRedemptionError as e:
        # Log voucher redemption failure
        await audit_service.log(
            actor=f"guest@{client_ip}",
            action="guest.authorize",
            outcome="denied",
            target_type="voucher",
            target_id=validation_result.normalized_code,
            meta={
                "client_ip": client_ip,
                "mac": mac_address,
                "user_agent": request.headers.get("User-Agent", "unknown"),
                "error": "voucher_redemption_failed",
                "detail": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(e),
        ) from e
    except BookingNotFoundError as e:
        # Log booking not found
        await audit_service.log(
            actor=f"guest@{client_ip}",
            action="guest.authorize",
            outcome="denied",
            target_type="booking",
            target_id=validation_result.normalized_code,
            meta={
                "client_ip": client_ip,
                "mac": mac_address,
                "user_agent": request.headers.get("User-Agent", "unknown"),
                "error": "booking_not_found",
                "detail": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except BookingOutsideWindowError as e:
        # Log booking outside time window
        await audit_service.log(
            actor=f"guest@{client_ip}",
            action="guest.authorize",
            outcome="denied",
            target_type="booking",
            target_id=validation_result.normalized_code,
            meta={
                "client_ip": client_ip,
                "mac": mac_address,
                "user_agent": request.headers.get("User-Agent", "unknown"),
                "error": "booking_outside_window",
                "detail": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e
    except DuplicateGrantError as e:
        # Log duplicate grant attempt
        await audit_service.log(
            actor=f"guest@{client_ip}",
            action="guest.authorize",
            outcome="denied",
            target_type="booking",
            target_id=validation_result.normalized_code,
            meta={
                "client_ip": client_ip,
                "mac": mac_address,
                "user_agent": request.headers.get("User-Agent", "unknown"),
                "error": "duplicate_grant",
                "detail": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e
    except IntegrationUnavailableError as e:
        # Log integration unavailable
        await audit_service.log(
            actor=f"guest@{client_ip}",
            action="guest.authorize",
            outcome="error",
            meta={
                "client_ip": client_ip,
                "mac": mac_address,
                "user_agent": request.headers.get("User-Agent", "unknown"),
                "error": "integration_unavailable",
                "detail": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e

    # Clear rate limit on successful authorization
    rate_limiter.clear(client_ip)

    # Log successful authorization
    await audit_service.log(
        actor=f"guest@{client_ip}",
        action="guest.authorize",
        outcome="success",
        target_type="voucher" if validation_result.code_type == CodeType.VOUCHER else "booking",
        target_id=str(grant.id),
        meta={
            "client_ip": client_ip,
            "mac": mac_address,
            "user_agent": request.headers.get("User-Agent", "unknown"),
            "code_type": validation_result.code_type.value,
            "grant_start": grant.start_utc.isoformat(),
            "grant_end": grant.end_utc.isoformat(),
        },
    )

    # Validate and determine redirect destination
    if continue_url and redirect_validator.is_safe(continue_url):
        redirect_url = continue_url
    else:
        redirect_url = "/guest/welcome"

    # Success - redirect with grant ID in session/cookie for controller integration
    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="grant_id",
        value=str(grant.id),
        httponly=True,
        samesite="strict",
        max_age=3600,  # 1 hour cookie lifetime
    )
    return response


@router.get("/welcome", response_class=HTMLResponse)
async def show_welcome(request: Request) -> HTMLResponse:
    """Display post-authorization welcome page.

    Args:
        request: FastAPI request object

    Returns:
        HTMLResponse: Rendered welcome page with security headers
    """
    response = templates.TemplateResponse(
        request=request,
        name="guest/welcome.html",
    )
    return _add_security_headers(response)


@router.get("/error", response_class=HTMLResponse)
async def show_error(
    request: Request,
    message: Annotated[Optional[str], Query()] = None,
) -> HTMLResponse:
    """Display guest error page.

    Args:
        request: FastAPI request object
        message: Optional error message to display (sanitized for security)

    Returns:
        HTMLResponse: Rendered error page with security headers
    """
    # Sanitize user-controlled error message to prevent XSS
    sanitized_message = _sanitize_error_message(message)

    response = templates.TemplateResponse(
        request=request,
        name="guest/error.html",
        context={
            "error_message": sanitized_message,
        },
    )
    return _add_security_headers(response)
