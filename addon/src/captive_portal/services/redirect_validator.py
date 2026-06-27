# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Redirect URL validator to prevent open redirect vulnerabilities."""

from dataclasses import dataclass
from unicodedata import normalize
from urllib.parse import SplitResult, unquote, urlparse, urlsplit

_GUEST_EXTERNAL_URL_ERROR = (
    "Guest external URL must be an HTTP or HTTPS URL with a host, and must not "
    "include a path, query, fragment, trailing slash, or control characters"
)


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

        # Block protocol-relative URLs (//evil.com)
        if url.startswith("//"):
            return False

        # Normalize backslashes to prevent bypass attempts
        url = url.replace("\\", "/")

        parsed = urlparse(url)

        # Block dangerous protocols
        if parsed.scheme.lower() in ["javascript", "data", "vbscript", "file"]:
            return False

        # Allow relative URLs (no scheme or netloc)
        if not parsed.scheme and not parsed.netloc:
            # Ensure it's a true relative path starting with /
            # Block protocol-relative and triple-slash attempts
            return url.startswith("/") and not url.startswith("//")

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


@dataclass(frozen=True)
class GuestExternalUrlValidationResult:
    """Result of guest external URL validation.

    Attributes:
        valid: Whether the submitted URL is safe to persist.
        normalized_url: Trimmed URL value safe to store when valid.
        error_message: User-facing error text when invalid.
    """

    valid: bool
    normalized_url: str
    error_message: str | None


class GuestExternalUrlValidator:
    """Validate guest portal external URLs before persistence."""

    @staticmethod
    def validate(url: str) -> GuestExternalUrlValidationResult:
        """Validate and normalize a guest external URL.

        Empty values are valid and clear the configured external URL.

        Args:
            url: Submitted guest external URL.

        Returns:
            Validation result with a normalized URL or error message.
        """
        normalized_url = url.strip()
        if normalized_url == "":
            return GuestExternalUrlValidationResult(
                valid=True,
                normalized_url="",
                error_message=None,
            )

        if (
            _contains_control_character(url)
            or _contains_control_character(unquote(normalized_url))
            or _contains_internal_whitespace(normalized_url)
        ):
            return _invalid_guest_external_url(normalized_url)

        try:
            parts = urlsplit(normalized_url)
            hostname = parts.hostname
            _ = parts.port
        except ValueError:
            return _invalid_guest_external_url(normalized_url)

        if hostname is None or not _guest_external_url_parts_valid(
            parts,
            normalized_url,
            hostname,
        ):
            return _invalid_guest_external_url(normalized_url)

        return GuestExternalUrlValidationResult(
            valid=True,
            normalized_url=normalized_url,
            error_message=None,
        )


def _guest_external_url_parts_valid(
    parts: SplitResult,
    normalized_url: str,
    hostname: str,
) -> bool:
    """Validate parsed guest external URL components.

    Args:
        parts: Parsed URL components.
        normalized_url: Trimmed URL value.
        hostname: Parsed hostname value.

    Returns:
        True when all URL components are safe to persist.
    """
    if parts.scheme.lower() not in {"http", "https"}:
        return False

    if parts.username is not None or parts.password is not None:
        return False

    if parts.query or parts.fragment or "?" in normalized_url or "#" in normalized_url:
        return False

    if parts.path:
        return False

    return _guest_external_url_netloc_valid(parts.netloc, hostname)


def _guest_external_url_netloc_valid(netloc: str, hostname: str) -> bool:
    """Validate guest external URL authority delimiters.

    Args:
        netloc: Parsed authority component.
        hostname: Parsed hostname value.

    Returns:
        True when decoded authority data contains no delimiter bypasses.
    """
    decoded_netloc = unquote(netloc)
    normalized_decoded_netloc = normalize("NFKC", decoded_netloc)
    if (decoded_netloc != netloc or normalized_decoded_netloc != decoded_netloc) and any(
        delimiter in normalized_decoded_netloc for delimiter in ":/?#[]@\\"
    ):
        return False

    try:
        idna_hostname = unquote(hostname).encode("idna").decode("ascii")
    except UnicodeError:
        return False

    return not (
        "/" in decoded_netloc
        or "\\" in decoded_netloc
        or "/" in idna_hostname
        or "\\" in idna_hostname
    )


def _contains_control_character(value: str) -> bool:
    """Return whether the value includes control characters.

    Args:
        value: String to scan.

    Returns:
        True when any character is a C0 or DEL control character.
    """
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _contains_internal_whitespace(value: str) -> bool:
    """Return whether the stripped value contains whitespace.

    Args:
        value: Stripped URL value to scan.

    Returns:
        True when whitespace remains inside the URL.
    """
    return any(character.isspace() for character in value)


def _invalid_guest_external_url(normalized_url: str) -> GuestExternalUrlValidationResult:
    """Build an invalid guest external URL result.

    Args:
        normalized_url: Trimmed URL value that failed validation.

    Returns:
        Validation result with the shared user-facing error message.
    """
    return GuestExternalUrlValidationResult(
        valid=False,
        normalized_url=normalized_url,
        error_message=_GUEST_EXTERNAL_URL_ERROR,
    )
