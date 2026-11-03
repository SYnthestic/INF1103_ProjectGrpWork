"""Small helpers shared by the tests."""

import tempfile
from contextlib import contextmanager
from types import SimpleNamespace

from data_manager import DataManager
from logic_manager import GrantScheme


@contextmanager
def temp_data_dir():
    """A DataManager pointed at an empty temporary folder for one test, so no
    test ever touches real accounts or saved files. Use as
    `with temp_data_dir() as (dm, folder):`."""
    with tempfile.TemporaryDirectory() as folder:
        yield DataManager(data_dir=folder), folder


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


def calculate_subsidy(base_amount, rate, cap):
    """Subsidy for an arbitrary rate and cap, using a throw-away GrantScheme."""
    scheme = type("TestScheme", (GrantScheme,), {"name": "test", "rate": rate, "cap": cap})
    return scheme().calculate_subsidy(base_amount)
