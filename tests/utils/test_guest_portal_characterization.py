# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for guest portal characterization normalization helpers."""

from __future__ import annotations

from tests.utils.guest_portal_characterization import (
    normalize_dynamic_values,
    normalize_guest_html,
    normalized_set_cookie,
)


def test_normalize_guest_html_replaces_only_csrf_value() -> None:
    """CSRF normalization preserves stable surrounding HTML."""
    html = '<input type="hidden" name="csrf_token" value="generated-token">'

    assert normalize_guest_html(html) == (
        '<input type="hidden" name="csrf_token" value="<csrf-token>">'
    )


def test_normalize_dynamic_values_replaces_ids_and_timestamps() -> None:
    """Dynamic ID and timestamp normalization keeps stable text exact."""
    value = "grant_id=2c2e3e9b-5c8f-48c2-bab1-44f7d53f8646; created=2026-06-29T00:30:01+00:00"

    assert normalize_dynamic_values(value) == "grant_id=<grant-id>; created=<timestamp>"


def test_normalized_set_cookie_preserves_cookie_attributes() -> None:
    """Set-Cookie normalization replaces only dynamic grant IDs."""
    headers = [
        "grant_id=2c2e3e9b-5c8f-48c2-bab1-44f7d53f8646; HttpOnly; Max-Age=3600; SameSite=Strict"
    ]

    assert normalized_set_cookie(headers) == [
        'grant_id="<grant-id>"; HttpOnly; Max-Age=3600; SameSite=Strict'
    ]
