SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Contract: Omada OpenAPI Requests and Responses

**Feature**: 013-omada-openapi-migration
**Date**: 2026-06-26
**Type**: External HTTP controller contract

## Common Rules

- Base URL is the configured Omada controller URL, for example
  `https://192.168.1.10:8043`.
- `verify_ssl` applies to every OpenAPI request.
- OpenAPI requests use `Authorization: AccessToken=<accessToken>`.
- `omadacId` and `siteId` are URL path parameters.
- Client MAC path parameters use uppercase dash format:
  `AA-BB-CC-DD-EE-FF`.
- Secrets, access tokens, and refresh tokens must never be logged.

## Controller ID Discovery

```http
GET /api/info
```

**Response**:

```json
{
  "errorCode": 0,
  "msg": "Success",
  "result": {
    "omadacId": "0123456789ab"
  }
}
```

Use the existing discovery behavior when `controller_id` is not configured.

## Token: Client Credentials

```http
POST /openapi/authorize/token?grant_type=client_credentials
Content-Type: application/json
```

**Request**:

```json
{
  "omadacId": "0123456789ab",
  "client_id": "configured-client-id",
  "client_secret": "configured-client-secret"
}
```

**Response**:

```json
{
  "errorCode": 0,
  "msg": "Success",
  "result": {
    "accessToken": "access-token",
    "refreshToken": "refresh-token",
    "expiresIn": 7200
  }
}
```

**Use**: Startup capability probe and initial OpenAPI authentication.

## Token: Refresh Token

```http
POST /openapi/authorize/token?grant_type=refresh_token&refreshToken=<refresh-token>
Content-Type: application/json
```

**Request**:

```json
{
  "omadacId": "0123456789ab",
  "client_id": "configured-client-id",
  "client_secret": "configured-client-secret"
}
```

**Response**: Same shape as client credentials.

**Use**: Proactive refresh before the access token expires, with a recommended
300-second safety margin.

## Site Discovery

```http
GET /openapi/v1/{omadacId}/sites?page=1&pageSize=100
Authorization: AccessToken=<accessToken>
```

**Response**:

```json
{
  "errorCode": 0,
  "msg": "Success",
  "result": {
    "data": [
      {
        "siteId": "site-id",
        "name": "Default"
      }
    ]
  }
}
```

**Use**: Page until a site with `name == site_name` is found or all pages are
exhausted, then cache `siteId` for the add-on run. Implementations may tolerate
`id` as a fallback key if a controller version uses that field name. Contract
tests should include a matching site beyond the first page when pagination
metadata is available.

## Hotspot Client Authorization

```http
POST /openapi/v1/{omadacId}/sites/{siteId}/hotspot/clients/{clientMac}/auth
Authorization: AccessToken=<accessToken>
```

**Request body**: None required by the official contract.

**Response**:

```json
{
  "errorCode": 0,
  "msg": ""
}
```

**Use**: Authorize a guest MAC. The add-on does not depend on per-call OpenAPI
duration fields; grant duration is enforced by add-on expiry processing and
`unauth`.

## Hotspot Client Deauthorization

```http
POST /openapi/v1/{omadacId}/sites/{siteId}/hotspot/clients/{clientMac}/unauth
Authorization: AccessToken=<accessToken>
```

**Request body**: None.

**Response**:

```json
{
  "errorCode": 0,
  "msg": ""
}
```

**Use**: Admin revoke, early revoke, and grant-expiry deauthorization.
Idempotent not-found/already-unauthorized responses should map to successful
revoke semantics when the controller indicates there is no active authorization
to remove.

## Authed Records Status

```http
GET /openapi/v1/{omadacId}/sites/{siteId}/hotspot/authed-records?page=1&pageSize=100
Authorization: AccessToken=<accessToken>
```

**Response**:

```json
{
  "errorCode": 0,
  "msg": "Success",
  "result": {
    "data": [
      {
        "id": "record-id",
        "mac": "AA-BB-CC-DD-EE-FF",
        "valid": true,
        "start": 1720000000,
        "end": 1720003600
      }
    ]
  }
}
```

**Use**: Best-effort status. Page until the normalized MAC is found or all pages
are exhausted. Use record presence plus `valid` to map authorization state. Use
a documented server-side filter only if the controller contract supports it.
The returned `end` timestamp is informational only; the add-on grant remains the
source of truth for access duration.

## Error Mapping

| Condition | Adapter behavior |
|-----------|------------------|
| HTTP 401/403 or OpenAPI token error | Authentication/configuration failure; forced OpenAPI startup fails, mid-run operation fails |
| HTTP 404 on token endpoint in `auto` mode | Probe failure; fallback to legacy only when legacy credentials are available |
| HTTP 429 or 5xx | Retry/backoff according to controller retry policy |
| `errorCode != 0` | Map to `OmadaClientError`-compatible controller error without secret values |
| Access token expired | Attempt refresh or full OpenAPI re-auth; do not switch backend mid-run |
