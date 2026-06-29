# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Guest authorization orchestration helpers shared by GET and POST routes."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from fastapi import HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from captive_portal.controllers.tp_omada.adapter_protocol import OmadaControllerAdapter
from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.models.portal_config import PortalConfig
from captive_portal.security.hmac_csrf import HMACCSRFProtection
from captive_portal.security.rate_limiter import RateLimiter
from captive_portal.services.audit_service import AuditService
from captive_portal.services.redirect_validator import RedirectValidator
from captive_portal.services.unified_code_service import CodeType, UnifiedCodeService

from .bookings import authorize_booking
from .context import (
    AuthorizationDecisionResult,
    GuestAuthorizationContext,
    GuestAuthorizationDependencies,
    GuestDecisionContext,
    GuestOmadaParams,
    audit_controller_failure,
    audit_success,
    enforce_rate_limit,
    extract_authorization_mac,
    resolve_client_ip,
    validate_guest_code,
)
from .controller import apply_legacy_site_override, apply_omada_metadata, authorize_with_controller
from .redirects import build_retry_query, safe_redirect_destination, success_redirect
from .vouchers import authorize_voucher

_logger = logging.getLogger("captive_portal.guest")


@dataclass(frozen=True, slots=True)
class GuestGetSubmissionProviders:
    """Dependency provider callables needed for GET authorization submissions."""

    audit_service_factory: Callable[[Session], AuditService]
    portal_config_factory: Callable[[Session], PortalConfig]
    omada_adapter_factory: Callable[..., OmadaControllerAdapter | None]
    rate_limiter_factory: Callable[[], RateLimiter]
    code_service_factory: Callable[[], UnifiedCodeService]
    redirect_validator_factory: Callable[[], RedirectValidator]


async def _handle_get_submission(
    *,
    request: Request,
    code: str,
    omada_params: GuestOmadaParams,
    session: Session,
    csrf: HMACCSRFProtection,
    providers: GuestGetSubmissionProviders,
) -> RedirectResponse:
    """Resolve remaining dependencies and process a GET submission."""
    omada_adapter = _resolve_omada_adapter(providers.omada_adapter_factory, request)
    return await _process_authorization(
        request=request,
        code=code,
        omada_params=omada_params,
        dependencies=GuestAuthorizationDependencies(
            rate_limiter=providers.rate_limiter_factory(),
            unified_code_service=providers.code_service_factory(),
            redirect_validator=providers.redirect_validator_factory(),
            session=session,
            audit_service=providers.audit_service_factory(session),
            portal_config=providers.portal_config_factory(session),
            omada_adapter=omada_adapter,
        ),
        csrf=csrf,
    )


def _resolve_omada_adapter(
    factory: Callable[..., OmadaControllerAdapter | None],
    request: Request,
) -> OmadaControllerAdapter | None:
    """Resolve the optional Omada adapter using current override behavior."""
    try:
        return factory(request)
    except TypeError:
        return factory()


async def _process_authorization(
    *,
    request: Request,
    code: str,
    omada_params: GuestOmadaParams,
    dependencies: GuestAuthorizationDependencies,
    csrf: HMACCSRFProtection,
) -> RedirectResponse:
    """Execute the shared guest authorization orchestration."""
    flow_context = await _prepare_authorization_flow(
        request=request,
        code=code,
        omada_params=omada_params,
        dependencies=dependencies,
        csrf=csrf,
    )
    decision = await _dispatch_authorization_decision(
        request=request,
        omada_params=omada_params,
        dependencies=dependencies,
        flow_context=flow_context,
    )
    flow_context.vlan_meta = decision.vlan_meta
    flow_context.grant = decision.grant
    grant = await _finalize_controller_authorization(
        request=request,
        omada_params=omada_params,
        dependencies=dependencies,
        flow_context=flow_context,
        decision=decision,
    )
    return await _complete_success(
        request=request,
        omada_params=omada_params,
        dependencies=dependencies,
        flow_context=flow_context,
        decision=decision,
        grant=grant,
    )


async def _prepare_authorization_flow(
    *,
    request: Request,
    code: str,
    omada_params: GuestOmadaParams,
    dependencies: GuestAuthorizationDependencies,
    csrf: HMACCSRFProtection,
) -> GuestAuthorizationContext:
    """Validate CSRF, rate limit, MAC address, and submitted code."""
    request.state.retry_query = build_retry_query(omada_params)
    _debug(request, "csrf_start")
    await csrf.validate_token(request)
    _debug(request, "csrf_ok")

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
    flow_context.mac_address = await extract_authorization_mac(
        request=request,
        form_mac=omada_params.client_mac,
        audit_service=dependencies.audit_service,
        client_ip=client_ip,
    )
    flow_context.validation_result = await validate_guest_code(
        code=code,
        service=dependencies.unified_code_service,
        audit_service=dependencies.audit_service,
        request=request,
        client_ip=client_ip,
        mac_address=flow_context.mac_address,
    )
    _log_code_validated(
        request,
        flow_context.validation_result.code_type.value,
        flow_context.validation_result.normalized_code,
    )
    return flow_context


