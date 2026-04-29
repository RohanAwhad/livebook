"""Manual test of all livebook functionality against a live Jupyter server."""

from livebook import Notebook, JupyterConnection, Cell, CellResult, CellError

URL = "http://localhost:8889"
TOKEN = "test-token"

conn = JupyterConnection(url=URL, token=TOKEN)

# ===== 1. Manual kernel lifecycle (no context manager) =====
print("=== 1. Manual kernel start/stop ===")
kernel_id = conn.start_kernel("python3")
print(f"Started kernel: {kernel_id}")

result = conn.execute(kernel_id, "print('hello from manual kernel')")
print(f"Execute result: success={result.success}, stdout={result.stdout!r}")

conn.stop_kernel(kernel_id)
print("Kernel stopped.\n")

# ===== 2. Context manager lifecycle =====
print("=== 2. Context manager lifecycle ===")
with Notebook(conn, kernel="python3") as nb:
    print(f"Kernel started via context manager")

    # --- 2a. Add cells, check return values ---
    print("\n--- 2a. add_code / add_markdown ---")
    setup = nb.add_code("import math", tag="setup")
    print(f"add_code returned: {type(setup).__name__}, tag={setup.tag!r}")
    assert isinstance(setup, Cell)
    assert setup.tag.startswith("setup-")
    assert setup.source == "import math"
    assert setup.cell_type == "code"

    title = nb.add_markdown("# Test Notebook", tag="title")
    print(f"add_markdown returned: tag={title.tag!r}, cell_type={title.cell_type!r}")
    assert title.cell_type == "markdown"

    # --- 2b. Tag uniqueness ---
    print("\n--- 2b. Tag uniqueness ---")
    dup1 = nb.add_code("x = 1", tag="dup")
    dup2 = nb.add_code("x = 2", tag="dup")
    print(f"dup1.tag={dup1.tag!r}, dup2.tag={dup2.tag!r}")
    assert dup1.tag != dup2.tag
    assert dup1.tag.startswith("dup-")
    assert dup2.tag.startswith("dup-")

    # --- 2c. Tags property (insertion order) ---
    print("\n--- 2c. tags property ---")
    print(f"tags = {nb.tags}")
    assert len(nb.tags) == 4
    assert nb.tags[0] == setup.tag
    assert nb.tags[1] == title.tag

    # --- 2d. Access by tag (__getitem__) ---
    print("\n--- 2d. Access by tag ---")
    cell = nb[setup.tag]
    assert cell is setup
    print(f"nb[{setup.tag!r}] is same object: {cell is setup}")

    # bad tag raises KeyError
    try:
        nb["nonexistent-tag"]
        assert False, "Should have raised KeyError"
    except KeyError as e:
        print(f"KeyError on bad tag: {e}")

    # --- 2e. Run single cell ---
    print("\n--- 2e. Run single cell ---")
    result = nb.run(setup.tag)
    print(f"run({setup.tag!r}): success={result.success}, stdout={result.stdout!r}")
    assert result.success
    assert isinstance(result, CellResult)

    # cell with stdout + return value
    calc = nb.add_code("print('computing...')\nmath.pi", tag="calc")
    result = nb.run(calc.tag)
    print(f"run({calc.tag!r}): stdout={result.stdout!r}, result={result.result!r}")
    assert result.success
    assert "computing..." in result.stdout
    assert result.result is not None  # should be repr of math.pi

    # cell with error
    bad = nb.add_code("1 / 0", tag="bad")
    result = nb.run(bad.tag)
    print(f"run({bad.tag!r}): success={result.success}, error={result.error}")
    assert not result.success
    assert isinstance(result.error, CellError)
    assert result.error.ename == "ZeroDivisionError"

    # --- 2f. Cell rewriting + staleness ---
    print("\n--- 2f. Cell rewriting + staleness ---")
    print(f"Before rewrite: setup.result_stale={setup.result_stale}")
    assert not setup.result_stale

    setup.source = "import os"
    print(f"After rewrite: setup.result_stale={setup.result_stale}")
    assert setup.result_stale

    # repr should contain the disclaimer
    repr_str = repr(setup)
    print(f"repr contains disclaimer: {'previous version' in repr_str}")
    assert "previous version" in repr_str

    # re-run clears staleness
    nb.run(setup.tag)
    print(f"After re-run: setup.result_stale={setup.result_stale}")
    assert not setup.result_stale

    # --- 2g. insert_before / insert_after ---
    print("\n--- 2g. insert_before / insert_after ---")
    preamble = nb.insert_before(setup.tag, code="# preamble", tag="preamble")
    print(f"insert_before: preamble.tag={preamble.tag!r}")
    assert isinstance(preamble, Cell)

    load = nb.insert_after(setup.tag, code="data = [1,2,3]", tag="load")
    print(f"insert_after: load.tag={load.tag!r}")

    tags = nb.tags
    preamble_idx = tags.index(preamble.tag)
    setup_idx = tags.index(setup.tag)
    load_idx = tags.index(load.tag)
    print(f"Order: preamble@{preamble_idx}, setup@{setup_idx}, load@{load_idx}")
    assert preamble_idx == setup_idx - 1
    assert load_idx == setup_idx + 1

    # --- 2h. remove ---
    print("\n--- 2h. remove ---")
    nb.remove(bad.tag)
    print(f"Removed {bad.tag!r}, tags now: {nb.tags}")
    assert bad.tag not in nb.tags

    # --- 2i. run_all ---
    print("\n--- 2i. run_all ---")
    results = nb.run_all()
    print(f"run_all returned {len(results)} results for code cells")
    # should only include code cells, not markdown
    assert title.tag not in results
    for tag, res in results.items():
        print(f"  {tag}: success={res.success}")

    # --- 2j. save_local ---
    print("\n--- 2j. save_local ---")
    nb.save_local("test_output.ipynb")
    print("Saved to test_output.ipynb")

    # --- 2k. save (remote) ---
    print("\n--- 2k. save (remote) ---")
    nb.save("test_remote.ipynb")
    print("Saved to Jupyter server as test_remote.ipynb")

print("Context manager exited (kernel stopped).\n")

# ===== 3. Load existing notebook =====
print("=== 3. Load existing notebook ===")
with Notebook.open(conn, "test_remote.ipynb") as nb2:
    print(f"Loaded notebook, tags: {nb2.tags}")
    assert len(nb2.tags) > 0

    # run a cell from the loaded notebook
    first_code_tag = None
    for t in nb2.tags:
        if nb2[t].cell_type == "code":
            first_code_tag = t
            break

    if first_code_tag:
        result = nb2.run(first_code_tag)
        print(f"Ran loaded cell {first_code_tag!r}: success={result.success}")

print("Loaded notebook context exited.\n")

# ===== 4. Stderr capture =====
print("=== 4. Stderr capture ===")
with Notebook(conn) as nb3:
    cell = nb3.add_code("import sys; sys.stderr.write('warning!\\n')", tag="stderr-test")
    result = nb3.run(cell.tag)
    print(f"stderr={result.stderr!r}")
    assert "warning!" in result.stderr

print("\n=== ALL TESTS PASSED ===")
