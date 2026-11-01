from __future__ import annotations

import pytest

from sentientos.toml_compat import tomllib

pytestmark = pytest.mark.no_legacy_skip


def test_toml_compat_exports_the_selected_parser() -> None:
    assert tomllib.loads("answer = 42\\n") == {"answer": 42}
