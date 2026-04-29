"""Unit tests for livebook._proto — message builders and parsers."""

from livebook._proto import build_execute_request, collect_iopub_to_result


class TestBuildExecuteRequest:
    def test_structure(self):
        msg = build_execute_request("print('hi')")
        assert msg["header"]["msg_type"] == "execute_request"
        assert msg["content"]["code"] == "print('hi')"
        assert msg["channel"] == "shell"

    def test_unique_msg_ids(self):
        m1 = build_execute_request("x")
        m2 = build_execute_request("x")
        assert m1["header"]["msg_id"] != m2["header"]["msg_id"]

    def test_custom_msg_id(self):
        msg = build_execute_request("x", msg_id="my-id")
        assert msg["header"]["msg_id"] == "my-id"

    def test_custom_session_id(self):
        msg = build_execute_request("x", session_id="my-session")
        assert msg["header"]["session"] == "my-session"

    def test_required_fields(self):
        msg = build_execute_request("x")
        assert "header" in msg
        assert "parent_header" in msg
        assert "metadata" in msg
        assert "content" in msg
        assert "buffers" in msg
        assert msg["header"]["version"] == "5.0"

    def test_content_defaults(self):
        msg = build_execute_request("x")
        c = msg["content"]
        assert c["silent"] is False
        assert c["store_history"] is True
        assert c["allow_stdin"] is False
        assert c["stop_on_error"] is False


def _make_iopub(msg_type: str, content: dict) -> dict:
    """Helper to build a minimal iopub message."""
    return {"header": {"msg_type": msg_type}, "content": content}


class TestCollectIopubToResult:
    def test_empty(self):
        r = collect_iopub_to_result([])
        assert r.success is True
        assert r.stdout == ""
        assert r.stderr == ""
        assert r.result is None

    def test_stdout(self):
        msgs = [_make_iopub("stream", {"name": "stdout", "text": "hello\n"})]
        r = collect_iopub_to_result(msgs)
        assert r.stdout == "hello\n"
        assert r.stderr == ""

    def test_stderr(self):
        msgs = [_make_iopub("stream", {"name": "stderr", "text": "warn\n"})]
        r = collect_iopub_to_result(msgs)
        assert r.stderr == "warn\n"

    def test_multiple_stdout_accumulated(self):
        msgs = [
            _make_iopub("stream", {"name": "stdout", "text": "a"}),
            _make_iopub("stream", {"name": "stdout", "text": "b"}),
        ]
        r = collect_iopub_to_result(msgs)
        assert r.stdout == "ab"

    def test_execute_result(self):
        msgs = [
            _make_iopub(
                "execute_result",
                {"data": {"text/plain": "42"}, "execution_count": 1},
            )
        ]
        r = collect_iopub_to_result(msgs)
        assert r.result == "42"

    def test_error(self):
        msgs = [
            _make_iopub(
                "error",
                {
                    "ename": "ZeroDivisionError",
                    "evalue": "division by zero",
                    "traceback": ["frame1", "frame2"],
                },
            )
        ]
        r = collect_iopub_to_result(msgs)
        assert r.success is False
        assert r.error is not None
        assert r.error.ename == "ZeroDivisionError"
        assert r.error.evalue == "division by zero"
        assert r.error.traceback == ["frame1", "frame2"]

    def test_display_data(self):
        msgs = [
            _make_iopub("display_data", {"data": {"text/html": "<b>hi</b>"}})
        ]
        r = collect_iopub_to_result(msgs)
        assert len(r.display_data) == 1
        assert r.display_data[0]["text/html"] == "<b>hi</b>"

    def test_mixed_messages(self):
        msgs = [
            _make_iopub("stream", {"name": "stdout", "text": "out\n"}),
            _make_iopub("stream", {"name": "stderr", "text": "err\n"}),
            _make_iopub(
                "execute_result",
                {"data": {"text/plain": "99"}, "execution_count": 1},
            ),
        ]
        r = collect_iopub_to_result(msgs)
        assert r.stdout == "out\n"
        assert r.stderr == "err\n"
        assert r.result == "99"
        assert r.success is True
