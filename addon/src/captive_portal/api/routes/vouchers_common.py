# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Shared helpers for voucher admin UI routes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, NamedTuple

from fastapi.responses import RedirectResponse

from captive_portal.api.routes.admin_redirects import safe_admin_redirect


def parse_vlan_form_input(raw: str | None) -> list[int] | None:
    """Parse comma-separated VLAN IDs from form input.

    Args:
        raw: Raw form input string (e.g. "50, 51, 52") or None.

    Returns:
        Sorted list of valid VLAN IDs, or None if input is empty.

    Raises:
        ValueError: If any VLAN ID is invalid.
    """
    if not raw or not str(raw).strip():
        return None
    vlans = sorted(set(int(v.strip()) for v in str(raw).split(",") if v.strip()))
    for vid in vlans:
        if vid < 1 or vid > 4094:
            raise ValueError(f"Invalid VLAN ID: {vid}")
    return vlans


class VoucherActions(NamedTuple):
    """Pre-computed action eligibility for a voucher."""

    can_revoke: bool
    can_delete: bool


@dataclass
class BulkResult:
    """Summary of a bulk operation outcome."""

    action: str
    success_count: int = 0
    skip_reasons: dict[str, int] = field(default_factory=dict)


def format_bulk_message(result: BulkResult) -> tuple[str, str]:
    """Format bulk operation result into feedback message and query key.

    Args:
        result: Bulk operation summary.

    Returns:
        Tuple of message text and query parameter key.
    """
    total_skipped = sum(result.skip_reasons.values())

    if result.success_count > 0 and total_skipped == 0:
        msg = f"{result.action.title()} {result.success_count} vouchers successfully"
        return msg, "success"
    if result.success_count > 0 and total_skipped > 0:
        skip_parts = [f"{count} {reason}" for reason, count in result.skip_reasons.items()]
        skip_detail = ", ".join(skip_parts)
        msg = (
            f"{result.action.title()} {result.success_count} vouchers, "
            f"skipped {total_skipped} ({skip_detail})"
        )
        return msg, "success"

    skip_parts = [f"{count} {reason}" for reason, count in result.skip_reasons.items()]
    skip_detail = ", ".join(skip_parts)
    msg = f"No vouchers {result.action} — {total_skipped} skipped ({skip_detail})"
    return msg, "error"


@dataclass
class BulkCreateParams:
    """Parsed and validated parameters for bulk voucher creation."""

    count: int
    duration: int
    max_devices: int
    allowed_vlans: list[int] | None
    booking_ref: str | None


def form_error_redirect(root: str, message: str) -> RedirectResponse:
    """Build a voucher form error redirect with an existing encoded message.

    Args:
        root: ASGI root path prefix.
        message: Query string message component.

    Returns:
        303 redirect response.
    """
    return safe_admin_redirect(root, f"/admin/vouchers/?error={message}")


def parse_bulk_create_form(
    form: Any,
    root: str,
) -> BulkCreateParams | RedirectResponse:
    """Parse and validate bulk-create form fields.

    Args:
        form: Submitted form data.
        root: Root path prefix for redirect URLs.

    Returns:
        Parsed parameters or a redirect response on validation error.
    """
    count_raw = form.get("count", "")
    try:
        count = int(count_raw)
    except (ValueError, TypeError):
        return form_error_redirect(root, "Count+must+be+a+positive+integer")
    if count < 1 or count > 100:
        return form_error_redirect(root, "Count+must+be+between+1+and+100")

    duration_raw = form.get("duration_minutes", "")
    try:
        duration = int(duration_raw)
    except (ValueError, TypeError):
        return form_error_redirect(root, "Duration+must+be+between+1+and+43200+minutes")
    if duration < 1 or duration > 43200:
        return form_error_redirect(root, "Duration+must+be+between+1+and+43200+minutes")

    max_devices_raw = form.get("max_devices", "1")
    try:
        max_devices = int(max_devices_raw)
    except (ValueError, TypeError):
        return form_error_redirect(root, "Max+devices+must+be+a+positive+integer")
    if max_devices < 1:
        return form_error_redirect(root, "Max+devices+must+be+at+least+1")

    allowed_vlans_raw = form.get("allowed_vlans", "")
    try:
        parsed_vlans = parse_vlan_form_input(str(allowed_vlans_raw) if allowed_vlans_raw else None)
    except ValueError:
        return form_error_redirect(root, "Invalid+VLAN+input")

    booking_ref_raw = form.get("booking_ref", "")
    booking_ref = str(booking_ref_raw).strip() or None if booking_ref_raw else None
    if booking_ref and len(booking_ref) > 128:
        return form_error_redirect(root, "Booking+reference+must+be+128+characters+or+less")

    return BulkCreateParams(
        count=count,
        duration=duration,
        max_devices=max_devices,
        allowed_vlans=parsed_vlans,
        booking_ref=booking_ref,
    )
