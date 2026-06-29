# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Guest portal routes for authorization and welcome pages."""

from __future__ import annotations

import logging
from collections.abc import Generator
from pathlib import Path
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from captive_portal._version import __version__
from captive_portal.api.routes.guest_authorization.bookings import authorize_booking
from captive_portal.api.routes.guest_authorization.context import (
    GuestAuthorizationContext,
    GuestAuthorizationDependencies,
    GuestOmadaParams,
    audit_controller_failure,
    audit_success,
    enforce_rate_limit,
    extract_authorization_mac,
    resolve_client_ip,
    validate_guest_code,
)
from captive_portal.api.routes.guest_authorization import controller as _controller
from captive_portal.api.routes.guest_authorization.controller import (
    apply_legacy_site_override,
    apply_omada_metadata,
)
from captive_portal.api.routes.guest_authorization.errors import (
    add_security_headers as _add_security_headers,
    sanitize_error_message as _sanitize_error_message,
)
from captive_portal.api.routes.guest_authorization.form import (
    is_get_submission,
    log_form_debug,
    log_get_submission_debug,
    render_authorize_form,
)
from captive_portal.api.routes.guest_authorization import mac_address as _mac_address
from captive_portal.api.routes.guest_authorization.redirects import (
    build_retry_query,
    safe_redirect_destination,
    success_redirect,
)
from captive_portal.api.routes.guest_authorization.vouchers import authorize_voucher
from captive_portal.controllers.tp_omada.adapter_protocol import OmadaControllerAdapter
from captive_portal.controllers.tp_omada.dependencies import get_omada_adapter
from captive_portal.models.access_grant import GrantStatus
from captive_portal.models.portal_config import PortalConfig
from captive_portal.persistence.database import get_session
from captive_portal.security.hmac_csrf import HMACCSRFProtection
from captive_portal.security.rate_limiter import RateLimiter
from captive_portal.services.audit_service import AuditService
from captive_portal.services.redirect_validator import RedirectValidator
from captive_portal.services.unified_code_service import CodeType, UnifiedCodeService

_logger = logging.getLogger("captive_portal.guest")

_SITE_ID_PATTERN = _controller.SITE_ID_PATTERN
_truncate = _controller.truncate
_apply_site_override = _controller.apply_site_override
_authorize_with_controller = _controller.authorize_with_controller
_extract_mac_address = _mac_address.extract_mac_address

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "templates"

router = APIRouter(prefix="/guest", tags=["guest"])
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.autoescape = True
templates.env.globals["app_version"] = __version__

_guest_csrf = HMACCSRFProtection()


def get_audit_service(session: Session = Depends(get_session)) -> AuditService:
    """Dependency for creating AuditService.

    Args:
        session: Database session.

    Returns:
        Configured AuditService instance.
    """
    return AuditService(session)


def _get_optional_session(
    request: Request,
) -> Generator[Optional[Session], None, None]:
    """Yield a database session only for GET form submissions.

    Args:
        request: Incoming HTTP request.

    Yields:
        Database session for submissions, ``None`` otherwise.
    """
    qp = request.query_params
    if not is_get_submission(qp.get("code"), qp.get("csrf_token")):
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
        session: Database session.

    Returns:
        PortalConfig singleton instance.

    Raises:
        HTTPException: If portal configuration cannot be loaded or created.
    """
    stmt: Any = select(PortalConfig).where(PortalConfig.id == 1)
    config: Optional[PortalConfig] = session.exec(stmt).first()

    if not config:
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


async def _handle_get_submission(
    *,
    request: Request,
    code: str,
    omada_params: GuestOmadaParams,
    session: Session,
) -> RedirectResponse:
    """Resolve remaining dependencies and process a GET submission.

    Args:
        request: FastAPI request object.
        code: Authorization code submitted by the guest.
        omada_params: Omada and redirect metadata from query parameters.
        session: Database session from the optional GET dependency.

    Returns:
        RedirectResponse on successful authorization.

    Raises:
        HTTPException: On authorization failures.
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
        omada_params=omada_params,
        dependencies=GuestAuthorizationDependencies(
            rate_limiter=rate_limiter_cls(),
            unified_code_service=code_service_cls(),
            redirect_validator=redirect_validator_cls(),
            session=session,
            audit_service=audit_service,
            portal_config=portal_config,
            omada_adapter=omada_adapter,
        ),
    )


