#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
# Entrypoint for the captive portal addon.
# Starts the real application via uvicorn with the create_app factory.

exec "$VIRTUAL_ENV/bin/python" -m uvicorn \
    captive_portal.app:create_app \
    --factory \
    --host 0.0.0.0 \
    --port 8080
