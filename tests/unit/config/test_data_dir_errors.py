# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test error handling for data directory issues."""

from __future__ import annotations

import os
import tempfile

import pytest

from captive_portal.config.settings import AppSettings


def test_nonexistent_db_parent_directory_raises() -> None:
    """Load should raise when db_path parent directory does not exist."""
    with pytest.raises(RuntimeError, match="does not exist"):
        AppSettings.load_and_validate(db_path="/nonexistent/path/db.sqlite")


def test_unwritable_db_parent_directory_raises() -> None:
    """Load should raise when db_path parent directory is not writable."""
    # Create a read-only directory
    with tempfile.TemporaryDirectory() as tmpdir:
        readonly_dir = os.path.join(tmpdir, "readonly")
        os.makedirs(readonly_dir)
        os.chmod(readonly_dir, 0o444)

        try:
            with pytest.raises(RuntimeError, match="not writable"):
                AppSettings.load_and_validate(db_path=os.path.join(readonly_dir, "db.sqlite"))
        finally:
            # Restore permissions for cleanup
            os.chmod(readonly_dir, 0o755)


def test_valid_db_path_does_not_raise() -> None:
    """Load should not raise for a valid writable db_path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        # Should not raise
        AppSettings.load_and_validate(db_path=db_path)
