from __future__ import annotations
import json, sys
from pathlib import Path
from scripts.build_host_local_diagnostic_lifecycle_closure import main
from tests.test_host_local_diagnostic_lifecycle_closure import _closed, NOW
import pytest
pytestmark=pytest.mark.no_legacy_skip

def test_cli_build_validate_and_latest_summary(tmp_path:Path,monkeypatch,capsys)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); ed=json.loads((Path(execution.bundle_root)/"bundle_manifest.json").read_text())["bundle_digest"]; rd=json.loads((Path(rollback.bundle_root)/"bundle_manifest.json").read_text())["bundle_digest"]; out=tmp_path/"cli"
    monkeypatch.setattr(sys,"argv",["closure","build","--execution-bundle-root",execution.bundle_root,"--execution-bundle-digest",ed,"--rollback-bundle-root",rollback.bundle_root,"--rollback-bundle-digest",rd,"--closure-time",NOW,"--output-root",str(out)])
    assert main()==0; built=json.loads(capsys.readouterr().out)
    monkeypatch.setattr(sys,"argv",["closure","validate","--packet-root",built["packet_root"]]); assert main()==0; capsys.readouterr()
    monkeypatch.setattr(sys,"argv",["closure","latest-summary","--output-root",str(out)]); assert main()==0 and json.loads(capsys.readouterr().out)["status"]=="host_local_diagnostic_lifecycle_closure_valid"
