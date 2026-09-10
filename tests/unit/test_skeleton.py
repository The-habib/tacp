"""Unit sanity test verifying TACP package skeleton."""

import tacp


def test_package_metadata() -> None:
    assert hasattr(tacp, "__version__")
    assert isinstance(tacp.__version__, str)
    assert tacp.__version__.startswith("0.1.0")
