# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Safe redirect helpers for fixed admin UI routes."""

from __future__ import annotations

from fastapi import status
from fastapi.responses import RedirectResponse

_FORBIDDEN_ROOT_CHARS = ("\\", "?", "#")


def sanitize_admin_root_path(root_path: object) -> str:
    """Normalize an ASGI root path into a safe internal URL prefix.

    Args:
        root_path: Value read from the request scope.

    Returns:
        A safe internal path prefix, or an empty string when the input could
        make a redirect absolute, protocol-relative, or header-splitting.
    """
    if not isinstance(root_path, str):
        return ""
    if any(
        char in _FORBIDDEN_ROOT_CHARS or char.isspace() or ord(char) < 32 or ord(char) == 127
        for char in root_path
    ):
        return ""

    root = root_path
    if not root or root == "/":
        return ""
    if "://" in root or root.startswith("//"):
        return ""
    if not root.startswith("/"):
        root = f"/{root}"
    return root.rstrip("/")


def admin_redirect_url(root_path: object, admin_path: str) -> str:
    """Build a fixed internal admin URL with a sanitized root path.

    Args:
        root_path: Value read from the request scope.
        admin_path: Fixed admin path and optional query string.

    Returns:
        Internal admin URL safe for a Location header.

    Raises:
        ValueError: If ``admin_path`` is not an absolute admin path.
    """
    if admin_path != "/admin" and not admin_path.startswith(("/admin/", "/admin?")):
        raise ValueError("admin_path must start with /admin")
    return f"{sanitize_admin_root_path(root_path)}{admin_path}"


def safe_admin_redirect(root_path: object, admin_path: str) -> RedirectResponse:
    """Build a 303 redirect to a fixed internal admin path.

    Args:
        root_path: Value read from the request scope.
        admin_path: Fixed admin path and optional query string.

    Returns:
        Redirect response using a sanitized root path.
    """
    return RedirectResponse(
        url=admin_redirect_url(root_path, admin_path),
        status_code=status.HTTP_303_SEE_OTHER,
    )
