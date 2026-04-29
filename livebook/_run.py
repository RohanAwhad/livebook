"""Thin entry point: Python with livebook available."""

import runpy
import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: livebook-run -c 'code' | livebook-run script.py")
        sys.exit(1)

    if sys.argv[1] == "-c":
        if len(sys.argv) < 3:
            print("Usage: livebook-run -c 'code'")
            sys.exit(1)
        exec(sys.argv[2])
    else:
        sys.argv = sys.argv[1:]
        runpy.run_path(sys.argv[0], run_name="__main__")
