# livebook — Design Document

A Python library that lets AI agents operate Jupyter notebooks programmatically — creating cells, modifying them, running them — without dealing with raw `.ipynb` JSON.

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Execution target | Remote Jupyter server | Connect via REST + WebSocket |
| Output model | stdout/stderr + result | Rich outputs (images, HTML) deferred to future |
| Cell identity | Tag-based with unique suffix | e.g. `setup-a3f2`. More robust than index-based for agents |
| Interface | Python library (programmatic) | No CLI or tool-calling layer |
| Kernel lifecycle | Notebook owns the kernel | Start on enter, stop on exit. No shared/long-lived kernels |
| Error handling | Captured as result object | No exceptions raised. `CellResult.success` indicates status |
| Dependency tracking | None (v1) | Over-engineering for now |
| Sync vs async | Sync public API | Agent needs previous output before proceeding |
| Tag uniqueness | Enforced unique | Auto-suffixed with 4-char UUID hash |
| Cell ordering | Insertion order, reorderable | Can insert cells between existing ones |
| Package name | `livebook` | — |
| Existing notebook loading | Auto-generate tags | Untagged cells get `cell-0-xxxx`, `cell-1-xxxx`, etc. |
| Cell rewriting | Destructive (no history) | Last write wins. Agent manages its own records if needed |
| Save target | Remote (default) + local | `save()` → server REST API, `save_local()` → filesystem via nbformat |

## Architecture

### Layer Diagram

```
Agent code
    │
    ▼
┌──────────────────┐
│    Notebook       │  ← public API (what agents touch)
│  Cell (tag-based) │
│  CellResult       │
└──────┬───────────┘
       │
┌──────▼───────────┐
│ JupyterConnection │  ← transport layer
│  REST  (httpx)    │  ← kernel lifecycle + remote save
│  WebSocket        │  ← code execution / output
└──────────────────┘
       │
   Remote Jupyter Server
```

### WebSocket Execution Flow

The Jupyter Server multiplexes all ZMQ channels over a single WebSocket at `ws://{host}/api/kernels/{id}/channels`. Messages include a `channel` field (`"shell"`, `"iopub"`, `"stdin"`, `"control"`).

```
Client                          Jupyter Server (WS)
  │                                    │
  ├─ execute_request (channel=shell) ──►
  │                                    │
  ◄── status: busy (iopub) ────────────┤
  ◄── execute_input (iopub) ───────────┤  (echo)
  ◄── stream (iopub) ─────────────────┤  (stdout/stderr, 0..N)
  ◄── display_data (iopub) ───────────┤  (rich output, 0..N)
  ◄── execute_result (iopub) ─────────┤  (return value, 0..1)
  ◄── error (iopub) ──────────────────┤  (if exception)
  ◄── status: idle (iopub) ───────────┤  (done signal)
  ◄── execute_reply (shell) ──────────┤  (final status)
```

All `iopub` messages are collected until `status: idle`, then packed into a `CellResult`.

## Data Models

### `CellError`

```python
@dataclass
class CellError:
    ename: str           # e.g. "ValueError"
    evalue: str          # e.g. "invalid literal for int()"
    traceback: list[str] # traceback frames (may contain ANSI codes)
```

### `CellResult`

```python
@dataclass
class CellResult:
    stdout: str                    # accumulated stream name=stdout
    stderr: str                    # accumulated stream name=stderr
    result: str | None             # text/plain from execute_result (return value)
    error: CellError | None        # populated if execution errored
    display_data: list[dict]       # rich outputs (future use)  # (rohan): do not implement this now!

    @property
    def success(self) -> bool:
        return self.error is None
```

### `Cell`

```python
@dataclass
class Cell:
    tag: str                                        # unique identifier, e.g. "setup-a3f2"
    source: str                                     # code or markdown content
    cell_type: Literal["code", "markdown"] = "code"
    result: CellResult | None = None                # last execution result (code cells only)
    _source_at_run: str | None = None               # snapshot of source when run() was last called

    @property
    def result_stale(self) -> bool:
        """True if source was modified after the last run()."""
        if self.result is None or self._source_at_run is None:
            return False
        return self.source != self._source_at_run
```

## Public API

### Connection

```python
conn = JupyterConnection(url="http://localhost:8888", token="my-token")
```

Auth via `Authorization: token <token>` header or `?token=...` query param.

### Notebook Lifecycle

```python
# create new notebook, kernel starts on enter
with Notebook(conn, kernel="python3") as nb:
    ...
# kernel is stopped on exit

# load existing .ipynb from the Jupyter server
with Notebook.open(conn, "existing.ipynb") as nb:
    ...
```

### Cell Management

```python
# add cells (appended to end) — returns the Cell object
cell = nb.add_code("import pandas as pd", tag="setup")
cell.tag   # "setup-a3f2" (full tag with suffix)
nb.add_markdown("# Analysis", tag="title")

# access by tag
cell = nb["setup"]
cell.source                         # read source
cell.source = "import polars as pl" # rewrite (destructive, no history)

# insert relative to existing cells — also returns Cell
preamble = nb.insert_before("setup", code="# preamble", tag="preamble")
load = nb.insert_after("setup", code="df = pd.read_csv('data.csv')", tag="load-data")

# remove
nb.remove("preamble")

# reorder
nb.move("load-data", before="setup")

# list all tags (in order)
nb.tags  # ["title", "setup", "load-data"]
```

