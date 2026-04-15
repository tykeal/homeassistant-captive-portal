# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Guest portal routes for authorization and welcome pages."""

import logging
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from captive_portal.controllers.tp_omada.adapter import OmadaAdapter
from captive_portal.controllers.tp_omada.base_client import (
    OmadaClientError,
    OmadaRetryExhaustedError,
)
from captive_portal.controllers.tp_omada.dependencies import get_omada_adapter
from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.models.portal_config import PortalConfig
from captive_portal.persistence.database import get_session
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
from captive_portal.services.vlan_validation_service import VlanValidationService
from captive_portal.services.voucher_service import (
    VoucherDeviceLimitError,
    VoucherRedemptionError,
    VoucherService,
)
from captive_portal.utils.network_utils import get_client_ip, validate_mac_address
from captive_portal.utils.time_utils import ceil_to_minute, floor_to_minute

_SITE_ID_PATTERN = re.compile(r"^[a-fA-F0-9]{12,64}$")

_logger = logging.getLogger("captive_portal.guest")


def _truncate(value: str | None, max_length: int) -> str | None:
    """Strip whitespace and truncate a value to ``max_length``.

    Returns ``None`` when the input is empty/whitespace-only.

    Args:
        value: Raw input string (may be None or empty).
        max_length: Maximum allowed length after stripping.

    Returns:
        Sanitized string or None.
    """
    if not value or not value.strip():
        return None
    return value.strip()[:max_length]


def _apply_site_override(
    site_from_form: str | None,
    current_site: str,
    pattern: re.Pattern[str],
) -> str:
    """Apply site override from form data if valid.

    Args:
        site_from_form: Site identifier from the submitted form.
        current_site: Current adapter site ID.
        pattern: Compiled regex for site ID validation.

    Returns:
        Overridden site if valid, otherwise the current site.
    """
    if site_from_form and site_from_form.strip() and pattern.match(site_from_form.strip()):
        return site_from_form.strip()
    return current_site


_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "templates"

router = APIRouter(prefix="/guest", tags=["guest"])
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
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


def get_portal_config_dep(session: Session = Depends(get_session)) -> PortalConfig:
    """Dependency for fetching portal configuration.

    Args:
        session: Database session

    Returns:
        PortalConfig singleton instance

    Raises:
        HTTPException: If portal configuration cannot be loaded or created
    """
    stmt: Any = select(PortalConfig).where(PortalConfig.id == 1)
    config: Optional[PortalConfig] = session.exec(stmt).first()

    if not config:
        # Atomic get-or-create to avoid race condition under concurrency
        try:
            config = PortalConfig(id=1)
            session.add(config)
            session.commit()
            session.refresh(config)
        except Exception:
            session.rollback()
            config = session.exec(stmt).first()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load portal configuration",
        )

    return config


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
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
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
    message = re.sub(r"<[^>]*>", "", message)

    # If message becomes empty after sanitization, use default
    return message.strip() or "An error occurred. Please try again."


async def _authorize_with_controller(
    adapter: OmadaAdapter | None,
    grant: AccessGrant,
    mac_address: str,
    gateway_mac: str | None = None,
    ap_mac: str | None = None,
    ssid_name: str | None = None,
    radio_id: str | None = None,
    vid: str | None = None,
) -> tuple[AccessGrant, Optional[str]]:
    """Authorize a grant with the Omada controller if configured.

    When the adapter is configured, enters the client async context and
    calls ``adapter.authorize()`` with the guest's MAC and grant expiry.
    On success, transitions the grant to ACTIVE and stores the controller
    grant ID.  On failure, transitions to FAILED.

    When no adapter is configured, transitions directly to ACTIVE
    (graceful degradation).

    Args:
        adapter: OmadaAdapter instance or None if not configured.
        grant: The access grant in PENDING status.
        mac_address: Device MAC address.
        gateway_mac: Gateway MAC for Gateway auth mode.
        ap_mac: Access point MAC for EAP auth mode.
        ssid_name: SSID name for EAP auth mode.
        radio_id: Radio identifier for EAP auth mode.
        vid: VLAN ID for Gateway auth mode.

    Returns:
        A tuple of (grant, error_detail) where error_detail is None
        on success or a diagnostic text string for audit/logging
        on failure.  This value must NOT be surfaced to end users.
    """
    if adapter is None:
        grant.status = GrantStatus.ACTIVE
        return grant, None

    error_detail: Optional[str] = None
    try:
        async with adapter.client:
            result = await adapter.authorize(
                mac=mac_address,
                expires_at=grant.end_utc,
                gateway_mac=gateway_mac,
                ap_mac=ap_mac,
                ssid_name=ssid_name,
                radio_id=radio_id,
                vid=vid,
            )
        grant.status = GrantStatus.ACTIVE
        grant.controller_grant_id = result.get("grant_id")
    except (OmadaClientError, OmadaRetryExhaustedError) as exc:
        _logger.error(
            "Controller authorization failed for MAC %s: %s",
            mac_address,
            exc,
        )
        grant.status = GrantStatus.FAILED
        error_detail = f"{type(exc).__name__}: {exc}"

    return grant, error_detail


