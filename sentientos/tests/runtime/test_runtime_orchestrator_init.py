import pytest
from sentientos.runtime.runtime import Runtime


pytestmark = pytest.mark.no_legacy_skip


def test_runtime_initializes_innerworld():
    runtime = Runtime()

    assert runtime.innerworld is not None
    assert runtime.core_loop.innerworld is runtime.innerworld


def test_runtime_run_cycle_does_not_raise():
    runtime = Runtime()

    result = runtime.run_cycle({"errors": 0})

    assert "innerworld" in result
