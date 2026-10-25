from importlib.metadata import version

import histra


def test_public_version_comes_from_distribution_metadata() -> None:
    assert histra.__version__ == version("histra-python") == "1.6.2"