@router.get("/authorize", response_class=HTMLResponse)
async def show_authorize_form(
    request: Request,
    client_mac: Annotated[Optional[str], Query(alias="clientMac")] = None,
    client_ip: Annotated[Optional[str], Query(alias="clientIp")] = None,
    site: Annotated[Optional[str], Query()] = None,
    ap_mac: Annotated[Optional[str], Query(alias="apMac")] = None,
    gateway_mac: Annotated[Optional[str], Query(alias="gatewayMac")] = None,
    radio_id: Annotated[Optional[str], Query(alias="radioId")] = None,
    ssid_name: Annotated[Optional[str], Query(alias="ssidName")] = None,
    vid: Annotated[Optional[str], Query()] = None,
    t: Annotated[Optional[str], Query()] = None,
    redirect_url: Annotated[Optional[str], Query(alias="redirectUrl")] = None,
    continue_url: Annotated[Optional[str], Query(alias="continue")] = None,
) -> HTMLResponse:
    """Display guest authorization form.

    Captures Omada controller redirect query parameters and passes them
    through as hidden form fields so they survive the GET→POST transition.

    Args:
        request: FastAPI request object
        client_mac: Device MAC address (from Omada redirect)
        client_ip: Device IP address (from Omada redirect)
        site: Omada site identifier hash (from Omada redirect)
        ap_mac: Access point MAC (from Omada redirect)
        gateway_mac: Gateway MAC (from Omada redirect)
        radio_id: Radio identifier (from Omada redirect)
        ssid_name: SSID name (from Omada redirect)
        vid: VLAN ID (from Omada redirect)
        t: Timestamp (from Omada redirect)
        redirect_url: Original redirect URL (from Omada redirect)
        continue_url: Optional redirect destination after successful authorization

    Returns:
        HTMLResponse: Rendered authorization form with CSRF token
    """
    omada_params = {
        "client_mac": client_mac or "",
        "client_ip": client_ip or "",
        "site": site or "",
        "ap_mac": ap_mac or "",
        "gateway_mac": gateway_mac or "",
        "radio_id": radio_id or "",
        "ssid_name": ssid_name or "",
        "vid": vid or "",
        "t": t or "",
        "redirect_url": redirect_url or "",
    }

    # DEBUG: configurable logging for hardware testing
    if getattr(request.app.state, "debug_guest_portal", False):
        _logger.debug(
            "GET /authorize query_params=%s omada_params=%s",
            dict(request.query_params),
            omada_params,
        )

    # Use redirectUrl as continue_url if no explicit continue was provided
    effective_continue = (
        continue_url or redirect_url or f"{request.scope.get('root_path', '')}/guest/welcome"
    )

    # Generate CSRF token
    csrf_token = _guest_csrf.generate_token()

    response = templates.TemplateResponse(
        request=request,
        name="guest/authorize.html",
        context={
            "continue_url": effective_continue,
            "csrf_token": csrf_token,
            "omada_params": omada_params,
        },
    )

    # Set CSRF token in cookie
    _guest_csrf.set_csrf_cookie(response, csrf_token)

    # Add security headers
    return _add_security_headers(response)


