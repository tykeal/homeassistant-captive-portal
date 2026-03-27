SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# captive-portal Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-03-27

## Active Technologies
- Python 3.12+ (runtime: Python 3.13 from HA base image) + FastAPI, Uvicorn, SQLModel, Pydantic, Jinja2, Argon2-cffi, HTTPX, passlib (003-addon-structure-refactor)
- SQLite via SQLModel (unchanged by this feature) (003-addon-structure-refactor)
- Python 3.12+ (type-annotated, mypy-enforced) + FastAPI, Uvicorn, SQLModel, Pydantic, Jinja2, s6-overlay (from HA base image) (004-dual-port-networking)
- SQLite via SQLModel ORM (`/data/captive_portal.db`) (004-dual-port-networking)
- Python 3.12+ (strict mypy, full type annotations) + FastAPI, Jinja2, SQLModel (SQLAlchemy + Pydantic), python-multipart (005-admin-ui-pages)
- SQLite via SQLModel ORM (existing `persistence/database.py` engine) (005-admin-ui-pages)
- Python 3.12+ (strict mypy, full type annotations) + FastAPI 0.100+, Jinja2, SQLModel (SQLAlchemy + Pydantic), HTTPX (async HTTP client for HA REST API), python-multipart (006-integrations-auto-detect)

- Python 3.12+ (per `pyproject.toml` `requires-python = ">=3.12"`) + FastAPI, uvicorn\[standard\], SQLModel, Jinja2, pydantic, argon2-cffi, httpx, passlib, python-multipart, email-validator (002-addon-app-wiring)

## Project Structure

```text
addon/src/
src/
tests/
```

## Commands

```bash
uv run pytest
uv run ruff check .
uv run mypy addon/src/captive_portal
```

## Code Style

Python 3.12+ (per `pyproject.toml` `requires-python = ">=3.12"`): Follow standard conventions

## Recent Changes
- 007-voucher-management: Added Python 3.12+ (strict mypy, full type annotations) + FastAPI 0.100+, Jinja2, SQLModel (SQLAlchemy + Pydantic), python-multipart
- 006-integrations-auto-detect: Added Python 3.12+ (strict mypy, full type annotations) + FastAPI 0.100+, Jinja2, SQLModel (SQLAlchemy + Pydantic), HTTPX (async HTTP client for HA REST API), python-multipart
- 005-admin-ui-pages: Added Python 3.12+ (strict mypy, full type annotations) + FastAPI 0.100+, Jinja2, SQLModel (SQLAlchemy + Pydantic), python-multipart
- 004-dual-port-networking: Added Python 3.12+ (type-annotated, mypy-enforced) + FastAPI, Uvicorn, SQLModel, Pydantic, Jinja2, s6-overlay (from HA base image)


<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
