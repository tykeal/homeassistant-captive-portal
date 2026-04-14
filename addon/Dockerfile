# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.13-alpine3.21
FROM ${BUILD_FROM}

# Install uv for fast Python package management
COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /usr/local/bin/uv

# Allow injecting version when .git is unavailable (Docker context)
ARG SETUPTOOLS_SCM_PRETEND_VERSION="0.0.0.dev0"
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${SETUPTOOLS_SCM_PRETEND_VERSION}

WORKDIR /app

# Phase 1: Install dependencies only (cached when only source changes)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Phase 2: Copy source and install the project
COPY src/ ./src/
COPY README.md ./
RUN uv sync --frozen --no-dev

# Set Python path and runtime environment
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# s6-overlay service definitions and rootfs overlay
COPY rootfs /
RUN chmod +x /etc/s6-overlay/s6-rc.d/captive-portal/run && \
    chmod +x /etc/s6-overlay/s6-rc.d/captive-portal-guest/run

EXPOSE 8080
EXPOSE 8099
