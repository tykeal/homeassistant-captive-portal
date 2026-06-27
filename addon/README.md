<!-- SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org> -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Captive Portal – Home Assistant Add-on

Guest network captive portal integrating TP-Omada and Home Assistant.

See the [project README](../README.md) for full documentation.

## Omada OpenAPI backend

Existing deployments continue to use the legacy Omada hotspot/external portal API when no OpenAPI credentials are configured. To prefer the documented Omada OpenAPI, create an Omada OpenAPI app in **Settings → Platform Integration → Open API → New App**, then enter the Client ID, Client Secret, and Backend Mode on the add-on Omada settings page.

Backend modes are `auto` (default; probe OpenAPI and fall back to legacy), `openapi` (require OpenAPI and fail clearly if unavailable), and `legacy` (skip OpenAPI). OpenAPI secrets are encrypted at rest and are never displayed in logs or the UI. Restart the add-on after backend credential changes so the separate guest listener adopts the selected backend.

OpenAPI authorization is timer-only: configure the Omada hotspot portal profile duration longer than your longest add-on grant. The add-on expiry worker calls the selected backend to unauthorize clients when grants expire.
