from __future__ import annotations

import json
import signal
import subprocess
from pathlib import Path

import pytest

from scripts.provenance_hash_chain import compute_provenance_hash
from sentientos import governed_improvement_signal_plane as signals
from sentientos import maintenance_health_probe as probe
from sentientos import maintenance_candidate as candidates

pytestmark = pytest.mark.no_legacy_skip

SHA = "2ed519bbe1115cf523f87268493402196526bedb"
NODE = "tests/test_maintenance_health_probe.py::test_passing_probe_writes_only_receipt"


def _config(tmp_path: Path) -> dict[str, object]:
    state=tmp_path/"state"; output=tmp_path/"signals"
    state.mkdir(mode=0o700); output.mkdir(mode=0o700)
    return {"schema_version":probe.CONFIG_SCHEMA,"repository_identity":"SentientOS","repository_root":str(Path.cwd()),"base_sha":SHA,"pytest_node_ids":[NODE],"probe_timeout_seconds":10,"maximum_failing_records":2,"probe_state_root":str(state),"governed_signal_output_root":str(output),"declared_validation_expectations":["python -m scripts.run_tests -q "+NODE],"requested_maintenance_authority_classes":["sentientos"],"declared_constraints":["no model","no network"],"estimated_file_count":3,"estimated_changed_line_count":300,"estimated_implementation_seconds":1200,"estimated_validation_seconds":600,"evaluation_time":"2026-08-07T00:00:00Z","receipt_journal_path":str(state/"receipts.jsonl")}


def _write_run(cfg: dict[str, object], *, failed: bool, tampered: bool=False) -> None:
    root=Path(str(cfg["repository_root"])); run=root/"glow/test_runs"; run.mkdir(parents=True,exist_ok=True)
    report=run/"test_failure_digest.json"
    if failed:
        report.write_text(json.dumps({"failure_groups":[{"nodeid":NODE,"file":"tests/test_maintenance_health_probe.py","line":42,"message":"bounded failure","failure_class":"assertion","count":1}]}))
    payload={"schema_version":1,"pytest_exit_code":1 if failed else 0,"tests_selected":1,"tests_executed":1,"tests_passed":0 if failed else 1,"tests_failed":1 if failed else 0,"metrics_status":"ok","reporter_ok":True,"exit_reason":"pytest-failed" if failed else "success","junitxml_path":str(run/"unused.xml"),"failure_report_path":str(report) if failed else None,"git_sha":SHA,"repo_root":str(root),"pytest_args":["-q",NODE],"selected_node_ids":[NODE],"prev_provenance_hash":None,"hash_algo":"sha256"}
    payload["provenance_hash"]=compute_provenance_hash(payload,None)
    if tampered: payload["tests_failed"]=9
    (run/"test_run_provenance.json").write_text(json.dumps(payload))


def _ready(monkeypatch: pytest.MonkeyPatch, cfg: dict[str, object], *, failed: bool, tampered: bool=False) -> None:
    monkeypatch.setattr(probe,"doctor",lambda config:{"status":"health_probe_ready"})
    def run(*args: object, **kwargs: object) -> int:
        _write_run(cfg,failed=failed,tampered=tampered)
        return 1 if failed else 0
    monkeypatch.setattr(probe,"_run_bounded",run)


def test_passing_probe_writes_only_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg=_config(tmp_path); _ready(monkeypatch,cfg,failed=False)
    result=probe.probe_once(cfg)
    assert result["status"]=="health_probe_healthy"
    assert list((tmp_path/"signals").iterdir())==[]
    assert probe.inspect(cfg)["receipt_count"]==1