@router.get("/authorize", response_class=HTMLResponse, response_model=None)
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
    code: Annotated[Optional[str], Query()] = None,
    csrf_token: Annotated[Optional[str], Query()] = None,
    session: Optional[Session] = Depends(_get_optional_session),
) -> HTMLResponse | RedirectResponse:
    """Display authorization form or process a GET submission.

    Args:
        request: FastAPI request object.
        client_mac: Device MAC from Omada redirect or form.
        client_ip: Device IP from Omada redirect.
        site: Omada site identifier hash.
        ap_mac: Access point MAC.
        gateway_mac: Gateway MAC.
        radio_id: Radio identifier.
        ssid_name: SSID name.
        vid: VLAN ID.
        t: Timestamp from Omada redirect.
        redirect_url: Original redirect URL.
        continue_url: Redirect destination after success.
        code: Authorization code for GET submissions.
        csrf_token: CSRF token for GET submissions.
        session: Database session used for GET submissions.

    Returns:
        HTMLResponse with the form, or RedirectResponse on successful authorization.
    """
    omada_params = GuestOmadaParams(
        client_mac=client_mac,
        client_ip=client_ip,
        site=site,
        gateway_mac=gateway_mac,
        ap_mac=ap_mac,
        radio_id=radio_id,
        ssid_name=ssid_name,
        vid=vid,
        t=t,
        redirect_url=redirect_url,
        continue_url=continue_url,
    )

    if is_get_submission(code, csrf_token):
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service temporarily unavailable.",
            )
        if getattr(request.app.state, "debug_guest_portal", False):
            log_get_submission_debug(request)
        return await _handle_get_submission(
            request=request,
            code=code or "",
            omada_params=omada_params,
            session=session,
        )

    if getattr(request.app.state, "debug_guest_portal", False):
        log_form_debug(request, omada_params)

    return render_authorize_form(
        request=request,
        templates=templates,
        csrf=_guest_csrf,
        params=omada_params,
    )


