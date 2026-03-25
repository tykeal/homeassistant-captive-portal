# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM ${BUILD_FROM}

# NOTE: requires-python >= 3.13 in pyproject.toml. The default HA base
# image ships Python 3.12; a custom base image or version adjustment
# is needed for production builds.
RUN apk add --no-cache python3 py3-pip bash

WORKDIR /app

# Use a venv to avoid PEP 668 externally-managed-environment error
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Copy project files and install the full captive_portal package.
# NOTE: Build context must be the repository root (not addon/).
# For HA addon store distribution, use a pre-built image tag in
# config.json or adjust CI to set the appropriate build context.
COPY pyproject.toml /app/
COPY README.md /app/
COPY src/ /app/src/

RUN "$VIRTUAL_ENV/bin/python" -m pip install --no-cache-dir /app

COPY addon/rootfs /

EXPOSE 8080
CMD ["/usr/bin/run.sh"]
