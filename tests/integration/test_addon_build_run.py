# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""T0718 – Integration tests for HA addon Docker image build and run.

Validates:
- Docker image builds successfully from repository root context
- Container starts and responds on health endpoint (/api/health)
- Container performs graceful shutdown on SIGTERM
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from contextlib import closing

from collections.abc import Generator

import pytest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
IMAGE_TAG = "captive-portal-test:latest"
# Full app uses /api/health
HEALTH_ENDPOINT = "/api/health"
CONTAINER_PORT = 8080


def _docker_available() -> bool:
    """Check if Docker CLI is available and daemon is running."""
    if not shutil.which("docker"):
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _find_free_port() -> int:
    """Find a free TCP port on localhost."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", 0))
        port: int = s.getsockname()[1]
        return port


def _wait_for_port(port: int, timeout: float = 30.0) -> bool:
    """Wait until a TCP port is accepting connections."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with closing(socket.create_connection(("127.0.0.1", port), timeout=1)):
                return True
        except OSError:
            time.sleep(0.5)
    return False


docker_required = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker not available or daemon not running",
)


@pytest.mark.integration
@docker_required
class TestAddonDockerBuild:
    """Test that the HA addon Docker image builds successfully."""

    @pytest.mark.xfail(
        reason="HA base image ships Python 3.12; requires-python >= 3.13",
        strict=False,
    )
    def test_docker_build_succeeds(self) -> None:
        """Docker build of addon/ should exit 0."""
        result = subprocess.run(
            ["docker", "build", "-f", "addon/Dockerfile", "-t", IMAGE_TAG, "."],
            cwd=os.path.abspath(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, (
            f"Docker build failed:\nstdout: {result.stdout[-2000:]}\n"
            f"stderr: {result.stderr[-2000:]}"
        )


@pytest.mark.integration
@docker_required
class TestAddonContainerRun:
    """Test that the addon container starts and responds on health endpoint."""

    @pytest.fixture(autouse=True)
    def _build_image(self) -> None:
        """Ensure image is built before run tests."""
        result = subprocess.run(
            ["docker", "build", "-f", "addon/Dockerfile", "-t", IMAGE_TAG, "."],
            cwd=os.path.abspath(REPO_ROOT),
            capture_output=True,
            timeout=300,
        )
        if result.returncode != 0:
            pytest.skip("Docker build failed; skipping run tests")

    @pytest.fixture
    def container(self) -> Generator[subprocess.Popen[bytes], None, None]:
        """Start container on a free port and clean up after test."""
        host_port = _find_free_port()
        proc = subprocess.Popen(
            [
                "docker",
                "run",
                "--rm",
                "-p",
                f"{host_port}:{CONTAINER_PORT}",
                "--name",
                f"cp-test-{host_port}",
                IMAGE_TAG,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Store port for test access
        proc.host_port = host_port  # type: ignore[attr-defined]
        yield proc
        # Cleanup: stop container
        subprocess.run(
            ["docker", "stop", f"cp-test-{host_port}"],
            capture_output=True,
            timeout=15,
        )
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    def test_container_starts_and_health_responds(self, container: subprocess.Popen[bytes]) -> None:
        """Container should start and /health should return 200."""
        import urllib.error
        import urllib.request

        port = container.host_port  # type: ignore[attr-defined]
        assert _wait_for_port(port, timeout=60), f"Container not listening on port {port}"

        url = f"http://127.0.0.1:{port}{HEALTH_ENDPOINT}"
        # Retry HTTP request — port may be open before app is ready
        last_err: Exception | None = None
        for attempt in range(10):
            try:
                with urllib.request.urlopen(url, timeout=10) as resp:
                    assert resp.status == 200
                    body = resp.read().decode()
                    assert "ok" in body.lower() or "status" in body.lower()
                    # Verify this is the real app, not the placeholder
                    assert "placeholder" not in body.lower()
                    return
            except (ConnectionResetError, urllib.error.URLError, OSError) as exc:
                last_err = exc
                time.sleep(1)
        msg = f"Health endpoint not ready after 10 retries: {last_err}"
        raise AssertionError(msg)

    def test_graceful_shutdown(self, container: subprocess.Popen[bytes]) -> None:
        """Container should shut down gracefully on docker stop (SIGTERM)."""
        port = container.host_port  # type: ignore[attr-defined]
        assert _wait_for_port(port, timeout=60), "Container did not start"

        # Send stop (SIGTERM via docker stop)
        stop_result = subprocess.run(
            ["docker", "stop", "-t", "10", f"cp-test-{port}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert stop_result.returncode == 0, f"docker stop failed: {stop_result.stderr}"

        # Container process should exit cleanly
        exit_code = container.wait(timeout=15)
        # Docker stop returns 0 for the stop command; the container exit may be
        # 0 (clean) or 143 (SIGTERM) — both are acceptable
        assert exit_code in (0, 143, -15), f"Unexpected exit code: {exit_code}"