### Tag Generation

Tags are auto-suffixed with a 4-char UUID to ensure uniqueness:

```python
cell1 = nb.add_code("x = 1", tag="setup")   # cell1.tag == "setup-a3f2"
cell2 = nb.add_code("y = 2", tag="setup")   # cell2.tag == "setup-b7c1" (no collision)

# access uses the full tag
nb[cell1.tag]
```

For loaded notebooks without tags: `cell-0-xxxx`, `cell-1-xxxx`, etc.

### Execution

```python
# run single cell by tag
result = nb.run("setup-a3f2")
result.success      # True
result.stdout       # "hello\n"
result.stderr       # ""
result.result       # "42" (if cell returns a value)
result.error        # None (or CellError if failed)

# run all cells in insertion order
results = nb.run_all()  # returns dict[str, CellResult] keyed by tag
```

### Save

```python
# remote save (default) — PUT /api/contents/{path} on the Jupyter server
nb.save("analysis.ipynb")

# local save — write to client filesystem via nbformat
nb.save_local("./notebooks/analysis.ipynb")
```

Both methods share the same conversion logic: `Cell` objects → nbformat `NotebookNode` cells → JSON. Tags are stored in `cell.metadata.tags`.

## Transport Layer (`JupyterConnection`)

### REST API (kernel lifecycle + save)

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/kernels` | Start kernel. Body: `{"name": "python3"}`. Returns `{"id": "..."}` |
| `DELETE` | `/api/kernels/{id}` | Stop kernel |
| `POST` | `/api/kernels/{id}/interrupt` | Interrupt running execution |
| `POST` | `/api/kernels/{id}/restart` | Restart kernel |
| `PUT` | `/api/contents/{path}` | Save notebook to server. Body: `{"type": "notebook", "format": "json", "content": <notebook_json>}` |

### WebSocket (code execution)

Endpoint: `ws://{host}/api/kernels/{id}/channels?token=...`

Messages are JSON with Jupyter messaging protocol v5 format:

```json
{
  "header": {
    "msg_id": "uuid",
    "msg_type": "execute_request",
    "session": "uuid",
    "username": "",
    "version": "5.0",
    "date": "ISO-8601"
  },
  "parent_header": {},
  "metadata": {},
  "content": {
    "code": "print('hello')",
    "silent": false,
    "store_history": true,
    "user_expressions": {},
    "allow_stdin": false,
    "stop_on_error": false
  },
  "buffers": [],
  "channel": "shell"
}
```

Response messages arrive on the `iopub` channel. Relevant `msg_type` values:

| msg_type | content shape | maps to |
|---|---|---|
| `stream` | `{"name": "stdout"\|"stderr", "text": str}` | `CellResult.stdout` / `.stderr` |
| `execute_result` | `{"data": {"text/plain": str, ...}, "execution_count": int}` | `CellResult.result` |
| `display_data` | `{"data": {"text/plain": str, ...}, "metadata": dict}` | `CellResult.display_data` |
| `error` | `{"ename": str, "evalue": str, "traceback": list[str]}` | `CellResult.error` → `CellError` |
| `status` | `{"execution_state": "busy"\|"idle"}` | `idle` = done collecting |

The `execute_reply` on the `shell` channel confirms final status but is secondary — we rely on `status: idle` on `iopub` to know output collection is complete.

## Cell Rewriting Behavior

Rewriting a cell is a simple mutation:

```python
nb["setup-a3f2"].source = "import polars as pl"
```

- The old source is **discarded** (no history, no undo)
- `cell.result` is **not cleared** — it still holds the result from the last `run()`
- `cell.result_stale` becomes `True` — source no longer matches what was executed
- To get the updated result, the agent must call `nb.run("setup-a3f2")` again
- On `save()`, the **current** `.source` and `.result` are persisted

### Staleness Tracking

When `run()` is called, `cell._source_at_run` is snapshot to the current `cell.source`. If the agent later mutates `cell.source`, `cell.result_stale` returns `True`.

When representing a `CellResult` to an agent (e.g. via `__repr__` or a display method), if `result_stale` is `True`, append a disclaimer:

> **Note:** This result is from a previous version of the cell source. Re-run the cell to get the latest result.

## File Layout

```
livebook/
├── __init__.py          # re-export: Notebook, Cell, CellResult, CellError, JupyterConnection
├── models.py            # dataclasses: Cell, CellResult, CellError
├── connection.py        # JupyterConnection: REST (httpx) + WebSocket (websocket-client)
├── notebook.py          # Notebook: public API, cell management, save/load
└── _proto.py            # Jupyter message builders/parsers (execute_request, iopub parsing)
```

## Dependencies

| Package | Purpose |
|---|---|
| `httpx` | REST API calls (kernel lifecycle, remote save) |
| `websocket-client` | Sync WebSocket (code execution over kernel channels) |
| `nbformat` | Save/load `.ipynb` files, cell/notebook construction |

No `jupyter_client` dependency — we talk directly to the Jupyter server's HTTP + WebSocket API.

## Implementation Order

1. `models.py` — data classes (no deps, pure data)
2. `_proto.py` — Jupyter message builders and iopub parsers
3. `connection.py` — REST + WS transport
4. `notebook.py` — public API, wiring everything together
5. Manual test with `play.py` against a local `jupyter server`
6. Unit tests for models + proto, integration test for connection + notebook
