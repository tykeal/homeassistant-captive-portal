# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Normalization helpers for guest portal characterization tests."""

from __future__ import annotations

import re
from http.cookies import SimpleCookie
from typing import Final

_CSRF_VALUE_RE: Final = re.compile(r'(name="csrf_token" value=")[^"]+(")')
_GRANT_COOKIE_RE: Final = re.compile(r"(grant_id=)[^;,]+")
_UUID_RE: Final = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_ISO_TIMESTAMP_RE: Final = re.compile(
    r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:\+00:00|Z)\b"
)


def normalize_guest_html(html: str) -> str:
    """Return guest HTML with only dynamic CSRF values normalized.

    Args:
        html: Rendered guest portal HTML.

    Returns:
        HTML with generated CSRF token values replaced by a stable marker.
    """
    return _CSRF_VALUE_RE.sub(r"\1<csrf-token>\2", html)


def normalize_dynamic_values(value: str) -> str:
    """Normalize dynamic identifiers and timestamps in characterization text.

    Args:
        value: Text containing generated values.

    Returns:
        Text with grant IDs, cookie values, and ISO timestamps replaced by
        explicit placeholders while leaving stable behavior unchanged.
    """
    normalized = _GRANT_COOKIE_RE.sub(r"\1<grant-id>", value)
    normalized = _UUID_RE.sub("<generated-id>", normalized)
    return _ISO_TIMESTAMP_RE.sub("<timestamp>", normalized)


def normalized_set_cookie(headers: list[str]) -> list[str]:
    """Normalize dynamic grant cookie values while preserving attributes.

    Args:
        headers: Raw ``Set-Cookie`` header values.

    Returns:
        Normalized ``Set-Cookie`` strings suitable for exact comparison.
    """
    normalized: list[str] = []
    for header in headers:
        cookie = SimpleCookie[str]()
        cookie.load(header)
        if "grant_id" in cookie:
            cookie["grant_id"] = "<grant-id>"
            normalized.append(cookie.output(header="").strip())
        else:
            normalized.append(header)
    return normalized
