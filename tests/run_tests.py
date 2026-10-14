"""Runs every test function (names starting with test_) in tests/test_*.py.

    python tests/run_tests.py        short report
    python tests/run_tests.py -v     one line per test

Plain functions and plain assert statements only, so there are no classes and
nothing to install. (pytest can also run these files unchanged.)
"""

import glob
import importlib
import inspect
import os
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_tests():
    """Yields (test name, function) for every test function, in file order."""
    for path in sorted(glob.glob(os.path.join(ROOT, "tests", "test_*.py"))):
        module = importlib.import_module("tests." + os.path.basename(path)[:-3])
        functions = [
            (name, function)
            for name, function in vars(module).items()
            if name.startswith("test_")
            and inspect.isfunction(function)
            and function.__module__ == module.__name__
        ]
        functions.sort(key=lambda item: item[1].__code__.co_firstlineno)
        for name, function in functions:
            yield f"{module.__name__.split('.')[-1]}::{name}", function


def run(verbose=False):
    """Runs all tests and returns the number that failed."""
    failures = []
    total = 0
    started = time.time()
    for name, function in find_tests():
        total += 1
        try:
            function()
        except Exception:
            failures.append((name, traceback.format_exc()))
            print(
                f"FAIL  {name}" if verbose else "F",
                end="\n" if verbose else "",
                flush=True,
            )
        else:
            print(
                f"ok    {name}" if verbose else ".",
                end="\n" if verbose else "",
                flush=True,
            )
    print()
    for name, trace in failures:
        print("=" * 70)
        print(f"FAIL: {name}")
        print(trace)
    print("-" * 70)
    print(f"Ran {total} tests in {time.time() - started:.2f}s")
    print("OK" if not failures else f"FAILED ({len(failures)} failed)")
    return len(failures)


if __name__ == "__main__":
    sys.path.insert(0, ROOT)
    sys.exit(1 if run(verbose="-v" in sys.argv) else 0)
