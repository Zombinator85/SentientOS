from scripts.pytest_airlock_guard import _line_has_pytest_command


def test_airlock_guard_distinguishes_commands_from_prose_and_explicit_opt_in():
    assert not _line_has_pytest_command("pytest is invoked after setup")
    assert not _line_has_pytest_command(
        "SENTIENTOS_ALLOW_NAKED_PYTEST=1 python -m pytest -q")
    assert _line_has_pytest_command("python -m pytest -q tests")
    assert _line_has_pytest_command("pytest tests/test_example.py")
