# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""RBAC allow path tests covering grants list & health endpoints.

Each test includes a docstring so interrogate counts it toward coverage.
"""

import pytest
from fastapi.testclient import TestClient
from typing import List, Tuple
from captive_portal.app import create_app

app = create_app()
client = TestClient(app)


ALLOWED: List[Tuple[str, int]] = [("operator", 200), ("auditor", 200), ("admin", 200)]


@pytest.mark.parametrize("role,status", ALLOWED)
def test_grants_list_allow(role: str, status: int) -> None:
    """Allowed roles get 200 with empty grants list placeholder."""
    r = client.get("/grants", headers={"X-Role": role})
    assert r.status_code == status
    assert r.json()["items"] == []


def test_health_allows_viewer() -> None:
    """Viewer role allowed to read health endpoint."""
    r = client.get("/health", headers={"X-Role": "viewer"})
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
