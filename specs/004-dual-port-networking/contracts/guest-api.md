SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Guest Listener API Contract

**Feature**: 004-dual-port-networking
**Listener**: Guest (`captive-portal-guest`, port 8099)
**Date**: 2025-07-15

## Overview

This document defines the HTTP contract for the guest-facing listener.  This
listener is directly accessible on the local network (no HA ingress proxy).
Only the endpoints listed below are available.  All other paths return
`404 Not Found`.

---

## Captive Portal Detection Endpoints

These endpoints are probed by operating systems to detect captive portals.
They MUST redirect to the guest authorization page.

### Android Detection

```
GET /generate_204
GET /gen_204
```

**Response**: `302 Found`
**Location**: `{guest_external_url}/guest/authorize` (or `/guest/authorize` if
external URL is not configured)

### Windows Detection

```
GET /connecttest.txt
GET /ncsi.txt
```

**Response**: `302 Found`
**Location**: `{guest_external_url}/guest/authorize` (or `/guest/authorize` if
external URL is not configured)

### Apple iOS/macOS Detection

```
GET /hotspot-detect.html
GET /library/test/success.html
```

**Response**: `302 Found`
**Location**: `{guest_external_url}/guest/authorize` (or `/guest/authorize` if
external URL is not configured)

### Firefox Detection

```
GET /success.txt
```

**Response**: `302 Found`
**Location**: `{guest_external_url}/guest/authorize` (or `/guest/authorize` if
external URL is not configured)

---

## Guest Authorization Endpoints

### Show Authorization Form

```
GET /guest/authorize
```

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `mac` | string | No | Pre-filled MAC address from WiFi controller |
| `error` | string | No | Error message to display |

**Response**: `200 OK`
**Content-Type**: `text/html`
**Body**: HTML authorization form with CSRF token.
**Cookies Set**: `guest_csrftoken` (CSRF double-submit cookie)

### Submit Authorization

```
POST /guest/authorize
```

**Content-Type**: `application/x-www-form-urlencoded`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `code` | string | Yes | Booking code or voucher code |
| `mac_address` | string | No | Client MAC address |
| `csrf_token` | string | Yes | CSRF token from form |

**Success Response**: `303 See Other`
**Location**: `/guest/success`

**Rate Limited Response**: `429 Too Many Requests`
**Headers**: `Retry-After: <seconds>`

**Error Response**: `303 See Other`
**Location**: `/guest/authorize?error=<message>`

### Success Page

```
GET /guest/success
```

**Response**: `200 OK`
**Content-Type**: `text/html`
**Body**: HTML welcome/success page confirming authorization.

### Error Page

```
GET /guest/error
```

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `message` | string | No | Error message to display |

**Response**: `200 OK`
**Content-Type**: `text/html`

---

## Guest Booking API

### Authorize via Booking Code (JSON API)

```
POST /api/guest/authorize
```

**Content-Type**: `application/json`

```json
{
  "booking_code": "string",
  "mac_address": "string (optional)"
}
```

**Success Response**: `200 OK`

```json
{
  "grant_id": "uuid",
  "status": "active",
  "expires_at": "ISO-8601 datetime",
  "message": "Access granted"
}
```

**Error Responses**:

| Status | Condition |
|--------|-----------|
| `404 Not Found` | Booking code not found |
| `409 Conflict` | Duplicate grant for this booking |
| `422 Unprocessable Entity` | Invalid input |
| `429 Too Many Requests` | Rate limit exceeded |

---

## Health Endpoints

### General Health

```
GET /api/health
```

**Response**: `200 OK`

```json
{
  "status": "ok",
  "timestamp": "ISO-8601 datetime"
}
```

### Readiness Probe

```
GET /api/ready
```

**Response (healthy)**: `200 OK`

```json
{
  "status": "ok",
  "timestamp": "ISO-8601 datetime",
  "checks": {
    "database": "ok"
  }
}
```

**Response (degraded)**: `503 Service Unavailable`

```json
{
  "status": "degraded",
  "timestamp": "ISO-8601 datetime",
  "checks": {
    "database": "unavailable"
  }
}
```

### Liveness Probe

```
GET /api/live
```

**Response**: `200 OK`

```json
{
  "status": "ok",
  "timestamp": "ISO-8601 datetime"
}
```

---

## Static Assets

```
GET /static/themes/{path}
```

**Response**: Static file (CSS, images, fonts) for guest portal theming.

---

## Root Redirect

```
GET /
```

**Response**: `303 See Other`
**Location**: `/guest/authorize`

---

## Security Headers (all responses)

| Header | Value |
|--------|-------|
| `X-Frame-Options` | `DENY` |
| `X-Content-Type-Options` | `nosniff` |
| `X-XSS-Protection` | `1; mode=block` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Content-Security-Policy` | `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; frame-ancestors 'none'; object-src 'none'` |

---

## Endpoints NOT Available on Guest Listener

The following endpoints return `404 Not Found` on the guest port.  They are
served exclusively on the ingress listener (port 8080).

| Path Pattern | Category |
|-------------|----------|
| `/api/admin/*` | Admin authentication |
| `/api/grants/*` | Grant management |
| `/api/vouchers/*` | Voucher management |
| `/api/portal/*` | Portal configuration |
| `/api/audit/*` | Audit configuration |
| `/api/integrations/*` | Integration management |
| `/admin/*` | Admin UI pages |
| `/grants` | Grant listing (placeholder) |

These routes are not registered in the guest app — they are absent from the
routing table entirely, producing standard FastAPI 404 responses.
