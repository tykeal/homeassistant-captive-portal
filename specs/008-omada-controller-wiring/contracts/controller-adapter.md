SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Contract: Controller Adapter Interface

**Feature**: 008-omada-controller-wiring
**Date**: 2025-07-11
**Type**: Internal service interface (Python async adapter)

## Overview

The `OmadaAdapter` provides the contract between the captive portal application (route handlers) and the TP-Link Omada controller API. Route handlers call adapter methods; the adapter translates to controller-specific HTTP payloads via `OmadaClient`.

This contract documents the interface that the wiring layer depends on. The adapter and client implementations are **existing and stable** — this document captures the contract for test validation purposes.

## Interface: OmadaAdapter

### `authorize(mac, expires_at, upload_limit_kbps?, download_limit_kbps?) → dict`

**Purpose**: Authorize a guest device on the controller.

**Input**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `mac` | `str` | Yes | Device MAC (AA:BB:CC:DD:EE:FF format) |
| `expires_at` | `datetime` | Yes | Grant expiration (UTC) |
| `upload_limit_kbps` | `int` | No (default: 0) | Upload bandwidth limit (0 = unlimited) |
| `download_limit_kbps` | `int` | No (default: 0) | Download bandwidth limit (0 = unlimited) |

**Output** (success):
```json
{
  "grant_id": "string (controller-assigned, or MAC as fallback)",
  "status": "active | pending",
  "mac": "AA:BB:CC:DD:EE:FF"
}
```

**Controller payload sent**:
```json
{
  "clientMac": "AA:BB:CC:DD:EE:FF",
  "site": "Default",
  "time": 1720000000000000,
  "authType": 4,
  "upKbps": 0,
  "downKbps": 0
}
```

**Endpoint**: `POST /extportal/auth`

**Error behavior**:
| Condition | Exception | Retried? |
|-----------|-----------|----------|
| Connection error | `OmadaRetryExhaustedError` | Yes (up to 4 attempts) |
| Timeout | `OmadaRetryExhaustedError` | Yes (up to 4 attempts) |
| HTTP 4xx | `OmadaClientError` | No |
| HTTP 5xx | `OmadaRetryExhaustedError` | Yes (up to 4 attempts) |
| Omada errorCode >= 5000 | `OmadaClientError` / `OmadaRetryExhaustedError` | Yes |
| Omada errorCode < 5000, != 0 | `OmadaClientError` | No |

---

### `revoke(mac, grant_id?) → dict`

**Purpose**: Deauthorize a guest device on the controller.

**Input**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `mac` | `str` | Yes | Device MAC (AA:BB:CC:DD:EE:FF format) |
| `grant_id` | `str | None` | No | Unused (signature compatibility) |

**Output** (success):
```json
{
  "success": true,
  "mac": "AA:BB:CC:DD:EE:FF"
}
```

**Output** (already revoked — treated as success):
```json
{
  "success": true,
  "mac": "AA:BB:CC:DD:EE:FF",
  "note": "Already revoked"
}
```

**Controller payload sent**:
```json
{
  "clientMac": "AA:BB:CC:DD:EE:FF",
  "site": "Default"
}
```

**Endpoint**: `POST /extportal/revoke`

**Error behavior**: Same retry logic as `authorize`. HTTP 404 is treated as success (idempotent revocation).

---

## Interface: OmadaClient

### Lifecycle Contract

```
OmadaClient(base_url, controller_id, username, password, verify_ssl, timeout)
    ↓ Construction: stores config. NO network I/O.
    ↓
async with client:   (enters __aenter__)
    ↓ Creates httpx.AsyncClient
    ↓ Calls _authenticate() → login, extract CSRF token + session cookie
    ↓ Client is now "active"
    ↓
    client.post_with_retry(endpoint, payload)
    ↓ Uses active httpx client with CSRF header
    ↓ Retries with exponential backoff [1s, 2s, 4s, 8s]
    ↓
(exits __aexit__)
    ↓ Closes httpx.AsyncClient
```

### Retry Backoff Schedule

| Attempt | Delay Before Retry |
|---------|-------------------|
| 1 → 2 | 1,000 ms |
| 2 → 3 | 2,000 ms |
| 3 → 4 | 4,000 ms |
| 4 → fail | 8,000 ms |

Maximum total wait: 15 seconds (excludes request time).

---

## Wiring Layer Contract

### app.state Attributes

Route handlers access the adapter via FastAPI dependency injection from `request.app.state`:

| Attribute | Type | Populated When | Value When Not Configured |
|-----------|------|----------------|--------------------------|
| `omada_client` | `OmadaClient | None` | Startup, if `omada_controller_url` non-empty | `None` |
| `omada_adapter` | `OmadaAdapter | None` | Startup, if `omada_controller_url` non-empty | `None` |

### Authorization Wiring (guest_portal.py)

```
Grant created (PENDING)
    ↓
adapter = get_omada_adapter(request)
    ↓
if adapter is None:
    grant.status = ACTIVE  (no controller)
else:
    try:
        async with adapter.client:
            result = await adapter.authorize(mac, grant.end_utc)
        grant.status = ACTIVE
        grant.controller_grant_id = result["grant_id"]
    except OmadaClientError:
        grant.status = FAILED
        → log error, show user message
```

### Revocation Wiring (grants.py)

```
Grant revoked in DB (REVOKED)
    ↓
adapter = get_omada_adapter(request)
    ↓
if adapter is not None and grant.mac:
    try:
        async with adapter.client:
            await adapter.revoke(grant.mac)
    except OmadaClientError:
        → log error, inform admin of partial failure
        (DB revocation still committed)
```
