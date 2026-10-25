import pytest
from semver.parser import compare, parse_version


def test_major_version_comparison():
    assert compare("2.0.0", "1.0.0") == 1
    assert compare("1.0.0", "2.0.0") == -1


def test_minor_version_single_digits():
    assert compare("1.2.0", "1.3.0") == -1
    assert compare("1.3.0", "1.2.0") == 1


def test_equal_versions():
    assert compare("1.0.0", "1.0.0") == 0
    assert compare("3.5.7", "3.5.7") == 0


def test_invalid_version_raises():
    with pytest.raises(ValueError):
        parse_version("1.0")
    with pytest.raises(ValueError):
        parse_version("1.2.3.4")
