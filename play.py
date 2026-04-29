"""Test: verify tags survive save_local → json.load and Notebook.open round-trip."""
import json
import sys
from livebook import JupyterConnection, Notebook

SAVE_PATH = "/tmp/test_tags.ipynb"

# --- Part 1: Create notebook, add cells with tags, save locally ---
conn = JupyterConnection("http://localhost:8888", token="")
nb = Notebook(conn)
nb.start()

c1 = nb.add_code("x = 1", tag="setup")
c2 = nb.add_code("y = x + 1", tag="transform")
c3 = nb.add_code("print(y)", tag="plot")

written_tags = [c1.tag, c2.tag, c3.tag]
print("=== WRITTEN TAGS ===")
for t in written_tags:
    print(f"  {t}")

nb.save_local(SAVE_PATH)
nb.stop()
print(f"\nSaved to {SAVE_PATH}")

# --- Part 2: Read raw .ipynb with json.load ---
print("\n=== RAW .ipynb CELL METADATA (json.load) ===")
with open(SAVE_PATH) as f:
    raw = json.load(f)

raw_tags = []
for i, cell in enumerate(raw["cells"]):
    tags = cell.get("metadata", {}).get("tags", [])
    raw_tags.append(tags)
    print(f"  cell[{i}]: metadata.tags = {tags}")

# --- Part 3: Load back via Notebook.open ---
# Notebook.open reads from Jupyter server, so we need to upload first.
# Instead, let's simulate what open() does: parse with nbformat.
import nbformat

print("\n=== Notebook.open() SIMULATION (nbformat parse) ===")
with open(SAVE_PATH) as f:
    nb_node = nbformat.read(f, as_version=4)

recovered_tags = []
for i, nb_cell in enumerate(nb_node.cells):
    tags = nb_cell.metadata.get("tags", [])
    tag = tags[0] if tags else f"cell-{i}-????"
    recovered_tags.append(tag)
    print(f"  cell[{i}]: recovered tag = {tag!r}")

# --- Part 4: Comparison ---
print("\n=== COMPARISON ===")
all_match = True
for i, (w, r_list, rec) in enumerate(zip(written_tags, raw_tags, recovered_tags)):
    raw_first = r_list[0] if r_list else "<MISSING>"
    match_raw = (w == raw_first)
    match_rec = (w == rec)
    status = "OK" if (match_raw and match_rec) else "MISMATCH"
    if not (match_raw and match_rec):
        all_match = False
    print(f"  cell[{i}]: written={w!r}  raw={raw_first!r}  recovered={rec!r}  [{status}]")

print(f"\nRound-trip reliable: {all_match}")
