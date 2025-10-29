# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Redirect URL validator to prevent open redirect vulnerabilities."""

from urllib.parse import urlparse


class RedirectValidator:
    """
    Validates redirect URLs to prevent open redirect attacks.

    Allows relative URLs and whitelisted domains only.
    Blocks dangerous protocols (javascript, data, etc.)

    Attributes:
        allowed_domains: Set of whitelisted domain names
    """

    def __init__(self, allowed_domains: list[str] | None = None) -> None:
        """
        Initialize validator.

        Args:
            allowed_domains: List of allowed domain names (optional)
        """
        self.allowed_domains = set(allowed_domains) if allowed_domains else set()

    def is_safe(self, url: str) -> bool:
        """
        Check if redirect URL is safe.

        Args:
            url: The URL to validate

        Returns:
            True if safe to redirect, False otherwise
        """
        if not url:
            return False

        # Parse URL
        parsed = urlparse(url)

        # Block dangerous protocols
        if parsed.scheme.lower() in ["javascript", "data", "vbscript", "file"]:
            return False

        # Allow relative URLs (no scheme or netloc)
        if not parsed.scheme and not parsed.netloc:
            return True

        # Allow only http/https protocols
        if parsed.scheme and parsed.scheme.lower() not in ["http", "https"]:
            return False

        # If we have a domain, check whitelist
        if parsed.netloc:
            if not self.allowed_domains:
                # No whitelist configured - block external redirects
                return False

            # Check if domain is in whitelist
            domain = parsed.netloc.lower()
            # Strip port if present
            domain = domain.split(":")[0]

            return domain in self.allowed_domains

        return True
