---
name: livebook
description: Programmatic Jupyter notebook control for AI agents. Create cells, run them, check results, update cells, and save notebooks — all from Python via `livebook-run`. Use when the user asks to create, run, or manage Jupyter notebooks programmatically.
---

# Skill: livebook

Programmatic Jupyter notebook control for AI agents. Create cells, run them, check results, update cells, and save notebooks — all from Python via `livebook-run`.

## Prerequisites

| Requirement | Details |
|---|---|
| `livebook-run` | Installed globally via `uv tool install "livebook @ git+https://github.com/RohanAwhad/livebook.git"` |
| Jupyter server | Must be running. Agent should ask the user for URL and token. |

## Core Concepts

- **Notebook** — manages cells and talks to a Jupyter kernel
- **JupyterConnection** — transport layer (URL + token). Created once, passed to Notebook.
- **Cell** — has a `tag` (unique ID like `setup-a3f2`), `source` (code), and `result`
- **CellResult** — contains `stdout`, `stderr`, `result` (return value), `error`, and `success` (bool)
- **Session file** — JSON file that persists kernel_id + cells between turns. Always pass the path explicitly.
- **Tags** — auto-suffixed with 4-char hash for uniqueness. `add_code(..., tag="setup")` produces `"setup-a3f2"`. Use `cell.tag` to get the full tag.

## Multi-Turn Workflow

Each agent turn is a separate `livebook-run -c "..."` invocation. State is preserved via a session file.

### Turn 1 — Start a new session

```bash
livebook-run -c "
from livebook import Notebook, JupyterConnection
conn = JupyterConnection(url='http://localhost:8888', token='')
nb = Notebook(conn)
nb.start()

cell = nb.add_code('import os; print(os.listdir(\".\"))', tag='explore')
result = nb.run(cell.tag)
print(f'tag: {cell.tag}')
print(result)

nb.save_session('.livebook_session.json')
"
```

### Turn N — Load session, add/update cells

```bash
livebook-run -c "
from livebook import Notebook, JupyterConnection
conn = JupyterConnection(url='http://localhost:8888', token='')
nb = Notebook.load_session(conn, '.livebook_session.json')

cell = nb.add_code('print(\"next step\")', tag='step2')
result = nb.run(cell.tag)
print(f'tag: {cell.tag}')
print(result)

nb.save_session('.livebook_session.json')
"
```

### Updating a cell and re-running

```bash
livebook-run -c "
from livebook import Notebook, JupyterConnection
conn = JupyterConnection(url='http://localhost:8888', token='')
nb = Notebook.load_session(conn, '.livebook_session.json')

nb['explore-a3f2'].source = 'import os; print(os.getcwd())'
result = nb.run('explore-a3f2')
print(result)

nb.save_session('.livebook_session.json')
"
```

### Final turn — Save notebook and stop kernel

```bash
livebook-run -c "
from livebook import Notebook, JupyterConnection
conn = JupyterConnection(url='http://localhost:8888', token='')
nb = Notebook.load_session(conn, '.livebook_session.json')
nb.save_local('analysis.ipynb')
nb.stop()
"
```

Clean up the session file after stopping:
```bash
rm .livebook_session.json
```

## API Reference

### Connection

```python
conn = JupyterConnection(url="http://localhost:8888", token="my-token")
# For no-token servers:
conn = JupyterConnection(url="http://localhost:8888", token="")
```

### Notebook lifecycle

```python
nb = Notebook(conn)
kernel_id = nb.start()      # start kernel, returns kernel_id
nb.stop()                    # stop kernel

# Or use context manager (auto start/stop):
with Notebook(conn) as nb:
    ...
```

### Cell management

