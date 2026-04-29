# livebook

Python library that lets AI agents operate Jupyter notebooks programmatically —
creating cells, running them, checking results, updating them — without dealing
with raw .ipynb JSON.

## Install

```bash
uv tool install "livebook @ git+https://github.com/RohanAwhad/livebook.git"
```

## Quick start

```bash
livebook-run -c "
from livebook import Notebook, JupyterConnection

conn = JupyterConnection(url='http://localhost:8888', token='')
with Notebook(conn) as nb:
    cell = nb.add_code('print(1 + 1)', tag='hello')
    result = nb.run(cell.tag)
    print(result.stdout)  # '2\n'
    nb.save_local('hello.ipynb')
"
```

## Why

Agents need to run code iteratively — write a cell, check the output, fix it,
continue. livebook gives them tag-based cell management, staleness tracking,
and session persistence across turns.

## Docs

See DESIGN.md for architecture and CLAUDE_SKILL.md for agent usage patterns.
