from __future__ import annotations

import importlib

import pytest


def _module_without_entrypoint_rituals(monkeypatch: pytest.MonkeyPatch):
    import sentientos.privilege as privilege

    monkeypatch.setattr(privilege, "require_admin_banner", lambda: None)
    monkeypatch.setattr(privilege, "require_lumos_approval", lambda: None)
    module = importlib.import_module("scripts.quota_alert")
    return importlib.reload(module)


@pytest.mark.no_legacy_skip
@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "-0.01", "1.01"])
def test_threshold_parser_rejects_nonfinite_and_out_of_range_values(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    module = _module_without_entrypoint_rituals(monkeypatch)

    with pytest.raises(module.argparse.ArgumentTypeError, match="finite"):
        module._threshold_arg(value)


@pytest.mark.no_legacy_skip
@pytest.mark.parametrize("value", ["0", "0.1", "1"])
def test_threshold_parser_accepts_fraction_boundaries(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    module = _module_without_entrypoint_rituals(monkeypatch)

    assert module._threshold_arg(value) == float(value)


@pytest.mark.no_legacy_skip
@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "-0.01", "1.01"])
def test_cli_rejects_invalid_threshold_before_reading_usage_or_sending_alert(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    module = _module_without_entrypoint_rituals(monkeypatch)
    monkeypatch.setattr(
        module,
        "load_latest_usage",
        lambda _path: pytest.fail("invalid threshold must be rejected before reading usage"),
    )
    monkeypatch.setattr(
        module,
        "send_slack",
        lambda *_args: pytest.fail("invalid threshold must not send an alert"),
    )

    with pytest.raises(SystemExit):
        module.main(["--threshold", value, "--slack-webhook", "https://example.invalid"])
