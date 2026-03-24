# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM ${BUILD_FROM}

RUN apk add --no-cache python3 py3-pip

WORKDIR /app

# Use a venv to avoid PEP 668 externally-managed-environment error
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN "$VIRTUAL_ENV/bin/python" -m pip install --no-cache-dir fastapi uvicorn[standard]

EXPOSE 8080
CMD ["python3","-c","import fastapi,uvicorn; from fastapi import FastAPI; app=FastAPI();\n@app.get('/health')\nasync def health(): return {'status':'ok'}; uvicorn.run(app,host='0.0.0.0',port=8080)"]
