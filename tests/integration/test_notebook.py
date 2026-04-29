"""Integration tests for Notebook against a real Jupyter server."""

import os

from livebook import JupyterConnection, Notebook, Cell, CellResult, CellError


class TestNotebookLifecycle:
    def test_context_manager(self, conn: JupyterConnection):
        with Notebook(conn) as nb:
            assert nb._kernel_id is not None
        assert nb._kernel_id is None

    def test_manual_kernel_via_connection(self, conn: JupyterConnection):
        kernel_id = conn.start_kernel("python3")
        result = conn.execute(kernel_id, "1 + 1")
        assert result.success
        conn.stop_kernel(kernel_id)


class TestCellManagement:
    def test_add_code_returns_cell(self, conn: JupyterConnection):
        with Notebook(conn) as nb:
            cell = nb.add_code("x = 1", tag="setup")
            assert isinstance(cell, Cell)
            assert cell.tag.startswith("setup-")
            assert cell.source == "x = 1"
            assert cell.cell_type == "code"

    def test_add_markdown(self, conn: JupyterConnection):
        with Notebook(conn) as nb:
            cell = nb.add_markdown("# Title", tag="title")
            assert cell.cell_type == "markdown"
            assert cell.tag.startswith("title-")

    def test_tag_uniqueness(self, conn: JupyterConnection):
        with Notebook(conn) as nb:
            c1 = nb.add_code("x = 1", tag="dup")
            c2 = nb.add_code("x = 2", tag="dup")
            assert c1.tag != c2.tag

    def test_tags_property(self, conn: JupyterConnection):
        with Notebook(conn) as nb:
            a = nb.add_code("1", tag="a")
            b = nb.add_code("2", tag="b")
            assert nb.tags == [a.tag, b.tag]

    def test_getitem(self, conn: JupyterConnection):
        with Notebook(conn) as nb:
            cell = nb.add_code("x = 1", tag="x")
            assert nb[cell.tag] is cell

    def test_getitem_bad_tag(self, conn: JupyterConnection):
        with Notebook(conn) as nb:
            import pytest

            with pytest.raises(KeyError):
                nb["nonexistent"]

    def test_insert_before(self, conn: JupyterConnection):
        with Notebook(conn) as nb:
            a = nb.add_code("a", tag="a")
            b = nb.insert_before(a.tag, code="b", tag="b")
            assert nb.tags.index(b.tag) < nb.tags.index(a.tag)

    def test_insert_after(self, conn: JupyterConnection):
        with Notebook(conn) as nb:
            a = nb.add_code("a", tag="a")
            b = nb.insert_after(a.tag, code="b", tag="b")
            assert nb.tags.index(b.tag) > nb.tags.index(a.tag)

    def test_remove(self, conn: JupyterConnection):
        with Notebook(conn) as nb:
            a = nb.add_code("a", tag="a")
            b = nb.add_code("b", tag="b")
            nb.remove(a.tag)
            assert a.tag not in nb.tags
            assert b.tag in nb.tags


class TestExecution:
    def test_run_single(self, conn: JupyterConnection):
        with Notebook(conn) as nb:
            cell = nb.add_code("print('hi')", tag="greet")
            result = nb.run(cell.tag)
            assert isinstance(result, CellResult)
            assert result.success
            assert result.stdout == "hi\n"

    def test_run_sets_cell_result(self, conn: JupyterConnection):
        with Notebook(conn) as nb:
            cell = nb.add_code("42", tag="val")
            nb.run(cell.tag)
            assert cell.result is not None
            assert cell.result.result == "42"

    def test_run_error(self, conn: JupyterConnection):
        with Notebook(conn) as nb:
            cell = nb.add_code("1/0", tag="err")
            result = nb.run(cell.tag)
            assert not result.success
            assert isinstance(result.error, CellError)
            assert result.error.ename == "ZeroDivisionError"

    def test_run_all_skips_markdown(self, conn: JupyterConnection):
        with Notebook(conn) as nb:
            code = nb.add_code("1", tag="c")
            md = nb.add_markdown("# hi", tag="m")
            results = nb.run_all()
            assert code.tag in results
            assert md.tag not in results

    def test_run_all_preserves_state(self, conn: JupyterConnection):
        with Notebook(conn) as nb:
            nb.add_code("x = 10", tag="setup")
            check = nb.add_code("print(x)", tag="check")
            results = nb.run_all()
            assert results[check.tag].stdout == "10\n"


class TestStaleness:
    def test_not_stale_after_run(self, conn: JupyterConnection):
        with Notebook(conn) as nb:
            cell = nb.add_code("x = 1", tag="s")
            nb.run(cell.tag)
            assert not cell.result_stale

    def test_stale_after_source_change(self, conn: JupyterConnection):
        with Notebook(conn) as nb:
            cell = nb.add_code("x = 1", tag="s")
            nb.run(cell.tag)
            cell.source = "x = 2"
            assert cell.result_stale

    def test_not_stale_after_rerun(self, conn: JupyterConnection):
        with Notebook(conn) as nb:
            cell = nb.add_code("x = 1", tag="s")
            nb.run(cell.tag)
            cell.source = "x = 2"
            nb.run(cell.tag)
            assert not cell.result_stale


class TestSave:
    def test_save_local(self, conn: JupyterConnection, tmp_path):
        with Notebook(conn) as nb:
            nb.add_code("x = 1", tag="s")
            nb.add_markdown("# hi", tag="m")
            path = str(tmp_path / "test.ipynb")
            nb.save_local(path)
            assert os.path.exists(path)

            # verify it's valid nbformat
            import nbformat

            with open(path) as f:
                loaded = nbformat.read(f, as_version=4)
            assert len(loaded.cells) == 2
            assert loaded.cells[0].source == "x = 1"
            assert loaded.cells[0].metadata["tags"][0].startswith("s-")
            assert loaded.cells[1].cell_type == "markdown"

    def test_save_remote(self, conn: JupyterConnection):
        with Notebook(conn) as nb:
            nb.add_code("y = 2", tag="r")
            nb.save("test_save_remote.ipynb")

        # verify by loading it back
        with Notebook.open(conn, "test_save_remote.ipynb") as nb2:
            assert len(nb2.tags) == 1
            assert nb2[nb2.tags[0]].source == "y = 2"

    def test_open_preserves_tags(self, conn: JupyterConnection):
        with Notebook(conn) as nb:
            c = nb.add_code("z = 3", tag="keep")
            original_tag = c.tag
            nb.save("test_preserve_tags.ipynb")

        with Notebook.open(conn, "test_preserve_tags.ipynb") as nb2:
            assert original_tag in nb2.tags
            assert nb2[original_tag].source == "z = 3"
