# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""RBAC deny tests confirming forbidden responses for unauthorized roles.

Each test has a docstring for interrogate coverage.
"""

from fastapi.testclient import TestClient
from captive_portal.app import create_app

app = create_app()
client = TestClient(app)


def test_grants_list_denied_for_viewer() -> None:
    """Viewer role is forbidden from listing grants."""
    r = client.get("/grants", headers={"X-Role": "viewer"})
    assert r.status_code == 403
    body = r.json()
    assert body["detail"]["code"] == "RBAC_FORBIDDEN"


def test_grants_list_denied_no_role() -> None:
    """Absence of role header is forbidden."""
    r = client.get("/grants")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "RBAC_FORBIDDEN"
