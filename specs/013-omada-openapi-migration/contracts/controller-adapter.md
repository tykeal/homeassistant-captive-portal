SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Contract: Omada Controller Adapter Protocol

**Feature**: 013-omada-openapi-migration
**Date**: 2026-06-26
**Type**: Internal Python async service interface

## Overview

`OmadaControllerAdapter` is the application-facing contract for Omada controller
operations. Guest authorization, admin revocation, grant-expiry
deauthorization, and best-effort status call this Protocol without knowing
whether the selected backend is OpenAPI or legacy.

Implementations:

- `OmadaLegacyAdapter`: existing hotspot/external portal behavior.
- `OmadaOpenApiAdapter`: documented OpenAPI behavior.

Callers must not access backend-specific clients, cookies, CSRF tokens, OpenAPI
tokens, or site-discovery state.

## Python Protocol

```python
from datetime import datetime
from typing import Any, Protocol


class OmadaControllerAdapter(Protocol):
    """Shared interface for TP-Link Omada controller backends."""

    async def authorize(
        self,
        mac: str,
        expires_at: datetime,
        upload_limit_kbps: int = 0,
        download_limit_kbps: int = 0,
        gateway_mac: str | None = None,
        ap_mac: str | None = None,
        ssid_name: str | None = None,
        radio_id: str | None = None,
        vid: str | None = None,
    ) -> dict[str, Any]:
        """Authorize a guest device by MAC."""

    async def revoke(
        self,
        mac: str,
        grant_id: str | None = None,
        gateway_mac: str | None = None,
        ap_mac: str | None = None,
        vid: str | None = None,
        ssid_name: str | None = None,
        radio_id: str | None = None,
    ) -> dict[str, Any]:
        """Deauthorize a guest device by MAC."""

    async def update(
        self,
        mac: str,
        expires_at: datetime,
        grant_id: str | None = None,
    ) -> dict[str, Any]:
        """Refresh or extend a controller authorization if supported."""

    async def get_status(self, mac: str) -> dict[str, Any]:
        """Return best-effort authorization status for a MAC."""
```

## `authorize(...) -> dict[str, Any]`

**Purpose**: Authorize a guest device on the selected Omada backend.

**Input**:

| Parameter | Type | Required | Backend behavior |
|-----------|------|----------|------------------|
| `mac` | `str` | Yes | Validated MAC from guest flow |
| `expires_at` | `datetime` | Yes | Legacy converts to `time`; OpenAPI ignores for request duration and relies on add-on expiry |
| `upload_limit_kbps` | `int` | No | Legacy sends when non-zero; OpenAPI does not depend on undocumented body fields |
| `download_limit_kbps` | `int` | No | Legacy sends when non-zero; OpenAPI does not depend on undocumented body fields |
| `gateway_mac`/`vid` | `str | None` | No | Legacy gateway auth context; OpenAPI ignores |
| `ap_mac`/`ssid_name`/`radio_id` | `str | None` | No | Legacy EAP auth context; OpenAPI ignores |

**Output**:

```json
{
  "grant_id": "controller identifier, auth record identifier, or MAC fallback",
  "status": "active",
  "mac": "AA:BB:CC:DD:EE:FF"
}
```

**Errors**: Raise the existing Omada controller exception types or subclasses
that route handlers already map to controller failure semantics. Do not expose
secrets or tokens in exception messages.

## `revoke(...) -> dict[str, Any]`

**Purpose**: Deauthorize a guest device for admin revoke, early revoke, or
grant-expiry processing.

**Input**: Same MAC and optional legacy context values as `authorize`.

**Output**:

```json
{
  "success": true,
  "mac": "AA:BB:CC:DD:EE:FF"
}
```

Already-deauthorized clients may be treated as success to preserve idempotent
admin/expiry behavior.

## `update(...) -> dict[str, Any]`

**Purpose**: Preserve the existing adapter surface for callers that refresh a
grant. Legacy may re-authorize. OpenAPI should either call `authorize` again or
return the current authorization mapping if no separate update is required by
current behavior.

**Duration rule**: `update` must not introduce dependency on undocumented
OpenAPI duration body fields. Add-on grant expiry remains authoritative.

## `get_status(mac) -> dict[str, Any]`

**Purpose**: Return equivalent best-effort status meaning across both backends.

**Output**:

```json
{
  "mac": "AA:BB:CC:DD:EE:FF",
  "authorized": true,
  "remaining_seconds": 0
}
```

`remaining_seconds` may be `0` or absent-equivalent when the controller does not
provide a reliable value. Callers must treat this as best-effort status, not the
source of truth for grant duration.

## Lifecycle Contract

- Adapter methods own any backend-specific HTTP client/session lifecycle.
- Route handlers and services do not use `async with adapter.client`.
- The startup factory stores the selected backend and immutable runtime
  configuration on app state; request dependencies create request-scoped
  adapters/clients from that selection.
- Legacy CSRF/cookie client state is never shared across concurrent requests.
- Shared OpenAPI token and site cache state, if used, is guarded by an
  `asyncio.Lock` so refresh and site discovery are concurrency-safe.
- The selected backend remains selected until app restart or explicit
  reconfiguration.
- Token refresh, site discovery, and legacy authentication are implementation
  details hidden behind this Protocol.
