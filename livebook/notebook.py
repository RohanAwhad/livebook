"""Notebook: public API for cell management, execution, and save."""

from __future__ import annotations

import json
import uuid
from typing import Any

import nbformat

from .connection import JupyterConnection
from .models import Cell, CellResult


def _generate_tag_suffix() -> str:
    return uuid.uuid4().hex[:4]


class Notebook:
    def __init__(self, conn: JupyterConnection, kernel: str = "python3") -> None:
        self._conn = conn
        self._kernel_name = kernel
        self._kernel_id: str | None = None
        self._cells: list[Cell] = []
        self._tag_to_index: dict[str, int] = {}

    @classmethod
    def open(
        cls, conn: JupyterConnection, path: str, kernel: str = "python3"
    ) -> Notebook:
        """Load an existing .ipynb from the Jupyter server."""
        nb = cls(conn, kernel)
        content = conn.get_notebook(path)
        nb_node = nbformat.reads(json.dumps(content), as_version=4)
        for i, nb_cell in enumerate(nb_node.cells):
            tags = nb_cell.metadata.get("tags", [])
            tag = tags[0] if tags else f"cell-{i}-{_generate_tag_suffix()}"
            cell_type = nb_cell.cell_type
            if cell_type not in ("code", "markdown"):
                cell_type = "code"
            cell = Cell(tag=tag, source=nb_cell.source, cell_type=cell_type)
            nb._cells.append(cell)
        nb._rebuild_index()
        return nb

    # --- Kernel lifecycle ---

    def start(self) -> str:
        """Start the kernel. Returns kernel_id."""
        self._kernel_id = self._conn.start_kernel(self._kernel_name)
        return self._kernel_id

    def stop(self) -> None:
        """Stop the kernel."""
        if self._kernel_id:
            self._conn.stop_kernel(self._kernel_id)
            self._kernel_id = None

    def __enter__(self) -> Notebook:
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()

    # --- Cell management ---

    def add_code(self, source: str, tag: str = "cell") -> Cell:
        """Append a code cell. Returns the Cell (with full tag)."""
        full_tag = self._make_tag(tag)
        cell = Cell(tag=full_tag, source=source, cell_type="code")
        self._cells.append(cell)
        self._rebuild_index()
        return cell

    def add_markdown(self, source: str, tag: str = "cell") -> Cell:
        """Append a markdown cell. Returns the Cell (with full tag)."""
        full_tag = self._make_tag(tag)
        cell = Cell(tag=full_tag, source=source, cell_type="markdown")
        self._cells.append(cell)
        self._rebuild_index()
        return cell

    def insert_before(self, ref_tag: str, code: str, tag: str = "cell") -> Cell:
        """Insert a code cell before the cell with ref_tag. Returns the Cell."""
        idx = self._resolve_index(ref_tag)
        full_tag = self._make_tag(tag)
        cell = Cell(tag=full_tag, source=code, cell_type="code")
        self._cells.insert(idx, cell)
        self._rebuild_index()
        return cell

    def insert_after(self, ref_tag: str, code: str, tag: str = "cell") -> Cell:
        """Insert a code cell after the cell with ref_tag. Returns the Cell."""
        idx = self._resolve_index(ref_tag)
        full_tag = self._make_tag(tag)
        cell = Cell(tag=full_tag, source=code, cell_type="code")
        self._cells.insert(idx + 1, cell)
        self._rebuild_index()
        return cell

    def remove(self, tag: str) -> None:
        """Remove a cell by tag."""
        idx = self._resolve_index(tag)
        self._cells.pop(idx)
        self._rebuild_index()

    def __getitem__(self, tag: str) -> Cell:
        return self._cells[self._resolve_index(tag)]

    @property
    def tags(self) -> list[str]:
        """All cell tags in insertion order."""
        return [cell.tag for cell in self._cells]

    # --- Execution ---

    def run(self, tag: str) -> CellResult:
        """Run a single cell by tag. Returns CellResult."""
        assert self._kernel_id is not None, "Kernel not started. Call nb.start() or use as context manager"
        cell = self[tag]
        result = self._conn.execute(self._kernel_id, cell.source)
        cell.result = result
        cell._source_at_run = cell.source  # snapshot for staleness tracking
        return result

    def run_all(self) -> dict[str, CellResult]:
        """Run all code cells in order. Returns dict of tag -> CellResult."""
        results: dict[str, CellResult] = {}
        for cell in self._cells:
            if cell.cell_type == "code":
                results[cell.tag] = self.run(cell.tag)
        return results

    # --- Save ---

    def save(self, path: str) -> None:
        """Save notebook to the Jupyter server via REST PUT."""
        nb_node = self._to_nbformat()
        content = json.loads(nbformat.writes(nb_node))
        self._conn.save_notebook(path, content)

    def save_local(self, path: str) -> None:
        """Save notebook to the local filesystem via nbformat."""
        nb_node = self._to_nbformat()
        with open(path, "w") as f:
            nbformat.write(nb_node, f)

    # --- Session persistence ---

    def save_session(self, path: str) -> None:
        """Save notebook state (kernel_id, cells) to a JSON file."""
        data = {
            "kernel_id": self._kernel_id,
            "kernel_name": self._kernel_name,
            "cells": [
                {"tag": c.tag, "source": c.source, "cell_type": c.cell_type}
                for c in self._cells
            ],
        }
        with open(path, "w") as f:
            json.dump(data, f)

    @classmethod
    def load_session(cls, conn: JupyterConnection, path: str) -> Notebook:
        """Restore a notebook from a session file. Reconnects to the existing kernel."""
        with open(path) as f:
            data = json.load(f)
        nb = cls(conn, kernel=data.get("kernel_name", "python3"))
        nb._kernel_id = data["kernel_id"]
        for cell_data in data.get("cells", []):
            cell = Cell(
                tag=cell_data["tag"],
                source=cell_data["source"],
                cell_type=cell_data.get("cell_type", "code"),
            )
            nb._cells.append(cell)
        nb._rebuild_index()
        return nb

    # --- Internal ---

    def _make_tag(self, base: str) -> str:
        return f"{base}-{_generate_tag_suffix()}"

    def _rebuild_index(self) -> None:
        self._tag_to_index = {cell.tag: i for i, cell in enumerate(self._cells)}

    def _resolve_index(self, tag: str) -> int:
        if tag not in self._tag_to_index:
            raise KeyError(f"No cell with tag {tag!r}")
        return self._tag_to_index[tag]

    def _to_nbformat(self) -> nbformat.NotebookNode:
        """Convert internal cells to an nbformat NotebookNode."""
        nb = nbformat.v4.new_notebook()
        for cell in self._cells:
            if cell.cell_type == "code":
                nb_cell = nbformat.v4.new_code_cell(source=cell.source)
            else:
                nb_cell = nbformat.v4.new_markdown_cell(source=cell.source)
            nb_cell.metadata["tags"] = [cell.tag]
            nb.cells.append(nb_cell)
        return nb