def _debug(request: Request, step: str) -> None:
    """Emit a guest authorization debug step when debugging is enabled."""
    if getattr(request.app.state, "debug_guest_portal", False):
        _logger.debug("%s /authorize step=%s", request.method, step)


def _log_code_validated(request: Request, code_type: str, normalized_code: str) -> None:
    """Emit the current debug log for code validation success."""
    if getattr(request.app.state, "debug_guest_portal", False):
        _logger.debug(
            "%s /authorize step=code_validated  type=%s  code=%r",
            request.method,
            code_type,
            normalized_code,
        )


async def _dispatch_authorization_decision(
    *,
    request: Request,
    omada_params: GuestOmadaParams,
    dependencies: GuestAuthorizationDependencies,
    flow_context: GuestAuthorizationContext,
) -> AuthorizationDecisionResult:
    """Dispatch to the voucher or booking decision helper."""
    validation_result = flow_context.validation_result
    if validation_result is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code type")
    decision_context = GuestDecisionContext(
        request=request,
        audit_service=dependencies.audit_service,
        client_ip=flow_context.client_ip,
        mac_address=cast(str, flow_context.mac_address),
        vid=omada_params.vid,
    )
    if validation_result.code_type == CodeType.VOUCHER:
        return await authorize_voucher(
            validation_result=validation_result,
            session=dependencies.session,
            decision_context=decision_context,
        )
    if validation_result.code_type == CodeType.BOOKING:
        return await authorize_booking(
            validation_result=validation_result,
            session=dependencies.session,
            decision_context=decision_context,
        )
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code type")


async def _finalize_controller_authorization(
    *,
    request: Request,
    omada_params: GuestOmadaParams,
    dependencies: GuestAuthorizationDependencies,
    flow_context: GuestAuthorizationContext,
    decision: AuthorizationDecisionResult,
) -> AccessGrant:
    """Apply Omada metadata, call the controller, and persist the result."""
    grant = apply_omada_metadata(decision.grant, omada_params)
    apply_legacy_site_override(dependencies.omada_adapter, omada_params.site)
    _log_controller_start(request, dependencies.omada_adapter)
    grant, error_detail = await authorize_with_controller(
        adapter=dependencies.omada_adapter,
        grant=grant,
        mac_address=cast(str, flow_context.mac_address),
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
        await _raise_controller_failure(
            request=request,
            dependencies=dependencies,
            flow_context=flow_context,
            grant=grant,
            error_detail=error_detail,
        )
    return grant


def _log_controller_start(
    request: Request,
    adapter: OmadaControllerAdapter | None,
) -> None:
    """Emit the current debug log before controller authorization."""
    if getattr(request.app.state, "debug_guest_portal", False):
        _logger.debug(
            "%s /authorize step=controller_auth_start  adapter=%s",
            request.method,
            type(adapter).__name__ if adapter else "None",
        )


async def _raise_controller_failure(
    *,
    request: Request,
    dependencies: GuestAuthorizationDependencies,
    flow_context: GuestAuthorizationContext,
    grant: AccessGrant,
    error_detail: str | None,
) -> None:
    """Audit a controller authorization failure and raise the current 502."""
    await audit_controller_failure(
        audit_service=dependencies.audit_service,
        request=request,
        client_ip=flow_context.client_ip,
        mac_address=cast(str, flow_context.mac_address),
        grant=grant,
        error_detail=error_detail,
    )
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="WiFi authorization could not be completed. Please try again or contact the host.",
    )


async def _complete_success(
    *,
    request: Request,
    omada_params: GuestOmadaParams,
    dependencies: GuestAuthorizationDependencies,
    flow_context: GuestAuthorizationContext,
    decision: AuthorizationDecisionResult,
    grant: AccessGrant,
) -> RedirectResponse:
    """Audit successful authorization and build the success redirect."""
    dependencies.rate_limiter.clear(flow_context.client_ip)
    await audit_success(
        audit_service=dependencies.audit_service,
        request=request,
        client_ip=flow_context.client_ip,
        mac_address=cast(str, flow_context.mac_address),
        decision=decision,
    )
    redirect_dest = safe_redirect_destination(
        request,
        omada_params.continue_url,
        dependencies.redirect_validator,
    )
    return success_redirect(redirect_dest, grant.id)
