"""Jupyter messaging protocol v5 builders and parsers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .models import CellError, CellResult


def _new_id() -> str:
    return uuid.uuid4().hex


def build_execute_request(
    code: str,
    msg_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Build a Jupyter execute_request message for the shell channel."""
    msg_id = msg_id or _new_id()
    session_id = session_id or _new_id()
    return {
        "header": {
            "msg_id": msg_id,
            "msg_type": "execute_request",
            "session": session_id,
            "username": "",
            "version": "5.0",
            "date": datetime.now(timezone.utc).isoformat(),
        },
        "parent_header": {},
        "metadata": {},
        "content": {
            "code": code,
            "silent": False,
            "store_history": True,
            "user_expressions": {},
            "allow_stdin": False,
            "stop_on_error": False,
        },
        "buffers": [],
        "channel": "shell",
    }


def collect_iopub_to_result(messages: list[dict[str, Any]]) -> CellResult:
    """Collect iopub messages into a CellResult.

    Expects raw Jupyter WS messages with header/content structure.
    Messages of type status and execute_input should be pre-filtered.
    """
    stdout = ""
    stderr = ""
    result: str | None = None
    error: CellError | None = None
    display_data: list[dict] = []

    for msg in messages:
        msg_type = msg["header"]["msg_type"]
        content = msg["content"]

        if msg_type == "stream":
            name = content.get("name", "")
            text = content.get("text", "")
            if name == "stdout":
                stdout += text
            elif name == "stderr":
                stderr += text
        elif msg_type == "execute_result":
            data = content.get("data", {})
            result = data.get("text/plain")
        elif msg_type == "display_data":
            display_data.append(content.get("data", {}))
        elif msg_type == "error":
            error = CellError(
                ename=content.get("ename", ""),
                evalue=content.get("evalue", ""),
                traceback=content.get("traceback", []),
            )

    return CellResult(
        stdout=stdout,
        stderr=stderr,
        result=result,
        error=error,
        display_data=display_data,
    )
