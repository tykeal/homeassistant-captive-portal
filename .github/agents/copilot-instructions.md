SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# captive-portal Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-03-25

## Active Technologies
- Python 3.12+ (runtime: Python 3.13 from HA base image) + FastAPI, Uvicorn, SQLModel, Pydantic, Jinja2, Argon2-cffi, HTTPX, passlib (003-addon-structure-refactor)
- SQLite via SQLModel (unchanged by this feature) (003-addon-structure-refactor)

- Python 3.12+ (per `pyproject.toml` `requires-python = ">=3.12"`) + FastAPI, uvicorn\[standard\], SQLModel, Jinja2, pydantic, argon2-cffi, httpx, passlib, python-multipart, email-validator (002-addon-app-wiring)

## Project Structure

```text
src/
tests/
```

## Commands

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```

## Code Style

Python 3.12+ (per `pyproject.toml` `requires-python = ">=3.12"`): Follow standard conventions

## Recent Changes
- 003-addon-structure-refactor: Added Python 3.12+ (runtime: Python 3.13 from HA base image) + FastAPI, Uvicorn, SQLModel, Pydantic, Jinja2, Argon2-cffi, HTTPX, passlib

- 002-addon-app-wiring: Added Python 3.12+ (per `pyproject.toml` `requires-python = ">=3.12"`) + FastAPI, uvicorn\[standard\], SQLModel, Jinja2, pydantic, argon2-cffi, httpx, passlib, python-multipart, email-validator

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
