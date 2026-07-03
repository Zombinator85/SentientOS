from __future__ import annotations

import json
import pytest
import subprocess
import sys

pytestmark = pytest.mark.no_legacy_skip

from tests.test_codex_workcell_storage_operator_consent_evidence_dossier_verifier import dossier

SCRIPT="scripts/verify_codex_workcell_storage_operator_consent_evidence_dossier.py"

def run(*args):
    return subprocess.run([sys.executable, SCRIPT, *args], text=True, capture_output=True)

def test_cli_writes_json_markdown_and_summary_deterministically(tmp_path):
    path=tmp_path/"d.json"; path.write_text(json.dumps(dossier(), sort_keys=True), encoding="utf-8")
    out=tmp_path/"out.json"; md=tmp_path/"out.md"
    first=run("--storage-operator-consent-evidence-dossier-json", str(path), "--output", str(out), "--markdown-output", str(md), "--summary")
    assert first.returncode == 0, first.stderr
    report=json.loads(out.read_text())
    assert report["verification_status"] == "storage_operator_consent_evidence_dossier_verified"
    assert "verification_status" in first.stdout
    json1=out.read_text(); md1=md.read_text()
    second=run("--storage-operator-consent-evidence-dossier-json", str(path), "--output", str(out), "--markdown-output", str(md), "--summary")
    assert second.returncode == 0
    assert out.read_text() == json1 and md.read_text() == md1


def test_cli_input_errors_exit_2(tmp_path):
    out=tmp_path/"out.json"
    assert run("--storage-operator-consent-evidence-dossier-json", str(tmp_path/"missing.json"), "--output", str(out)).returncode == 2
    bad=tmp_path/"bad.json"; bad.write_text("{", encoding="utf-8")
    assert run("--storage-operator-consent-evidence-dossier-json", str(bad), "--output", str(out)).returncode == 2
    arr=tmp_path/"arr.json"; arr.write_text("[]", encoding="utf-8")
    assert run("--storage-operator-consent-evidence-dossier-json", str(arr), "--output", str(out)).returncode == 2
    good=tmp_path/"good.json"; good.write_text(json.dumps(dossier()), encoding="utf-8")
    assert run("--storage-operator-consent-evidence-dossier-json", str(good), "--storage-policy-verifier-json", str(bad), "--output", str(out)).returncode == 2


def test_markdown_escaping_handles_pipes_and_newlines(tmp_path):
    d=dossier(); d["storage_operator_consent_evidence_dossier_id"]="a|b\nc"
    path=tmp_path/"d.json"; path.write_text(json.dumps(d), encoding="utf-8")
    out=tmp_path/"out.json"; md=tmp_path/"out.md"
    assert run("--storage-operator-consent-evidence-dossier-json", str(path), "--output", str(out), "--markdown-output", str(md)).returncode == 0
    text=md.read_text()
    assert "a\\|b<br>c" in text
