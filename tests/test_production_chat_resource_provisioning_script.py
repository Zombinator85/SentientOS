from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

import scripts.production_chat_resource_provisioning as script
from sentientos.production_chat_resource_provisioning_actuator import prepare_provisioning_intent
from tests.test_production_chat_resource_provisioning_actuator import packet

pytestmark = pytest.mark.no_legacy_skip


def test_cli_has_only_prepare_create_and_one_request_path() -> None:
    parser = script.build_parser()
    subcommands = next(action for action in parser._actions if action.dest == "command").choices
    assert set(subcommands) == {"prepare", "create"}
    source = inspect.getsource(script)
    for forbidden in ("--principal", "--provenance", "--catalog", "--registry", "--policy",
                      "--source-root", "--state-root", "--destination", "--force",
                      "--create-installation", "cleanup", "renew"):
        assert forbidden not in source


def test_prepare_json_and_missing_or_wrong_confirmation_are_bounded(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    raw, _, _ = packet(tmp_path); path = tmp_path / "request.json"; path.write_bytes(raw)
    assert script.main(["prepare", "--request", str(path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "production_resource_provisioning_intent_ready"
    assert output["intent"]["intent_digest"] == prepare_provisioning_intent(raw).intent_digest
    assert script.main(["create", "--request", str(path)]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "status": "production_resource_provisioning_blocked",
        "reason_code": "invalid_confirmation_digest",
    }
    assert script.main(["create", "--request", str(path),
                        "--confirm-intent-digest", "0" * 64]) == 2
    assert json.loads(capsys.readouterr().out)["reason_code"] == "intent_confirmation_mismatch"
