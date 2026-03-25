# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Captive portal detection routes.

Handles common captive portal detection URLs and redirects to authorization form.
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


@router.get("/generate_204")
@router.get("/gen_204")
async def android_captive_detect(request: Request) -> Response:
    """Android captive portal detection.

    Args:
        request: FastAPI request object

    Returns:
        RedirectResponse: Redirect to authorization form (triggers captive portal UI)
    """
    return RedirectResponse(url="/guest/authorize", status_code=302)


@router.get("/connecttest.txt")
@router.get("/ncsi.txt")
async def windows_captive_detect(request: Request) -> Response:
    """Windows captive portal detection.

    Args:
        request: FastAPI request object

    Returns:
        RedirectResponse: Redirect to authorization form
    """
    return RedirectResponse(url="/guest/authorize", status_code=302)


@router.get("/hotspot-detect.html")
@router.get("/library/test/success.html")
async def apple_captive_detect(request: Request) -> Response:
    """Apple iOS/macOS captive portal detection.

    Args:
        request: FastAPI request object

    Returns:
        RedirectResponse: Redirect to authorization form
    """
    return RedirectResponse(url="/guest/authorize", status_code=302)


@router.get("/success.txt")
async def firefox_captive_detect(request: Request) -> Response:
    """Firefox captive portal detection.

    Args:
        request: FastAPI request object

    Returns:
        RedirectResponse: Redirect to authorization form
    """
    return RedirectResponse(url="/guest/authorize", status_code=302)
