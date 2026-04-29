"""JupyterConnection: REST + WebSocket transport layer."""

from __future__ import annotations

import json
from typing import Any

import httpx
import websocket  # websocket-client

from ._proto import build_execute_request, collect_iopub_to_result
from .models import CellResult


class JupyterConnection:
    def __init__(self, url: str, token: str) -> None:
        self.url = url.rstrip("/")
        self.token = token
        headers = {}
        if token:
            headers["Authorization"] = f"token {token}"
        self._client = httpx.Client(base_url=self.url, headers=headers)
        self._ws_connections: dict[str, websocket.WebSocket] = {}
        self._fetch_xsrf()

    # --- Kernel lifecycle (REST) ---

    def start_kernel(self, name: str = "python3") -> str:
        """Start a kernel, return kernel_id."""
        resp = self._client.post("/api/kernels", json={"name": name})
        resp.raise_for_status()
        return resp.json()["id"]

    def stop_kernel(self, kernel_id: str) -> None:
        """Stop kernel and close its WebSocket if open."""
        self._close_ws(kernel_id)
        resp = self._client.delete(f"/api/kernels/{kernel_id}")
        resp.raise_for_status()

    def interrupt_kernel(self, kernel_id: str) -> None:
        resp = self._client.post(f"/api/kernels/{kernel_id}/interrupt")
        resp.raise_for_status()

    def restart_kernel(self, kernel_id: str) -> None:
        resp = self._client.post(f"/api/kernels/{kernel_id}/restart")
        resp.raise_for_status()

    # --- Notebook contents (REST) ---

    def get_notebook(self, path: str) -> dict[str, Any]:
        """GET notebook content from the server."""
        resp = self._client.get(f"/api/contents/{path}")
        resp.raise_for_status()
        return resp.json()["content"]

    def save_notebook(self, path: str, content: dict[str, Any]) -> None:
        """PUT notebook content to the server."""
        resp = self._client.put(
            f"/api/contents/{path}",
            json={"type": "notebook", "format": "json", "content": content},
        )
        resp.raise_for_status()

    # --- Execution (WebSocket) ---

    def execute(self, kernel_id: str, code: str) -> CellResult:
        """Execute code on the kernel and return the collected result."""
        ws = self._get_ws(kernel_id)

        msg = build_execute_request(code)
        msg_id = msg["header"]["msg_id"]
        ws.send(json.dumps(msg))

        iopub_messages: list[dict[str, Any]] = []

        while True:
            raw = ws.recv()
            response = json.loads(raw)

            # Only collect messages that are responses to our request
            parent_msg_id = response.get("parent_header", {}).get("msg_id", "")
            if parent_msg_id != msg_id:
                continue

            channel = response.get("channel", "")
            if channel != "iopub":
                continue

            msg_type = response.get("header", {}).get("msg_type", "")
            content = response.get("content", {})

            # status: idle = done collecting
            if msg_type == "status" and content.get("execution_state") == "idle":
                break

            # skip status:busy and execute_input echo
            if msg_type in ("status", "execute_input"):
                continue

            iopub_messages.append(response)

        return collect_iopub_to_result(iopub_messages)

    # --- Internal ---

    def _get_ws(self, kernel_id: str) -> websocket.WebSocket:
        if kernel_id not in self._ws_connections:
            ws_url = self._ws_url(kernel_id)
            self._ws_connections[kernel_id] = websocket.create_connection(ws_url)
        return self._ws_connections[kernel_id]

    def _close_ws(self, kernel_id: str) -> None:
        if kernel_id in self._ws_connections:
            self._ws_connections[kernel_id].close()
            del self._ws_connections[kernel_id]

    def _fetch_xsrf(self) -> None:
        """Fetch _xsrf cookie from the server and set it as a header for all requests."""
        resp = self._client.get("/tree")
        xsrf = resp.cookies.get("_xsrf")
        if xsrf:
            self._client.headers["X-XSRFToken"] = xsrf
            self._client.cookies.set("_xsrf", xsrf)

    def _ws_url(self, kernel_id: str) -> str:
        base = self.url.replace("http://", "ws://").replace("https://", "wss://")
        return f"{base}/api/kernels/{kernel_id}/channels?token={self.token}"
