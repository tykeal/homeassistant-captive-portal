# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Guest portal routes for authorization and welcome pages."""

import logging
import re
import urllib.parse
from collections.abc import Generator
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
from captive_portal.security.hmac_csrf import HMACCSRFProtection
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
from captive_portal._version import __version__
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
templates.env.globals["app_version"] = __version__

# Guest CSRF uses HMAC-signed tokens (no cookie required).
# iOS Captive Network Assistant does not persist cookies between
# GET and POST, so the double-submit cookie pattern fails there.
_guest_csrf = HMACCSRFProtection()


def get_audit_service(session: Session = Depends(get_session)) -> AuditService:
    """Dependency for creating AuditService.

    Args:
        session: Database session

    Returns:
        Configured AuditService instance
    """
    return AuditService(session)


def _get_optional_session(
    request: Request,
) -> Generator[Optional[Session], None, None]:
    """Yield a database session only for form submissions.

    Inspects query parameters to detect a form submission
    (both ``code`` and ``csrf_token`` present). For plain
    form-display requests the dependency yields ``None``,
    avoiding unnecessary database overhead.

    Args:
        request: Incoming HTTP request.

    Yields:
        Database session for submissions, ``None`` otherwise.
    """
    qp = request.query_params
    is_submission = bool(qp.get("code")) and bool(qp.get("csrf_token"))
    if not is_submission:
        yield None
        return

    try:
        session_factory = request.app.dependency_overrides.get(
            get_session,
            get_session,
        )
        gen = session_factory()
        session = next(gen)
        try:
            yield session
        finally:
            gen.close()
    except RuntimeError as exc:
        if "not initialized" in str(exc):
            yield None
        else:
            raise


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

    Note:
        On the guest listener, ``SecurityHeadersMiddleware`` overrides
        the CSP set here with ``guest_app._GUEST_CSP``.  This
        route-level CSP acts as a fallback for test clients that
        bypass middleware.

    Args:
        response: HTMLResponse to add headers to

    Returns:
        Same response with security headers added
    """
    # Route-level CSP (middleware may override in production)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'self'"
    )
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin"
    response.headers["Cache-Control"] = "no-store"
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


async def _handle_get_submission(
    *,
    request: Request,
    code: str,
    continue_url: str | None,
    client_mac: str | None,
    site: str | None,
    gateway_mac: str | None,
    ap_mac: str | None,
    vid: str | None,
    ssid_name: str | None,
    radio_id: str | None,
    session: Session,
) -> RedirectResponse:
    """Resolve remaining deps and delegate to ``_process_authorization``.

    Called by the GET handler when a form submission is detected
    (both ``code`` and ``csrf_token`` present).  The database
    session comes from ``_get_optional_session`` and remaining
    dependencies are resolved via ``app.dependency_overrides``
    so tests can substitute any factory or class.

    Args:
        request: FastAPI request object.
        code: Authorization code submitted by the guest.
        continue_url: Redirect destination after success.
        client_mac: Device MAC address.
        site: Omada site identifier.
        gateway_mac: Gateway MAC for Gateway auth mode.
        ap_mac: Access point MAC for EAP auth mode.
        vid: VLAN ID for Gateway auth mode.
        ssid_name: SSID name for EAP auth mode.
        radio_id: Radio identifier for EAP auth mode.
        session: Database session (from FastAPI DI).

    Returns:
        RedirectResponse on successful authorization.

    Raises:
        HTTPException: On CSRF, rate-limit, or validation
            failures.
    """
    overrides = request.app.dependency_overrides

    audit_factory = overrides.get(get_audit_service, get_audit_service)
    audit_service = audit_factory(session)

    config_factory = overrides.get(get_portal_config_dep, get_portal_config_dep)
    portal_config = config_factory(session)

    omada_factory = overrides.get(get_omada_adapter, get_omada_adapter)
    try:
        omada_adapter = omada_factory(request)
    except TypeError:
        omada_adapter = omada_factory()

    rate_limiter_cls = overrides.get(RateLimiter, RateLimiter)
    code_service_cls = overrides.get(UnifiedCodeService, UnifiedCodeService)
    redirect_validator_cls = overrides.get(RedirectValidator, RedirectValidator)

    return await _process_authorization(
        request=request,
        code=code,
        continue_url=continue_url,
        client_mac=client_mac,
        site=site,
        gateway_mac=gateway_mac,
        ap_mac=ap_mac,
        vid=vid,
        ssid_name=ssid_name,
        radio_id=radio_id,
        rate_limiter=rate_limiter_cls(),
        unified_code_service=code_service_cls(),
        redirect_validator=redirect_validator_cls(),
        session=session,
        audit_service=audit_service,
        portal_config=portal_config,
        omada_adapter=omada_adapter,
    )


@router.get("/authorize", response_class=HTMLResponse, response_model=None)
async def show_authorize_form(  # noqa: C901
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
    code: Annotated[Optional[str], Query()] = None,
    csrf_token: Annotated[Optional[str], Query()] = None,
    session: Optional[Session] = Depends(_get_optional_session),
) -> HTMLResponse | RedirectResponse:
    """Display authorization form or process a GET submission.

    When both ``code`` and ``csrf_token`` query parameters are
    present the request is treated as a form submission (the HTML
    form uses ``method="get"`` so that captive-portal gateways
    that drop POST bodies can still authorize guests).  Otherwise
    the authorization form is rendered.

    Args:
        request: FastAPI request object
        client_mac: Device MAC (from Omada redirect or form)
        client_ip: Device IP (from Omada redirect or form)
        site: Omada site identifier hash
        ap_mac: Access point MAC
        gateway_mac: Gateway MAC
        radio_id: Radio identifier
        ssid_name: SSID name
        vid: VLAN ID
        t: Timestamp (from Omada redirect)
        redirect_url: Original redirect URL
        continue_url: Redirect destination after success
        code: Authorization code (present on form submission)
        csrf_token: CSRF token (present on form submission)
        session: Database session (used on form submission)

    Returns:
        HTMLResponse with the form, or RedirectResponse on
        successful authorization.
    """
    # --- Form submission path (GET with code + csrf_token) ---
    if code and csrf_token:
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service temporarily unavailable.",
            )
        if getattr(request.app.state, "debug_guest_portal", False):
            redacted_params = {
                k: ("[REDACTED]" if k in {"code", "csrf_token"} else v)
                for k, v in request.query_params.items()
            }
            _logger.debug(
                "GET %s (submission) query_params=%s",
                request.url.path,
                redacted_params,
            )

        return await _handle_get_submission(
            request=request,
            code=code,
            continue_url=continue_url,
            client_mac=client_mac,
            site=site,
            gateway_mac=gateway_mac,
            ap_mac=ap_mac,
            vid=vid,
            ssid_name=ssid_name,
            radio_id=radio_id,
            session=session,
        )

    # --- Form display path ---
    omada_params = {
        "clientMac": client_mac or "",
        "clientIp": client_ip or "",
        "site": site or "",
        "apMac": ap_mac or "",
        "gatewayMac": gateway_mac or "",
        "radioId": radio_id or "",
        "ssidName": ssid_name or "",
        "vid": vid or "",
        "t": t or "",
        "redirectUrl": redirect_url or "",
    }

    if getattr(request.app.state, "debug_guest_portal", False):
        redacted_params = {
            k: ("[REDACTED]" if k in {"code", "csrf_token"} else v)
            for k, v in request.query_params.items()
        }
        form_action = f"{request.scope.get('root_path', '')}/guest/authorize"
        _logger.debug(
            "GET %s query_params=%s omada_params=%s",
            request.url.path,
            redacted_params,
            omada_params,
        )
        _logger.debug(
            "GET %s form_action=%s  User-Agent=%s",
            request.url.path,
            form_action,
            request.headers.get("user-agent", ""),
        )
        _logger.debug(
            "GET %s route_csp=%s",
            request.url.path,
            _add_security_headers(HTMLResponse("")).headers.get(
                "Content-Security-Policy",
                "",
            ),
        )

    effective_continue = (
        continue_url or redirect_url or f"{request.scope.get('root_path', '')}/guest/welcome"
    )

    generated_csrf = _guest_csrf.generate_token()

    response = templates.TemplateResponse(
        request=request,
        name="guest/authorize.html",
        context={
            "continue_url": effective_continue,
            "csrf_token": generated_csrf,
            "omada_params": omada_params,
        },
    )

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


async def _process_authorization(  # noqa: C901
    *,
    request: Request,
    code: str,
    continue_url: str | None,
    client_mac: str | None,
    site: str | None,
    gateway_mac: str | None,
    ap_mac: str | None,
    vid: str | None,
    ssid_name: str | None,
    radio_id: str | None,
    rate_limiter: RateLimiter,
    unified_code_service: UnifiedCodeService,
    redirect_validator: RedirectValidator,
    session: Session,
    audit_service: AuditService,
    portal_config: PortalConfig,
    omada_adapter: OmadaAdapter | None,
) -> RedirectResponse:
    """Execute the full guest authorization flow.

    Shared logic for both GET and POST authorization paths.
    Validates the CSRF token, checks the rate limit, extracts
    the device MAC, validates the submitted code, creates an
    access grant, and authorizes the client on the controller.

    Args:
        request: FastAPI request object.
        code: Authorization code (voucher or booking code).
        continue_url: Optional redirect destination.
        client_mac: Device MAC from Omada controller redirect.
        site: Omada site identifier from controller redirect.
        gateway_mac: Gateway MAC for Gateway auth mode.
        ap_mac: Access point MAC for EAP auth mode.
        vid: VLAN ID for Gateway auth mode.
        ssid_name: SSID name for EAP auth mode.
        radio_id: Radio identifier for EAP auth mode.
        rate_limiter: Rate limiting service.
        unified_code_service: Code validation service.
        redirect_validator: Redirect URL validation service.
        session: Database session.
        audit_service: Audit logging service.
        portal_config: Portal configuration.
        omada_adapter: Optional Omada controller adapter.

    Returns:
        RedirectResponse to the success page or original
        destination.

    Raises:
        HTTPException: On CSRF, rate-limit, or validation
            failures.
    """
    # Store retry URL query params so the error page can link
    # back with the original Omada parameters preserved.
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

    debug = getattr(request.app.state, "debug_guest_portal", False)

    if debug:
        _logger.debug(
            "%s /authorize step=csrf_start",
            request.method,
        )

    # Validate CSRF token
    await _guest_csrf.validate_token(request)

    if debug:
        _logger.debug(
            "%s /authorize step=csrf_ok",
            request.method,
        )

    # Get trusted proxy networks from configuration
    trusted_networks = portal_config.get_trusted_networks()
    client_ip = get_client_ip(
        request,
        trust_proxies=True,
        trusted_networks=trusted_networks,
    )

    # Check rate limit
    if not rate_limiter.is_allowed(client_ip):
        retry_after = rate_limiter.get_retry_after_seconds(client_ip)

        await audit_service.log(
            actor=f"guest@{client_ip}",
            action="guest.authorize",
            outcome="rate_limited",
            meta={
                "client_ip": client_ip,
                "user_agent": request.headers.get(
                    "User-Agent",
                    "unknown",
                ),
                "retry_after": retry_after,
            },
        )

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=("Too many authorization attempts. Please try again later."),
            headers={"Retry-After": str(retry_after or 60)},
        )

    # Extract device MAC address
    try:
        mac_address = _extract_mac_address(
            request,
            form_mac=client_mac,
        )
    except HTTPException as e:
        await audit_service.log(
            actor=f"guest@{client_ip}",
            action="guest.authorize",
            outcome="error",
            meta={
                "client_ip": client_ip,
                "user_agent": request.headers.get(
                    "User-Agent",
                    "unknown",
                ),
                "error": "mac_extraction_failed",
                "detail": str(e.detail),
            },
        )
        raise

    # Validate code format and determine type
    try:
        validation_result = await unified_code_service.validate_code(
            code,
        )
    except ValueError as e:
        await audit_service.log(
            actor=f"guest@{client_ip}",
            action="guest.authorize",
            outcome="denied",
            meta={
                "client_ip": client_ip,
                "mac": mac_address,
                "user_agent": request.headers.get(
                    "User-Agent",
                    "unknown",
                ),
                "error": "invalid_code_format",
                "detail": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    if debug:
        _logger.debug(
            "%s /authorize step=code_validated  type=%s  code=%r",
            request.method,
            validation_result.code_type.value,
            validation_result.normalized_code,
        )

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

            if debug:
                _logger.debug(
                    "%s /authorize step=booking_found  event=%r  integration=%r",
                    request.method,
                    event.slot_code if event else None,
                    integration.integration_id if integration else None,
                )

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

            if debug:
                _logger.debug(
                    "%s /authorize step=grant_created  grant_id=%s  mac=%s",
                    request.method,
                    grant.id,
                    grant.mac,
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid code type",
            )

    except VoucherDeviceLimitError:
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

    if debug:
        _logger.debug(
            "%s /authorize step=controller_auth_start  adapter=%s",
            request.method,
            type(omada_adapter).__name__ if omada_adapter else "None",
        )

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
        redirect_dest = continue_url
    else:
        redirect_dest = f"{request.scope.get('root_path', '')}/guest/welcome"

    # Success — redirect with grant ID cookie
    response = RedirectResponse(
        url=redirect_dest,
        status_code=status.HTTP_303_SEE_OTHER,
    )
    response.headers["Referrer-Policy"] = "strict-origin"
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        key="grant_id",
        value=str(grant.id),
        httponly=True,
        samesite="strict",
        max_age=3600,  # 1 hour cookie lifetime
    )
    return response


@router.post("/authorize")
async def handle_authorization(
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
    """Process guest authorization code via POST submission.

    Delegates to ``_process_authorization`` after resolving
    FastAPI dependencies.

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
        unified_code_service: Code validation service
        redirect_validator: Redirect URL validation service
        session: Database session
        audit_service: Audit logging service
        portal_config: Portal configuration
        omada_adapter: Optional Omada controller adapter

    Returns:
        RedirectResponse to success page or original destination

    Raises:
        HTTPException: On CSRF, rate-limit, or validation
            failures.
    """
    if getattr(request.app.state, "debug_guest_portal", False):
        _logger.debug(
            "POST /authorize client_mac=%r site=%r headers=%s",
            client_mac,
            site,
            {k: v for k, v in request.headers.items() if "mac" in k.lower()},
        )

    return await _process_authorization(
        request=request,
        code=code,
        continue_url=continue_url,
        client_mac=client_mac,
        site=site,
        gateway_mac=gateway_mac,
        ap_mac=ap_mac,
        vid=vid,
        ssid_name=ssid_name,
        radio_id=radio_id,
        rate_limiter=rate_limiter,
        unified_code_service=unified_code_service,
        redirect_validator=redirect_validator,
        session=session,
        audit_service=audit_service,
        portal_config=portal_config,
        omada_adapter=omada_adapter,
    )


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
