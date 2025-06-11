from __future__ import annotations

"""SentientOS package bootstrap."""

import os
import pkgutil

__version__: str = "0.1.1"

# Extend the package search path so that top-level modules can be imported as
# ``sentientos.<module>`` without manual ``sys.path`` manipulation in tests.
_HERE = os.path.abspath(os.path.dirname(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir))
__path__ = pkgutil.extend_path(__path__, __name__)
if _ROOT not in __path__:
    __path__.append(_ROOT)

