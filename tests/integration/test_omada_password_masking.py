# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration test for password masking in log output.

Validates that the HA token never appears in any log output, and
that secret fields are masked as "(set)" / "(not set)".
"""

from __future__ import annotations

import logging
import logging.handlers

from captive_portal.config.settings import AppSettings


class TestPasswordMasking:
    """Tests for ha_token masking in log output."""

    def test_token_never_in_log_output(self) -> None:
        """Token value should never appear in log output."""

        test_token = "sv-secret-token-xyz"
        settings = AppSettings(ha_token=test_token)

        test_logger = logging.getLogger("test_password_masking")
        handler = logging.handlers.MemoryHandler(capacity=1000)
        handler.setLevel(logging.DEBUG)
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.DEBUG)

        try:
            settings.log_effective(test_logger)

            for record in handler.buffer:
                formatted = handler.format(record)
                assert test_token not in formatted, f"Token found in log output: {formatted}"
                assert test_token not in record.getMessage(), (
                    f"Token found in log message: {record.getMessage()}"
                )

            # Verify "(set)" appears instead
            messages = [r.getMessage() for r in handler.buffer]
            all_text = " ".join(messages)
            assert "(set)" in all_text
        finally:
            test_logger.removeHandler(handler)

    def test_empty_token_shows_not_set(self) -> None:
        """Empty ha_token should show '(not set)' in log."""
        settings = AppSettings(ha_token="")

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
