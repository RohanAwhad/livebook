"""Data models: CellError, CellResult, Cell."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class CellError:
    ename: str  # e.g. "ValueError"
    evalue: str  # e.g. "invalid literal for int()"
    traceback: list[str]  # traceback frames (may contain ANSI codes)


@dataclass
class CellResult:
    stdout: str = ""
    stderr: str = ""
    result: str | None = None  # text/plain from execute_result
    error: CellError | None = None
    display_data: list[dict] = field(default_factory=list)  # rich outputs (future)

    @property
    def success(self) -> bool:
        return self.error is None


@dataclass
class Cell:
    tag: str  # unique identifier, e.g. "setup-a3f2"
    source: str  # code or markdown content
    cell_type: Literal["code", "markdown"] = "code"
    result: CellResult | None = None
    _source_at_run: str | None = field(
        default=None, init=False, repr=False, compare=False
    )

    @property
    def result_stale(self) -> bool:
        """True if source was modified after the last run()."""
        if self.result is None or self._source_at_run is None:
            return False
        return self.source != self._source_at_run

    def __repr__(self) -> str:
        base = (
            f"Cell(tag={self.tag!r}, source={self.source!r}, "
            f"cell_type={self.cell_type!r}"
        )
        if self.result is not None:
            base += f", result={self.result!r}"
        base += ")"
        if self.result_stale:
            base += (
                "\nNote: This result is from a previous version of the cell "
                "source. Re-run the cell to get the latest result."
            )
        return base
