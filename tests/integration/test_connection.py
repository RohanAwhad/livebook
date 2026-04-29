"""Integration tests for JupyterConnection against a real Jupyter server."""

from livebook import JupyterConnection


class TestKernelLifecycle:
    def test_start_and_stop(self, conn: JupyterConnection):
        kernel_id = conn.start_kernel("python3")
        assert isinstance(kernel_id, str)
        assert len(kernel_id) > 0
        conn.stop_kernel(kernel_id)

    def test_restart(self, conn: JupyterConnection):
        kernel_id = conn.start_kernel("python3")
        conn.restart_kernel(kernel_id)
        # kernel should still be usable after restart
        result = conn.execute(kernel_id, "1 + 1")
        assert result.success
        conn.stop_kernel(kernel_id)

    def test_interrupt(self, conn: JupyterConnection):
        kernel_id = conn.start_kernel("python3")
        conn.interrupt_kernel(kernel_id)
        conn.stop_kernel(kernel_id)


class TestExecute:
    def test_stdout(self, conn: JupyterConnection):
        kernel_id = conn.start_kernel("python3")
        result = conn.execute(kernel_id, "print('hello')")
        assert result.success
        assert result.stdout == "hello\n"
        conn.stop_kernel(kernel_id)

    def test_stderr(self, conn: JupyterConnection):
        kernel_id = conn.start_kernel("python3")
        result = conn.execute(kernel_id, "import sys; sys.stderr.write('warn\\n')")
        assert result.success
        assert "warn" in result.stderr
        conn.stop_kernel(kernel_id)

    def test_return_value(self, conn: JupyterConnection):
        kernel_id = conn.start_kernel("python3")
        result = conn.execute(kernel_id, "2 + 3")
        assert result.success
        assert result.result == "5"
        conn.stop_kernel(kernel_id)

    def test_error(self, conn: JupyterConnection):
        kernel_id = conn.start_kernel("python3")
        result = conn.execute(kernel_id, "1 / 0")
        assert not result.success
        assert result.error is not None
        assert result.error.ename == "ZeroDivisionError"
        conn.stop_kernel(kernel_id)

    def test_multiple_executions_same_kernel(self, conn: JupyterConnection):
        kernel_id = conn.start_kernel("python3")
        r1 = conn.execute(kernel_id, "x = 42")
        assert r1.success
        r2 = conn.execute(kernel_id, "print(x)")
        assert r2.success
        assert r2.stdout == "42\n"
        conn.stop_kernel(kernel_id)

    def test_stdout_and_return_value(self, conn: JupyterConnection):
        kernel_id = conn.start_kernel("python3")
        result = conn.execute(kernel_id, "print('side effect')\n99")
        assert result.success
        assert "side effect" in result.stdout
        assert result.result == "99"
        conn.stop_kernel(kernel_id)


class TestNotebookContents:
    def test_save_and_get_roundtrip(self, conn: JupyterConnection, remote_notebooks):
        import nbformat

        nb = nbformat.v4.new_notebook()
        nb.cells.append(nbformat.v4.new_code_cell(source="x = 1"))
        content = nbformat.writes(nb)

        import json

        remote_notebooks.append("test_roundtrip.ipynb")
        conn.save_notebook("test_roundtrip.ipynb", json.loads(content))
        loaded = conn.get_notebook("test_roundtrip.ipynb")
        assert len(loaded["cells"]) == 1
        assert loaded["cells"][0]["source"] == "x = 1"
