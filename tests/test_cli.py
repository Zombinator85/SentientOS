import json

import pytest

from cli import sentientos_cli
from sentientos.consciousness.cognitive_state import COGNITIVE_SNAPSHOT_VERSION


pytestmark = pytest.mark.no_legacy_skip


class StubOrchestrator:
    def __init__(self, profile=None, approval=False):
        self.profile = profile
        self.approval = approval

    def run_consciousness_cycle(self):
        return {"status": "cycle"}

    def ssa_dry_run(self):
        return {"status": "dry"}

    def ssa_execute(self, relay=None):
        return {"status": "executed", "approval": self.approval}

    def ssa_prefill_827(self):
        return {"status": "prefilled", "approval": self.approval}


def test_cli_cycle_smoke(monkeypatch, capsys):
    monkeypatch.setattr(sentientos_cli, "SentientOrchestrator", StubOrchestrator)

    sentientos_cli.main(["cycle"])

    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "cycle"


def test_cli_dry_run(monkeypatch, capsys):
    monkeypatch.setattr(sentientos_cli, "SentientOrchestrator", StubOrchestrator)
    monkeypatch.setattr(sentientos_cli, "load_profile_json", lambda path: {"p": path})

    sentientos_cli.main(["ssa", "dry-run", "--profile", "profile.json"])

    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "dry"


def test_cli_requires_approval(monkeypatch, capsys):
    with pytest.raises(SystemExit):
        sentientos_cli.main(["ssa", "execute", "--profile", "profile.json"])

    output = json.loads(capsys.readouterr().out)
    assert output["error"] == "approval_required"


def test_cli_review_redacts(monkeypatch, capsys):
    bundle = {
        "execution_log": [{"page": "home", "value": "secret"}],
        "profile": {"first_name": "Secret"},
        "status": "done",
        "pages": ["home"],
    }

    monkeypatch.setattr(sentientos_cli, "_load_bundle", lambda path: bundle)

    sentientos_cli.main(["ssa", "review", "--bundle", "bundle.json"])

    output = json.loads(capsys.readouterr().out)
    assert output["execution_log"][0]["value"] == "***"
    assert output["profile"]["first_name"] == "***"


def test_cli_integrity(monkeypatch, capsys):
    monkeypatch.setattr(sentientos_cli, "compute_system_diagnostics", lambda: {"ok": True})

    sentientos_cli.main(["integrity"])

    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True


def test_cli_cognition_status_expect_version(monkeypatch, capsys):
    snapshot = {"cognitive_snapshot_version": COGNITIVE_SNAPSHOT_VERSION, "ok": True}
    monkeypatch.setattr(sentientos_cli, "_cognitive_status_snapshot", lambda: snapshot)

    sentientos_cli.main(["cognition", "status", "--expect-version", str(COGNITIVE_SNAPSHOT_VERSION)])

    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True


def test_cli_cognition_status_expect_version_mismatch(monkeypatch, capsys):
    snapshot = {"cognitive_snapshot_version": COGNITIVE_SNAPSHOT_VERSION + 1, "ok": True}
    monkeypatch.setattr(sentientos_cli, "_cognitive_status_snapshot", lambda: snapshot)

    with pytest.raises(SystemExit):
        sentientos_cli.main(
            ["cognition", "status", "--expect-version", str(COGNITIVE_SNAPSHOT_VERSION)]
        )

    output = json.loads(capsys.readouterr().out)
    assert "error" in output
