# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for redirect whitelist (prevent open redirect)."""

from captive_portal.services.redirect_validator import RedirectValidator


class TestPostAuthRedirectWhitelist:
    """Test open redirect prevention."""

    def test_allow_relative_urls(self) -> None:
        """Relative URLs starting with / are allowed."""
        validator = RedirectValidator()

        assert validator.is_safe("/page")
        assert validator.is_safe("/admin/dashboard")
        assert validator.is_safe("/path/to/resource")

    def test_allow_whitelisted_domains(self) -> None:
        """Whitelisted domains are allowed."""
        validator = RedirectValidator(allowed_domains=["example.com", "trusted.com"])

        assert validator.is_safe("http://example.com/page")
        assert validator.is_safe("https://trusted.com/page")

    def test_block_non_whitelisted_domains(self) -> None:
        """Non-whitelisted domains are blocked."""
        validator = RedirectValidator(allowed_domains=["example.com"])

        assert not validator.is_safe("http://evil.com/page")
        assert not validator.is_safe("https://phishing.com/page")

    def test_block_javascript_protocol(self) -> None:
        """JavaScript protocol is blocked."""
        validator = RedirectValidator()

        assert not validator.is_safe("javascript:alert(1)")
        assert not validator.is_safe("JAVASCRIPT:alert(1)")

    def test_block_data_protocol(self) -> None:
        """Data protocol is blocked."""
        validator = RedirectValidator()

        assert not validator.is_safe("data:text/html,<script>alert(1)</script>")

    def test_block_protocol_relative_urls(self) -> None:
        """Protocol-relative URLs are blocked to prevent open redirect."""
        validator = RedirectValidator()

        assert not validator.is_safe("//evil.com/phishing")
        assert not validator.is_safe("//attacker.com")

    def test_block_triple_slash_urls(self) -> None:
        """Triple-slash URLs are blocked."""
        validator = RedirectValidator()

        assert not validator.is_safe("///etc/passwd")
        assert not validator.is_safe("////malicious.com")

    def test_block_backslash_bypass(self) -> None:
        """Backslash URL bypasses are normalized and validated."""
        validator = RedirectValidator()

        # Double backslash becomes // and is blocked
        assert not validator.is_safe("\\\\evil.com")
        # Single backslash becomes / which is a valid local path
        # This is acceptable since it resolves to a relative path on our server

    def test_block_relative_paths_not_starting_with_slash(self) -> None:
        """Relative paths not starting with / are blocked."""
        validator = RedirectValidator()

        assert not validator.is_safe("../other")
        assert not validator.is_safe("./page")
        assert not validator.is_safe("page")
