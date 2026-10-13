"""Small helpers shared by the tests. Functions only (the project has no classes)."""

import tempfile
from contextlib import contextmanager
from types import SimpleNamespace

import data_manager as dm


@contextmanager
def temp_data_dir():
    """Points the Data Manager at an empty temporary folder for one test, so
    no test ever touches real accounts or saved files."""
    with tempfile.TemporaryDirectory() as folder:
        old_dir = dm.DATA_DIR
        dm.DATA_DIR = folder
        dm.set_active_user(None)
        try:
            yield folder
        finally:
            dm.set_active_user(None)
            dm.DATA_DIR = old_dir


@contextmanager
def raises(expected):
    """`with raises(ValueError) as caught:` fails the test unless the block
    raises `expected`; the error is then available as caught.exception."""
    caught = SimpleNamespace(exception=None)
    try:
        yield caught
    except expected as error:
        caught.exception = error
    else:
        raise AssertionError(f"{expected.__name__} was not raised")
