# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM ${BUILD_FROM}

RUN apk add --no-cache python3 py3-pip bash

WORKDIR /app

# Use a venv to avoid PEP 668 externally-managed-environment error
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Copy project files and install the full captive_portal package
COPY pyproject.toml /app/
COPY src/ /app/src/

RUN "$VIRTUAL_ENV/bin/python" -m pip install --no-cache-dir /app

COPY rootfs /

EXPOSE 8080
CMD ["/usr/bin/run.sh"]
