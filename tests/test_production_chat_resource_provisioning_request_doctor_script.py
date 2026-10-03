from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import scripts.production_chat_resource_provisioning_request_doctor as cli
from sentientos.installation_state import InstallationStateRegistry
from sentientos.production_chat_resource_provisioning_request_doctor import (
    ProductionChatResourceProvisioningRequestDoctorReport,
)

pytestmark = pytest.mark.no_legacy_skip


def _report(shape: str, status: str) -> ProductionChatResourceProvisioningRequestDoctorReport:
    return ProductionChatResourceProvisioningRequestDoctorReport({
        "doctor_report_id": "publication-doctor-test",
        "overall_doctor_status": status,
        "custody_shape": shape,
        "publication_complete": shape == "complete_pair",
        "next_inspection_guidance": "separately_governed_recovery_review_required",
    })


@pytest.mark.parametrize(("shape", "status"), [
    ("complete_pair", "publication_doctor_complete"),
    ("bare_request", "publication_doctor_incomplete"),
    ("orphan_receipt", "publication_doctor_contradictory"),
])
def test_cli_emits_normal_diagnostic_states(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], shape: str, status: str,
) -> None:
    class Registry:
        def open(self, identity: object, *, create: bool) -> object:
            assert create is False
            return object()
    monkeypatch.setattr(InstallationStateRegistry, "system", classmethod(lambda cls: Registry()))
    monkeypatch.setattr(cli, "diagnose_production_chat_resource_provisioning_request_publication",
                        lambda handle, selected: _report(shape, status))
    assert cli.main(["--installation-identity", "installation", "--resource-provisioning-id", "doctor"]) == 0
    assert json.loads(capsys.readouterr().out)["custody_shape"] == shape


def test_cli_grammar_is_narrow_and_summary_is_deterministic() -> None:
    parser = cli.build_parser()
    options = {option for action in parser._actions for option in action.option_strings}
    assert options == {"-h", "--help", "--installation-identity",
                       "--resource-provisioning-id", "--summary"}
    source = Path(cli.__file__).read_text()
    assert "InstallationStateRegistry.system()" in source
    assert "create=False" in source
    assert "prepare_provisioning_intent" not in source
    assert "execute_provisioning_intent" not in source


def test_cli_malformed_identity_is_bounded_without_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["--installation-identity", "../bad", "--resource-provisioning-id", "doctor"]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "status": "publication_doctor_blocked", "reason_code": "invalid_installation_identity"}
    assert "Traceback" not in captured.out + captured.err
