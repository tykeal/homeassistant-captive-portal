# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM ${BUILD_FROM}

# Install python 3.13 (placeholder, base image may already include python)
RUN apk add --no-cache python3 py3-pip

# Copy app (placeholder minimal)
WORKDIR /app
COPY pyproject.toml README.md /app/

# Install deps via uv if available else pip
RUN pip install --no-cache-dir fastapi uvicorn[standard]

EXPOSE 8080
CMD ["python3","-c","import fastapi,uvicorn; from fastapi import FastAPI; app=FastAPI();\n@app.get('/health')\nasync def health(): return {'status':'ok'}; uvicorn.run(app,host='0.0.0.0',port=8080)"]
