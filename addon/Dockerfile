# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM ${BUILD_FROM}

RUN apk add --no-cache python3

# Install uv for fast Python package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

ENV VIRTUAL_ENV=/opt/venv
RUN uv venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install the captive_portal package.
# Build context is addon/ — source lives here alongside the Dockerfile.
COPY pyproject.toml README.md /app/
COPY src/ /app/src/

RUN uv pip install --no-cache /app

# s6-overlay service definitions and rootfs overlay
COPY rootfs /

EXPOSE 8080
