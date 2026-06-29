# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Performance tests for guest error sanitization helpers."""

from __future__ import annotations

import time

import pytest

from captive_portal.api.routes.guest_authorization.errors import (
    _strip_html_tags,
    sanitize_error_message,
)


@pytest.mark.performance
def test_sanitize_error_message_handles_pathological_input_promptly() -> None:
    """Long tag-like guest errors stay within the promptness budget."""
    message = ("<" * 50_000) + ("tag>" * 50_000)
    long_tag = "prefix" + ("<" * 50_000) + ">" + "suffix"

    start = time.perf_counter()
    sanitized = sanitize_error_message(message)
    stripped = _strip_html_tags(long_tag)
    elapsed = time.perf_counter() - start

    assert sanitized == ("<" * 500) + "..."
    assert stripped == "prefixsuffix"
    assert elapsed < 1.0
