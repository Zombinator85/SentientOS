from __future__ import annotations

import importlib

import pytest


def _module_without_entrypoint_rituals(monkeypatch: pytest.MonkeyPatch):
    import sentientos.privilege as privilege

    monkeypatch.setattr(privilege, "require_admin_banner", lambda: None)
    monkeypatch.setattr(privilege, "require_lumos_approval", lambda: None)
    return importlib.import_module("scripts.wait_for_health")


@pytest.mark.no_legacy_skip
@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "-1"])
def test_timeout_argument_rejects_nonfinite_and_negative_values(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    module = _module_without_entrypoint_rituals(monkeypatch)

    with pytest.raises(module.argparse.ArgumentTypeError, match="finite"):
        module._timeout_arg(value)


@pytest.mark.no_legacy_skip
@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_environment_timeout_uses_finite_argument_validation(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    module = _module_without_entrypoint_rituals(monkeypatch)
    monkeypatch.setenv("WAIT_TIMEOUT", value)

    with pytest.raises(SystemExit):
        module.parse_args(["--url", "http://127.0.0.1/health"])


@pytest.mark.no_legacy_skip
@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_cli_timeout_uses_finite_argument_validation(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    module = _module_without_entrypoint_rituals(monkeypatch)

    with pytest.raises(SystemExit):
        module.parse_args(
            ["--url", "http://127.0.0.1/health", "--max-wait", value]
        )


@pytest.mark.no_legacy_skip
@pytest.mark.parametrize("timeout,interval", [(float("inf"), 2.0), (float("nan"), 2.0), (1.0, float("inf"))])
def test_wait_for_rejects_nonfinite_limits_before_network_access(
    monkeypatch: pytest.MonkeyPatch, timeout: float, interval: float
) -> None:
    module = _module_without_entrypoint_rituals(monkeypatch)
    monkeypatch.setattr(
        module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: pytest.fail("health endpoint must not be contacted"),
    )

    with pytest.raises(ValueError, match="finite"):
        module.wait_for("http://127.0.0.1/health", timeout=timeout, interval=interval)