```python
cell = nb.add_code("x = 1", tag="setup")          # returns Cell, tag auto-suffixed
cell = nb.add_markdown("# Title", tag="title")     # markdown cell

cell = nb.insert_before("setup-a3f2", code="# preamble", tag="pre")
cell = nb.insert_after("setup-a3f2", code="y = 2", tag="next")

nb.remove("pre-b1c2")                              # remove by tag

nb["setup-a3f2"]                                    # access cell by tag
nb["setup-a3f2"].source = "x = 99"                  # update cell source
nb.tags                                             # list all tags in order
```

### Execution

```python
result = nb.run("setup-a3f2")     # run single cell, returns CellResult
result.success                     # True if no error
result.stdout                      # captured stdout
result.stderr                      # captured stderr
result.result                      # return value (text/plain repr)
result.error                       # CellError or None
result.error.ename                 # e.g. "ValueError"
result.error.evalue                # e.g. "invalid literal"

results = nb.run_all()             # run all code cells, returns dict[tag, CellResult]
```

### Staleness tracking

```python
nb.run("setup-a3f2")                    # result_stale = False
nb["setup-a3f2"].source = "new code"    # result_stale = True
# repr(cell) will include a disclaimer warning about stale results
nb.run("setup-a3f2")                    # result_stale = False again
```

### Session persistence

```python
nb.save_session(".livebook_session.json")                  # save kernel_id + cells
nb2 = Notebook.load_session(conn, ".livebook_session.json") # restore and reconnect
```

### Save

```python
nb.save_local("analysis.ipynb")         # save to local filesystem
nb.save("analysis.ipynb")               # save to Jupyter server
```

### Load existing notebook from server

```python
nb = Notebook.open(conn, "existing.ipynb")
nb.start()  # or use as context manager
```

## Important Rules

1. **Always `load_session` on turn 2+** — every turn after the first must start with `Notebook.load_session(conn, path)`. Without it, you lose all cells and the kernel connection.
2. **Always print `cell.tag`** after `add_code` — you need the full tag (with suffix) for subsequent turns.
3. **Always `save_session`** at the end of every turn (except the final stop turn).
4. **Always pass `path` to `save_session`** — it does not remember the last path.
5. **One `livebook-run -c` per turn** — check the output, then decide the next step.
6. **Kernel state persists** between turns — variables defined in cell 1 are available in cell 2.
7. **Notebook state persists** via session file — cells, tags, and ordering are restored on `load_session`.
8. **Clean up** — call `nb.stop()` and `rm .livebook_session.json` when done.

## Human-AI Notebook Sync Checklist

The human may be editing the same notebook in the Jupyter UI while you edit via livebook. There is no CRDT/OT layer — the .ipynb file on disk is the single source of truth. Follow this checklist to stay in sync.

### Before every edit session

- [ ] Read the .ipynb from disk (the human's version)
- [ ] Read your livebook session (your version)
- [ ] Print both side by side — compare cell count, source previews, char counts
- [ ] Identify what the human changed (new cells, edited cells, deleted cells)
- [ ] Absorb their changes into your session (update cell source, add/remove cells)
- [ ] Run any cells you updated to verify they still work

### After every edit session

- [ ] Save to .ipynb via `nb.save_local()` immediately — do NOT continue making more changes without saving first
- [ ] Save your session via `nb.save_session()`
- [ ] Tell the human to refresh their browser to pick up your changes (they lose viewer outputs but kernel state is preserved)

### Conflict resolution rules

1. **Human edits always win** — if you both changed the same cell, take the human's version and reapply your logic on top
2. **Save before you build** — always save to .ipynb before starting a new batch of changes. Drifting ahead without saving is what causes desync
3. **Match cells by content** — livebook tracks cells by tag, the .ipynb tracks by cell ID. There is no shared identifier. Match cells by comparing source content (fragile but workable for v1)
4. **If a cell can't be matched** — ask the human what changed rather than guessing

### What to know

- The kernel is shared and stays alive — losing outputs in the browser on refresh is cosmetic, not a real problem
- The human must save (Ctrl+S) in the Jupyter UI before you can see their changes on disk
- Your session can drift ahead of the .ipynb if you keep editing without saving — this is the #1 cause of desync
