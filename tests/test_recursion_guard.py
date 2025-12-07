import pytest

from sentientos.consciousness.recursion_guard import (
    RecursionGuard,
    RecursionLimitExceeded,
)


def test_recursion_guard_counts_depth():
    guard = RecursionGuard(max_depth=3)

    assert guard.depth == 0
    with guard.enter():
        assert guard.depth == 1
        with guard.enter():
            assert guard.depth == 2
        assert guard.depth == 1
    assert guard.depth == 0


def test_recursion_guard_exceeds_max_depth():
    guard = RecursionGuard(max_depth=1)

    with guard.enter():
        with pytest.raises(RecursionLimitExceeded):
            with guard.enter():
                pass

    assert guard.depth == 0


def test_recursion_guard_depth_resets_after_error():
    guard = RecursionGuard(max_depth=1)

    with pytest.raises(RecursionLimitExceeded):
        with guard.enter():
            with guard.enter():
                pass

    assert guard.depth == 0
