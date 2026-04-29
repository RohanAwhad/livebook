"""Fixtures for integration tests — spins up a real Jupyter server."""

import socket
import subprocess
import sys
import time

import httpx
import pytest

from livebook import JupyterConnection

TOKEN = "test-token-integration"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def jupyter_server():
    """Start a real Jupyter server for the test session, yield (url, token), then kill it."""
    port = _free_port()
    url = f"http://localhost:{port}"

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "jupyter_server",
            f"--port={port}",
            "--no-browser",
            f"--IdentityProvider.token={TOKEN}",
            "--ServerApp.disable_check_xsrf=True",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # Wait for server to be ready (up to 30s)
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            resp = httpx.get(
                f"{url}/api/status",
                headers={"Authorization": f"token {TOKEN}"},
            )
            if resp.status_code == 200:
                break
        except httpx.ConnectError:
            pass
        time.sleep(0.5)
    else:
        proc.kill()
        stdout = proc.stdout.read().decode() if proc.stdout else ""
        raise RuntimeError(f"Jupyter server failed to start:\n{stdout}")

    yield url, TOKEN

    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="session")
def conn(jupyter_server):
    """A JupyterConnection connected to the test server."""
    url, token = jupyter_server
    return JupyterConnection(url=url, token=token)


@pytest.fixture
def remote_notebooks(conn):
    """Track remote notebook paths created during a test, delete them on teardown."""
    paths: list[str] = []
    yield paths
    for path in paths:
        try:
            conn._client.delete(f"/api/contents/{path}")
        except Exception:
            pass
