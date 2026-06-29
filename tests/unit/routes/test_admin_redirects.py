# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for safe admin redirect helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from captive_portal.api.routes.admin_redirects import (
    admin_redirect_url,
    safe_admin_redirect,
    sanitize_admin_root_path,
)


class TestSanitizeAdminRootPath:
    """Coverage for root path sanitization decisions."""

    def test_ingress_root_path_is_preserved(self) -> None:
        """A normal Home Assistant ingress root path should be preserved."""
        assert (
            sanitize_admin_root_path("/api/hassio_ingress/abc123") == "/api/hassio_ingress/abc123"
        )

    def test_trailing_slash_is_normalized(self) -> None:
        """A valid root path with a trailing slash should not double slash."""
        assert sanitize_admin_root_path("/api/hassio_ingress/abc123/") == (
            "/api/hassio_ingress/abc123"
        )

    def test_relative_root_path_is_made_internal(self) -> None:
        """A relative root path should be normalized to an internal path."""
        assert sanitize_admin_root_path("api/hassio_ingress/abc123") == (
            "/api/hassio_ingress/abc123"
        )

    @pytest.mark.parametrize("root_path", ["", "/", None])
    def test_empty_root_paths_are_neutral(self, root_path: object) -> None:
        """Empty, root-only, and non-string values should become empty."""
        assert sanitize_admin_root_path(root_path) == ""

    @pytest.mark.parametrize(
        "root_path",
        [
            "//evil.example",
            "https://evil.example",
            "/api/hassio_ingress/abc123\r\nLocation: https://evil.example",
            r"/api\hassio_ingress\abc123",
        ],
    )
    def test_malicious_root_paths_are_neutralized(self, root_path: str) -> None:
        """Malicious root path values should be removed."""
        assert sanitize_admin_root_path(root_path) == ""


class TestSafeAdminRedirect:
    """Coverage for redirect URL construction."""

    def test_redirect_preserves_ingress_prefix_and_query(self) -> None:
        """Redirects should preserve valid prefixes and existing query text."""
        response = safe_admin_redirect(
            "/api/hassio_ingress/abc123",
            "/admin/vouchers/?success=Voucher+created+successfully",
        )
        assert response.status_code == 303
        assert response.headers["location"] == (
            "/api/hassio_ingress/abc123/admin/vouchers/?success=Voucher+created+successfully"
        )

    @pytest.mark.parametrize(
        "root_path",
        ["//evil.example", "https://evil.example", "line\r\nbreak", r"bad\path"],
    )
    def test_redirect_stays_internal_for_malicious_root_path(self, root_path: str) -> None:
        """Malicious prefixes should not make redirects leave admin paths."""
        assert admin_redirect_url(root_path, "/admin/login") == "/admin/login"

    def test_non_admin_paths_are_rejected(self) -> None:
        """The helper should only build redirects to fixed admin paths."""
        with pytest.raises(ValueError, match="admin_path"):
            admin_redirect_url("/api/hassio_ingress/abc123", "/guest/authorize")


def test_admin_routes_do_not_concatenate_root_path_into_admin_redirects() -> None:
    """Admin route modules should use the shared redirect helper."""
    repo_root = Path(__file__).resolve().parents[3]
    routes_dir = repo_root / "addon" / "src" / "captive_portal" / "api" / "routes"
    for route_file in routes_dir.glob("*.py"):
        content = route_file.read_text(encoding="utf-8")
        assert 'f"{root}/admin' not in content, route_file.name
        assert 'f"{redirect_base}' not in content, route_file.name