def _extract_mac_address(
    request: Request,
    form_mac: Optional[str] = None,
) -> str:
    """Extract and validate MAC address from request.

    Checks HTTP headers, form data, and query parameters for MAC address.
    Supports both header-based injection (reverse proxies) and Omada
    controller query parameter style (clientMac).

    Args:
        request: FastAPI request object
        form_mac: MAC address from form data (client_mac hidden field)

    Returns:
        Validated and normalized MAC address (format: AA:BB:CC:DD:EE:FF)

    Raises:
        HTTPException: If MAC address cannot be determined or is invalid
    """
    # 1. Check headers (reverse proxy / controller injection)
    mac = request.headers.get("X-MAC-Address")
    if not mac:
        mac = request.headers.get("X-Client-Mac") or request.headers.get("Client-MAC")

    # 2. Check form data (from our hidden field)
    if not mac and form_mac and isinstance(form_mac, str) and form_mac.strip():
        mac = form_mac.strip()

    # 3. Check query parameters (direct GET redirect from controller)
    if not mac:
        mac = request.query_params.get("clientMac")

    if not mac:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to determine device MAC address. "
            "Please ensure you're connecting through the captive portal.",
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
async def handle_authorization(  # noqa: C901 - TODO: refactor to reduce complexity
    request: Request,
    code: Annotated[str, Form()],
    continue_url: Annotated[Optional[str], Form()] = None,
    client_mac: Annotated[Optional[str], Form()] = None,
    site: Annotated[Optional[str], Form()] = None,
    gateway_mac: Annotated[Optional[str], Form()] = None,
    ap_mac: Annotated[Optional[str], Form()] = None,
    vid: Annotated[Optional[str], Form()] = None,
    ssid_name: Annotated[Optional[str], Form()] = None,
    radio_id: Annotated[Optional[str], Form()] = None,
    rate_limiter: RateLimiter = Depends(),
    unified_code_service: UnifiedCodeService = Depends(),
    redirect_validator: RedirectValidator = Depends(),
    session: Session = Depends(get_session),
    audit_service: AuditService = Depends(get_audit_service),
    portal_config: PortalConfig = Depends(get_portal_config_dep),
    omada_adapter: OmadaAdapter | None = Depends(get_omada_adapter),
) -> RedirectResponse:
    """Process guest authorization code submission.

    Validates the authorization code, creates an access grant, and authorizes the
    client device on the network controller.

    Args:
        request: FastAPI request object
        code: Authorization code (voucher or booking code)
        continue_url: Optional redirect destination
        client_mac: Device MAC from Omada controller redirect
        site: Omada site identifier from controller redirect
        gateway_mac: Gateway MAC for Gateway auth mode
        ap_mac: Access point MAC for EAP auth mode
        vid: VLAN ID for Gateway auth mode
        ssid_name: SSID name for EAP auth mode
        radio_id: Radio identifier for EAP auth mode
        rate_limiter: Rate limiting service
        unified_code_service: Code validation and grant creation service
        redirect_validator: Redirect URL validation service
        session: Database session
        audit_service: Audit logging service
        portal_config: Portal configuration
        omada_adapter: Optional Omada controller adapter

    Returns:
        RedirectResponse: Redirect to success page or original destination

    Raises:
        HTTPException: 403 for CSRF validation, 429 if rate limit exceeded, 400/404/409/410 for validation errors
    """
    # DEBUG: configurable logging for hardware testing
    if getattr(request.app.state, "debug_guest_portal", False):
        _logger.debug(
            "POST /authorize client_mac=%r site=%r headers=%s",
            client_mac,
            site,
            {k: v for k, v in request.headers.items() if "mac" in k.lower()},
        )

    # Store retry URL query params so the error page can link back
    # with the original Omada parameters preserved.
    retry_params = {
        k: v
        for k, v in {
            "clientMac": client_mac,
            "site": site,
            "gatewayMac": gateway_mac,
            "apMac": ap_mac,
            "vid": vid,
            "ssidName": ssid_name,
            "radioId": radio_id,
            "continue": continue_url,
        }.items()
        if v
    }
    request.state.retry_query = urllib.parse.urlencode(retry_params) if retry_params else ""

    # Validate CSRF token
    await _guest_csrf.validate_token(request)

    # Get trusted proxy networks from configuration
    trusted_networks = portal_config.get_trusted_networks()
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
        mac_address = _extract_mac_address(request, form_mac=client_mac)
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
    vlan_service = VlanValidationService()
    vlan_meta: dict[str, Any] = {}
    try:
        if validation_result.code_type == CodeType.VOUCHER:
            # Look up voucher for VLAN check before redeeming
            voucher_service = VoucherService(session)
            voucher_for_vlan = voucher_service.voucher_repo.get_by_code(
                validation_result.normalized_code
            )
            if voucher_for_vlan:
                vlan_result = vlan_service.validate_voucher_vlan(vid, voucher_for_vlan)
                vlan_meta = {
                    "vlan_allowed": vlan_result.allowed,
                    "vlan_reason": vlan_result.reason,
                    "vlan_device_vid": vlan_result.device_vid,
                    "vlan_allowed_vlans": vlan_result.allowed_vlans,
                }
                if not vlan_result.allowed:
                    await audit_service.log(
                        actor=f"guest@{client_ip}",
                        action="guest.authorize",
                        outcome="denied",
                        target_type="voucher",
                        target_id=validation_result.normalized_code,
                        meta={
                            "client_ip": client_ip,
                            "mac": mac_address,
                            "error": "vlan_check_failed",
                            **vlan_meta,
                        },
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="This code is not valid for your network.",
                    )

            # Redeem voucher
            grant = await voucher_service.redeem(
                code=validation_result.normalized_code,
                mac=mac_address,
            )
        elif validation_result.code_type == CodeType.BOOKING:
            # Validate booking code and create grant
            booking_validator = BookingCodeValidator(session)

            # Check if any integrations exist
            all_integrations = list(session.exec(select(HAIntegrationConfig)).all())
            if not all_integrations:
                raise IntegrationUnavailableError("No rental control integration configured")

            # Search ALL integrations for matching code
            event, integration = booking_validator.find_across_integrations(
                validation_result.normalized_code
            )
            if not event or not integration:
                raise BookingNotFoundError("Booking not found")

            # VLAN validation against the MATCHED integration
            vlan_result = vlan_service.validate_booking_vlan(vid, integration)
            vlan_meta = {
                "vlan_allowed": vlan_result.allowed,
                "vlan_reason": vlan_result.reason,
                "vlan_device_vid": vlan_result.device_vid,
                "vlan_allowed_vlans": vlan_result.allowed_vlans,
            }
            if not vlan_result.allowed:
                await audit_service.log(
                    actor=f"guest@{client_ip}",
                    action="guest.authorize",
                    outcome="denied",
                    target_type="booking",
                    target_id=validation_result.normalized_code,
                    meta={
                        "client_ip": client_ip,
                        "mac": mac_address,
                        "error": "vlan_check_failed",
                        **vlan_meta,
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This code is not valid for your network.",
                )

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

    except VoucherDeviceLimitError:
        # Log device limit reached
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
                "error": "voucher_device_limit",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This code has reached its maximum number of devices.",
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

    # --- Controller authorization ---
    # Store Omada connection params for future revocation (sanitized)
    grant.omada_gateway_mac = _truncate(gateway_mac, 17)
    grant.omada_ap_mac = _truncate(ap_mac, 17)
    grant.omada_vid = _truncate(vid, 8)
    grant.omada_ssid_name = _truncate(ssid_name, 64)
    grant.omada_radio_id = _truncate(radio_id, 2)

    # Override adapter site_id if Omada controller sent a site identifier
    if omada_adapter is not None:
        omada_adapter.site_id = _apply_site_override(site, omada_adapter.site_id, _SITE_ID_PATTERN)

    grant, error_detail = await _authorize_with_controller(
        adapter=omada_adapter,
        grant=grant,
        mac_address=mac_address,
        gateway_mac=grant.omada_gateway_mac,
        ap_mac=grant.omada_ap_mac,
        ssid_name=grant.omada_ssid_name,
        radio_id=grant.omada_radio_id,
        vid=grant.omada_vid,
    )
    session.add(grant)
    session.commit()
    session.refresh(grant)

    if grant.status == GrantStatus.FAILED:
        # Log controller failure
        await audit_service.log(
            actor=f"guest@{client_ip}",
            action="guest.authorize",
            outcome="error",
            target_type="access_grant",
            target_id=str(grant.id),
            meta={
                "client_ip": client_ip,
                "mac": mac_address,
                "user_agent": request.headers.get("User-Agent", "unknown"),
                "error": "controller_authorization_failed",
                "detail": error_detail,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="WiFi authorization could not be completed. Please try again or contact the host.",
        )

    # Clear rate limit on successful authorization
    rate_limiter.clear(client_ip)

    # Log successful authorization
    success_meta: dict[str, Any] = {
        "client_ip": client_ip,
        "mac": mac_address,
        "user_agent": request.headers.get("User-Agent", "unknown"),
        "code_type": validation_result.code_type.value,
        "grant_start": grant.start_utc.isoformat(),
        "grant_end": grant.end_utc.isoformat(),
    }
    if vlan_meta:
        success_meta.update(vlan_meta)
    await audit_service.log(
        actor=f"guest@{client_ip}",
        action="guest.authorize",
        outcome="success",
        target_type="voucher" if validation_result.code_type == CodeType.VOUCHER else "booking",
        target_id=str(grant.id),
        meta=success_meta,
    )

    # Validate and determine redirect destination
    if continue_url and redirect_validator.is_safe(continue_url):
        redirect_url = continue_url
    else:
        redirect_url = f"{request.scope.get('root_path', '')}/guest/welcome"

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

    rp = request.scope.get("root_path", "")
    retry_url = f"{rp}/guest/authorize"

    response = templates.TemplateResponse(
        request=request,
        name="guest/error.html",
        context={
            "error_message": sanitized_message,
            "retry_url": retry_url,
        },
    )
    return _add_security_headers(response)
