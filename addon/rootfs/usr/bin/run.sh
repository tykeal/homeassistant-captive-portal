#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
# Placeholder entrypoint for the captive portal addon.

exec python3 -c "
from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get('/health')
async def health():
    return {'status': 'ok'}

uvicorn.run(app, host='0.0.0.0', port=8080)
"
