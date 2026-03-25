# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Unified code service for auto-detecting voucher vs booking codes."""

import re
from enum import Enum
from dataclasses import dataclass


class CodeType(str, Enum):
    """Type of authorization code."""

    VOUCHER = "voucher"
    BOOKING = "booking"
    INVALID = "invalid"


@dataclass
class CodeValidationResult:
    """Result of code validation."""

    code_type: CodeType
    normalized_code: str
    original_code: str


def detect_code_type(code: str) -> CodeType:
    r"""
    Detect whether code is a voucher or booking code.

    Voucher codes: Alphanumeric A-Z0-9, 4-24 chars
    Booking codes: Numeric-only (\d{4,}) or contains special chars/spaces
    Invalid: <4 or >24 chars, empty, whitespace-only

    Args:
        code: The authorization code to detect

    Returns:
        CodeType enum value
    """
    if not code or not code.strip():
        return CodeType.INVALID

    code = code.strip()

    if len(code) < 4 or len(code) > 24:
        return CodeType.INVALID

    # Check if it's purely alphanumeric (A-Z0-9)
    if re.match(r"^[A-Z0-9]+$", code, re.IGNORECASE):
        # If it's purely numeric and 4+ digits, it's a booking slot_code
        if re.match(r"^\d{4,}$", code):
            return CodeType.BOOKING
        # Otherwise it's a voucher
        return CodeType.VOUCHER

    # Contains special chars/spaces - treat as booking slot_name
    return CodeType.BOOKING


class UnifiedCodeService:
    """Service for validating and normalizing authorization codes."""

    async def validate_code(self, code: str) -> CodeValidationResult:
        """
        Validate and normalize authorization code.

        Args:
            code: The code to validate

        Returns:
            CodeValidationResult with type and normalized code

        Raises:
            ValueError: If code is invalid
        """
        code_type = detect_code_type(code)

        if code_type == CodeType.INVALID:
            raise ValueError("Invalid authorization code")

        # Normalize: uppercase for vouchers, preserve case for booking
        if code_type == CodeType.VOUCHER:
            normalized = code.strip().upper()
        else:
            normalized = code.strip()

        return CodeValidationResult(
            code_type=code_type, normalized_code=normalized, original_code=code
        )
