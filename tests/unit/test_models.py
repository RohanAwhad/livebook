"""Unit tests for livebook.models — pure data, no server needed."""

from livebook.models import Cell, CellError, CellResult


class TestCellError:
    def test_fields(self):
        err = CellError(ename="ValueError", evalue="bad", traceback=["frame1"])
        assert err.ename == "ValueError"
        assert err.evalue == "bad"
        assert err.traceback == ["frame1"]


class TestCellResult:
    def test_success_when_no_error(self):
        r = CellResult(stdout="hi\n")
        assert r.success is True

    def test_not_success_when_error(self):
        err = CellError(ename="TypeError", evalue="oops", traceback=[])
        r = CellResult(error=err)
        assert r.success is False

    def test_defaults(self):
        r = CellResult()
        assert r.stdout == ""
        assert r.stderr == ""
        assert r.result is None
        assert r.error is None
        assert r.display_data == []


class TestCell:
    def test_basic_fields(self):
        c = Cell(tag="setup-ab12", source="x = 1")
        assert c.tag == "setup-ab12"
        assert c.source == "x = 1"
        assert c.cell_type == "code"
        assert c.result is None

    def test_markdown_cell(self):
        c = Cell(tag="title-ff00", source="# Hi", cell_type="markdown")
        assert c.cell_type == "markdown"

    def test_result_stale_false_when_no_result(self):
        c = Cell(tag="t-0000", source="x = 1")
        assert c.result_stale is False

    def test_result_stale_false_when_source_matches(self):
        c = Cell(tag="t-0000", source="x = 1")
        c.result = CellResult(stdout="ok")
        c._source_at_run = "x = 1"
        assert c.result_stale is False

    def test_result_stale_true_after_source_change(self):
        c = Cell(tag="t-0000", source="x = 1")
        c.result = CellResult(stdout="ok")
        c._source_at_run = "x = 1"
        c.source = "x = 2"
        assert c.result_stale is True

    def test_result_stale_false_when_source_at_run_is_none(self):
        # result exists but _source_at_run was never set (e.g. loaded notebook)
        c = Cell(tag="t-0000", source="x = 1")
        c.result = CellResult()
        assert c.result_stale is False

    def test_repr_no_disclaimer_when_not_stale(self):
        c = Cell(tag="t-0000", source="x = 1")
        c.result = CellResult()
        c._source_at_run = "x = 1"
        assert "previous version" not in repr(c)

    def test_repr_has_disclaimer_when_stale(self):
        c = Cell(tag="t-0000", source="x = 2")
        c.result = CellResult()
        c._source_at_run = "x = 1"
        assert "previous version" in repr(c)

    def test_repr_shows_result_when_present(self):
        c = Cell(tag="t-0000", source="x = 1")
        c.result = CellResult(stdout="hi")
        r = repr(c)
        assert "result=" in r

    def test_repr_omits_result_when_none(self):
        c = Cell(tag="t-0000", source="x = 1")
        r = repr(c)
        assert "result=" not in r
