# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Helpers for inspecting FastAPI routes in tests."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute


def iter_api_routes(app: FastAPI) -> Iterator[APIRoute]:
    """Yield all API routes registered on an application.

    Args:
        app: FastAPI application to inspect.

    Yields:
        Concrete APIRoute entries, including routes stored inside
        FastAPI's lazy included-router wrappers.
    """
    yield from _iter_api_routes(app.routes)


def route_paths(app: FastAPI) -> set[str]:
    """Return all concrete route paths registered on an application.

    Args:
        app: FastAPI application to inspect.

    Returns:
        Set of concrete APIRoute paths.
    """
    return {route.path for route in iter_api_routes(app)}


def _iter_api_routes(routes: Iterable[Any]) -> Iterator[APIRoute]:
    """Recursively yield concrete APIRoute objects from route containers.

    Args:
        routes: Route objects from a FastAPI application or router.

    Yields:
        Concrete APIRoute entries.
    """
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
            continue

        original_router = getattr(route, "original_router", None)
        nested_routes = getattr(original_router, "routes", None)
        if isinstance(nested_routes, Iterable):
            yield from _iter_api_routes(nested_routes)
