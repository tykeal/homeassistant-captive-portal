# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Captive portal detection routes.

Handles common captive portal detection URLs and redirects to authorization form.
Both the ingress and guest listeners mount this router.  When running on the
guest listener, ``request.app.state.guest_external_url`` provides the external
redirect base; on the ingress listener that attribute is absent and the ingress
``root_path`` is used instead.
"""

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

router = APIRouter(tags=["captive-detection"])

# Common captive portal detection URLs
DETECTION_URLS = [
    "/generate_204",  # Android
    "/gen_204",  # Android alternative
    "/connecttest.txt",  # Windows
    "/ncsi.txt",  # Windows alternative
    "/hotspot-detect.html",  # Apple iOS/macOS
    "/library/test/success.html",  # Apple alternative
    "/success.txt",  # Firefox
]


def _resolve_redirect_base(request: Request) -> str:
    """Determine the redirect base URL for captive detection.

    On the guest listener, ``request.app.state.guest_external_url``
    carries the administrator-configured external URL.  On the ingress
    listener, the ASGI ``root_path`` (set by HA ingress proxy) is used.

    Args:
        request: Incoming HTTP request.

    Returns:
        Base URL string to prepend to ``/guest/authorize``.
    """
    guest_url: str = getattr(request.app.state, "guest_external_url", "")
    if guest_url:
        return guest_url
    return request.scope.get("root_path", "") or ""


@router.get("/generate_204")
@router.get("/gen_204")
async def android_captive_detect(request: Request) -> Response:
    """Android captive portal detection.

    Args:
        request: FastAPI request object

    Returns:
        RedirectResponse: Redirect to authorization form (triggers captive portal UI)
    """
    base = _resolve_redirect_base(request)
    return RedirectResponse(url=f"{base}/guest/authorize", status_code=302)


@router.get("/connecttest.txt")
@router.get("/ncsi.txt")
async def windows_captive_detect(request: Request) -> Response:
    """Windows captive portal detection.

    Args:
        request: FastAPI request object

    Returns:
        RedirectResponse: Redirect to authorization form
    """
    base = _resolve_redirect_base(request)
    return RedirectResponse(url=f"{base}/guest/authorize", status_code=302)


@router.get("/hotspot-detect.html")
@router.get("/library/test/success.html")
async def apple_captive_detect(request: Request) -> Response:
    """Apple iOS/macOS captive portal detection.

    Args:
        request: FastAPI request object

    Returns:
        RedirectResponse: Redirect to authorization form
    """
    base = _resolve_redirect_base(request)
    return RedirectResponse(url=f"{base}/guest/authorize", status_code=302)


@router.get("/success.txt")
async def firefox_captive_detect(request: Request) -> Response:
    """Firefox captive portal detection.

    Args:
        request: FastAPI request object

    Returns:
        RedirectResponse: Redirect to authorization form
    """
    base = _resolve_redirect_base(request)
    return RedirectResponse(url=f"{base}/guest/authorize", status_code=302)
