# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration test for password masking in log output.

Validates that the Omada password never appears in any log output.
"""

from __future__ import annotations

import logging
import logging.handlers

from captive_portal.config.settings import AppSettings


class TestPasswordMasking:
    """Tests for password masking in log output."""

    def test_password_never_in_log_output(self) -> None:
        """Password value should never appear in log output."""

        test_password = "s3cret-p@ss!"
        settings = AppSettings(
            omada_controller_url="https://ctrl.local:8043",
            omada_username="user1",
            omada_password=test_password,
            omada_site_name="TestSite",
            omada_controller_id="ctrl-123",
            omada_verify_ssl=False,
        )

        test_logger = logging.getLogger("test_password_masking")
        handler = logging.handlers.MemoryHandler(capacity=1000)
        handler.setLevel(logging.DEBUG)
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.DEBUG)

        try:
            settings.log_effective(test_logger)

            for record in handler.buffer:
                formatted = handler.format(record)
                assert test_password not in formatted, f"Password found in log output: {formatted}"
                assert test_password not in record.getMessage(), (
                    f"Password found in log message: {record.getMessage()}"
                )

            # Verify "(set)" appears instead
            messages = [r.getMessage() for r in handler.buffer]
            all_text = " ".join(messages)
            assert "(set)" in all_text
        finally:
            test_logger.removeHandler(handler)

    def test_empty_password_shows_not_set(self) -> None:
        """Empty password should show '(not set)' in log."""
        settings = AppSettings(
            omada_password="",
        )

        test_logger = logging.getLogger("test_password_masking_empty")
        handler = logging.handlers.MemoryHandler(capacity=1000)
        handler.setLevel(logging.DEBUG)
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.DEBUG)

        try:
            settings.log_effective(test_logger)

            messages = [r.getMessage() for r in handler.buffer]
            all_text = " ".join(messages)
            assert "(not set)" in all_text
        finally:
            test_logger.removeHandler(handler)
