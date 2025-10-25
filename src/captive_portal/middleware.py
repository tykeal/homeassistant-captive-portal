# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""RBAC enforcement dependency placeholder.
Actual integration will attach roles to request (e.g., session) later.
"""
from __future__ import annotations
from fastapi import HTTPException, Request
from .security import is_allowed  # type: ignore  # path corrected by package layout

# Simple stub: role passed via header X-Role for early tests
DEFAULT_ACTION_HEADER = "X-Action"
async def rbac_enforcer(request: Request, action: str | None = None) -> None:
    if action is None:
        action = request.headers.get(DEFAULT_ACTION_HEADER, "")
    role = request.headers.get("X-Role", "")
    if not is_allowed(role, action):
        raise HTTPException(status_code=403, detail={"error": "forbidden", "code": "RBAC_FORBIDDEN"})