async def _process_authorization(
    *,
    request: Request,
    code: str,
    omada_params: GuestOmadaParams,
    dependencies: GuestAuthorizationDependencies,
) -> RedirectResponse:
    """Execute the shared guest authorization orchestration.

    Args:
        request: FastAPI request object.
        code: Submitted authorization code.
        omada_params: Omada and redirect metadata.
        dependencies: Resolved request dependencies.

    Returns:
        RedirectResponse to the success destination.

    Raises:
        HTTPException: On CSRF, rate-limit, validation, or controller failures.
    """
    request.state.retry_query = build_retry_query(omada_params)
    debug = getattr(request.app.state, "debug_guest_portal", False)

    if debug:
        _logger.debug("%s /authorize step=csrf_start", request.method)
    await _guest_csrf.validate_token(request)
    if debug:
        _logger.debug("%s /authorize step=csrf_ok", request.method)

    client_ip = resolve_client_ip(request, dependencies.portal_config)
    flow_context = GuestAuthorizationContext(
        client_ip=client_ip,
        retry_query=request.state.retry_query,
    )
    request.state.guest_authorization_context = flow_context
    await enforce_rate_limit(
        rate_limiter=dependencies.rate_limiter,
        audit_service=dependencies.audit_service,
        request=request,
        client_ip=client_ip,
    )
    mac_address = await extract_authorization_mac(
        request=request,
        form_mac=omada_params.client_mac,
        audit_service=dependencies.audit_service,
        client_ip=client_ip,
    )
    flow_context.mac_address = mac_address
    validation_result = await validate_guest_code(
        code=code,
        service=dependencies.unified_code_service,
        audit_service=dependencies.audit_service,
        request=request,
        client_ip=client_ip,
        mac_address=mac_address,
    )
    flow_context.validation_result = validation_result

    if debug:
        _logger.debug(
            "%s /authorize step=code_validated  type=%s  code=%r",
            request.method,
            validation_result.code_type.value,
            validation_result.normalized_code,
        )

    if validation_result.code_type == CodeType.VOUCHER:
        decision = await authorize_voucher(
            validation_result=validation_result,
            session=dependencies.session,
            audit_service=dependencies.audit_service,
            request=request,
            client_ip=client_ip,
            mac_address=mac_address,
            vid=omada_params.vid,
        )
    elif validation_result.code_type == CodeType.BOOKING:
        decision = await authorize_booking(
            validation_result=validation_result,
            session=dependencies.session,
            audit_service=dependencies.audit_service,
            request=request,
            client_ip=client_ip,
            mac_address=mac_address,
            vid=omada_params.vid,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid code type",
        )

    flow_context.vlan_meta = decision.vlan_meta
    flow_context.grant = decision.grant
    grant = apply_omada_metadata(decision.grant, omada_params)
    apply_legacy_site_override(dependencies.omada_adapter, omada_params.site)

    if debug:
        _logger.debug(
            "%s /authorize step=controller_auth_start  adapter=%s",
            request.method,
            type(dependencies.omada_adapter).__name__ if dependencies.omada_adapter else "None",
        )

    grant, error_detail = await _authorize_with_controller(
        adapter=dependencies.omada_adapter,
        grant=grant,
        mac_address=mac_address,
        gateway_mac=grant.omada_gateway_mac,
        ap_mac=grant.omada_ap_mac,
        ssid_name=grant.omada_ssid_name,
        radio_id=grant.omada_radio_id,
        vid=grant.omada_vid,
    )
    dependencies.session.add(grant)
    dependencies.session.commit()
    dependencies.session.refresh(grant)
    decision.grant = grant

    if grant.status == GrantStatus.FAILED:
        await audit_controller_failure(
            audit_service=dependencies.audit_service,
            request=request,
            client_ip=client_ip,
            mac_address=mac_address,
            grant=grant,
            error_detail=error_detail,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="WiFi authorization could not be completed. Please try again or contact the host.",
        )

    dependencies.rate_limiter.clear(client_ip)
    await audit_success(
        audit_service=dependencies.audit_service,
        request=request,
        client_ip=client_ip,
        mac_address=mac_address,
        decision=decision,
    )
    redirect_dest = safe_redirect_destination(
        request,
        omada_params.continue_url,
        dependencies.redirect_validator,
    )
    return success_redirect(redirect_dest, grant.id)


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
    omada_adapter: OmadaControllerAdapter | None = Depends(get_omada_adapter),
) -> RedirectResponse:
    """Process guest authorization code via POST submission.

    Args:
        request: FastAPI request object.
        code: Authorization code submitted by the guest.
        continue_url: Optional redirect destination.
        client_mac: Device MAC from hidden form data.
        site: Omada site identifier.
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
        RedirectResponse to success page or original destination.

    Raises:
        HTTPException: On CSRF, rate-limit, or validation failures.
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
        omada_params=GuestOmadaParams(
            client_mac=client_mac,
            site=site,
            gateway_mac=gateway_mac,
            ap_mac=ap_mac,
            vid=vid,
            ssid_name=ssid_name,
            radio_id=radio_id,
            continue_url=continue_url,
        ),
        dependencies=GuestAuthorizationDependencies(
            rate_limiter=rate_limiter,
            unified_code_service=unified_code_service,
            redirect_validator=redirect_validator,
            session=session,
            audit_service=audit_service,
            portal_config=portal_config,
            omada_adapter=omada_adapter,
        ),
    )


@router.get("/welcome", response_class=HTMLResponse)
async def show_welcome(request: Request) -> HTMLResponse:
    """Display post-authorization welcome page.

    Args:
        request: FastAPI request object.

    Returns:
        Rendered welcome page with security headers.
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
        request: FastAPI request object.
        message: Optional error message to display.

    Returns:
        Rendered error page with security headers.
    """
    response = templates.TemplateResponse(
        request=request,
        name="guest/error.html",
        context={
            "error_message": _sanitize_error_message(message),
            "retry_url": f"{request.scope.get('root_path', '')}/guest/authorize",
        },
    )
    return _add_security_headers(response)
