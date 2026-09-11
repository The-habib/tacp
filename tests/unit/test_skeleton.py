import re

import tacp


def test_package_metadata() -> None:
    assert hasattr(tacp, "__version__")
    assert isinstance(tacp.__version__, str)
    assert re.match(r"^\d+\.\d+\.\d+", tacp.__version__)
