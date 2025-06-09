import sentientos.core as sc
from sentientos import __version__


def test_core_greet():
    c = sc.Core("tester")
    assert c.greet() == "Hello from tester"


def test_version_str():
    assert isinstance(__version__, str)