def test_failure_produces_valid_collector_compatible_evaluation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg=_config(tmp_path); _ready(monkeypatch,cfg,failed=True)
    result=probe.probe_once(cfg); assert result["status"]=="health_probe_findings", result
    payload=json.loads(Path(result["governed_signal_path"]).read_text())
    valid, reasons=signals.validate_evaluation(payload)
    assert valid, reasons
    row=payload["batch"]["signals"][0]
    assert row["spec_id"]==NODE and row["subject_path"]=="tests/test_maintenance_health_probe.py"
    assert row["declared_validation_expectations"]==cfg["declared_validation_expectations"]
    assert row["requested_authority_classes"]==cfg["requested_maintenance_authority_classes"]
    assert row["declared_constraints"]==cfg["declared_constraints"]
    assert [row[x] for x in ("estimated_file_count","estimated_changed_line_count","estimated_implementation_seconds","estimated_validation_seconds")]==[3,300,1200,600]
    # The actual collector parser/adaptor sees a canonical candidate without an
    # operator-authored candidate manifest or invoking collection.
    candidate=candidates.adapt_governed_signal(signals.ImprovementSignal(**row),base_repository_sha=SHA)
    assert candidate.source_kind=="governed_improvement_signal"


def test_invocation_time_overrides_static_time_without_changing_config_digest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg=_config(tmp_path); _ready(monkeypatch,cfg,failed=True); before=probe.validate_config(cfg)["config_digest"]
    result=probe.probe_once(cfg,evaluation_time="2031-02-03T04:05:06Z")
    expected="2031-02-03T04:05:06.0000000Z"
    payload=json.loads(Path(result["governed_signal_path"]).read_text())
    assert result["evaluation_time"] == expected
    assert payload["batch"]["signals"][0]["observed_at"] == expected
    assert probe.inspect(cfg)["receipts"][0]["evaluation_time"] == expected
    assert probe.validate_config(cfg)["config_digest"] == before
    assert cfg["evaluation_time"] == "2026-08-07T00:00:00Z"


def test_tampered_provenance_blocks_without_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg=_config(tmp_path); _ready(monkeypatch,cfg,failed=True,tampered=True)
    assert probe.probe_once(cfg)["status"]=="health_probe_blocked"
    assert not list((tmp_path/"signals").iterdir())


def test_retry_reuses_exact_bytes_and_repairs_missing_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg=_config(tmp_path); _ready(monkeypatch,cfg,failed=True)
    first=probe.probe_once(cfg); path=Path(first["governed_signal_path"]); raw=path.read_bytes()
    Path(str(cfg["receipt_journal_path"])).unlink()
    second=probe.probe_once(cfg)
    assert second["status"]=="health_probe_findings" and path.read_bytes()==raw
    assert probe.inspect(cfg)["receipt_count"]==1


def test_conflicting_existing_output_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg=_config(tmp_path); _ready(monkeypatch,cfg,failed=True)
    first=probe.probe_once(cfg); Path(first["governed_signal_path"]).write_text("{}")
    assert "governed_signal_output_conflict" in probe.probe_once(cfg)["reason_codes"]


def test_print_command_is_fixed_argv_and_config_rejects_inference(tmp_path: Path) -> None:
    cfg=_config(tmp_path); command=probe.print_run_command(cfg)
    assert command["argv"][1:4]==["-m","scripts.run_tests","-q"] and command["shell"] is False
    del cfg["declared_constraints"]
    with pytest.raises(ValueError,match="missing_config_field"): probe.validate_config(cfg)


def test_timeout_terminates_process_group(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class Child:
        pid=123
        calls=0
        def wait(self,timeout: float | None=None) -> int:
            self.calls+=1
            if self.calls<3: raise subprocess.TimeoutExpired("probe", timeout)
            return -9
    child=Child(); killed=[]
    monkeypatch.setattr("subprocess.Popen",lambda *a,**k:child)
    monkeypatch.setattr("os.killpg",lambda pid,sig:killed.append((pid,sig)))
    with pytest.raises(ValueError,match="probe_timeout"): probe._run_bounded(["python"],cwd=tmp_path,timeout=1)
    assert killed==[(123,signal.SIGTERM),(123,signal.SIGKILL)]
