import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.governed_improvement_signal_plane import build_batch, evaluate_signal_plane, render_markdown


def test_deterministic_batch_routing_and_markdown(tmp_path):
    records = [
        {"source_kind":"coverage","finding_kind":"uncovered_flow","severity":"medium","description":"gap","capability_id":"cap","telemetry_stream":"cap.stream","subject_path":"sentientos/x.py","observed_at":"t"},
        {"source_kind":"run_tests","finding_kind":"test_failure","severity":"high","description":"fail","spec_id":"spec.alpha","subject_path":"tests/x.py","observed_at":"t"},
        {"source_kind":"gap_seeker","finding_kind":"todo","severity":"low","description":"todo","subject_path":"sentientos/y.py","observed_at":"t"},
    ]
    a = evaluate_signal_plane(records, repo_root=tmp_path)
    b = evaluate_signal_plane(list(reversed(records)), repo_root=tmp_path)
    assert a.batch.batch_id == b.batch.batch_id
    assert [r.disposition for r in a.receipts] == [r.disposition for r in b.receipts]
    dispositions = {r.disposition for r in a.receipts}
    assert {"genesis_proposal_candidate", "spec_amendment_candidate", "gap_seeker_diagnostic"} <= dispositions
    assert a.summary["adoption_performed"] is False
    assert a.summary["repository_mutation_performed"] is False
    assert "Repository mutation performed: `false`" in render_markdown(a)


def test_duplicate_contradiction_and_authority_claims_fail_closed(tmp_path):
    records = [
        {"source_kind":"telemetry","finding_kind":"missing_capability","description":"one","capability_id":"cap","observed_at":"t"},
        {"source_kind":"telemetry","finding_kind":"missing_capability","description":"two","capability_id":"cap","observed_at":"t"},
        {"source_kind":"unknown","finding_kind":"missing_capability","description":"bad","capability_id":"bad","adoption_performed":True},
    ]
    ev = evaluate_signal_plane(records, repo_root=tmp_path)
    assert ev.batch.contradiction_ids
    assert ev.summary["blocked_invalid_count"] >= 1
    assert all(not r.adoption_occurred and not r.repository_mutation_occurred for r in ev.receipts)


def test_path_traversal_rejected(tmp_path):
    try:
        build_batch([{"source_kind":"run_tests","finding_kind":"test_failure","description":"x","subject_path":"../x"}], repo_root=tmp_path)
    except ValueError as exc:
        assert "path_traversal" in str(exc)
    else:
        raise AssertionError("path traversal accepted")

import json
from pathlib import Path

from sentientos.governed_improvement_signal_plane import collect_repository_evidence, records_from_artifact, validate_evaluation


def _write_run_tests_chain(root: Path, *, observed_name: str = "one", message: str = "boom") -> None:
    d = root / "glow" / "test_runs"
    d.mkdir(parents=True)
    failure = d / f"failure_digest_{observed_name}.json"
    failure.write_text(json.dumps({"schema_version":"test_failure_digest:v1","failure_groups":[{"failure_class":"assertion","exception_type":"AssertionError","nodeid":"tests/test_x.py::test_a","message":message,"file":"tests/test_x.py","line":7,"count":2}]}), encoding="utf-8")
    (d / "test_run_provenance.json").write_text(json.dumps({"schema_version":"run_tests_provenance:v1","pytest_exit_code":1,"tests_selected":1,"tests_executed":1,"tests_passed":0,"tests_failed":1,"metrics_status":"failed","exit_reason":"pytest_failed","junitxml_path":"glow/test_runs/junit.xml","failure_report_path":failure.relative_to(root).as_posix(),"git_sha":"abc","provenance_hash":"sha256:p","prev_provenance_hash":None}), encoding="utf-8")
    (d / "junit.xml").write_text("<testsuite><testcase classname='tests.test_x' name='test_a' file='tests/test_x.py'><failure message='boom' type='AssertionError'/></testcase></testsuite>", encoding="utf-8")


def test_native_run_tests_failure_groups_become_signals(tmp_path: Path) -> None:
    _write_run_tests_chain(tmp_path)
    signals = collect_repository_evidence(repo_root=tmp_path)
    assert len(signals) == 1
    signal = signals[0]
    assert signal.finding_kind == "test_failure"
    assert signal.spec_id == "tests/test_x.py::test_a"
    assert signal.subject_path == "tests/test_x.py"
    assert any(ref == "failure_class:assertion" for ref in signal.evidence_refs)


def test_semantic_identity_excludes_observed_at_and_artifact_location(tmp_path: Path) -> None:
    evidence_a = tmp_path / "a" / "failure.json"
    evidence_b = tmp_path / "b" / "failure.json"
    payload = {"schema_version":"x","failure_groups":[{"failure_class":"assertion","exception_type":"AssertionError","nodeid":"tests/test_x.py::test_a","message":"boom","file":"tests/test_x.py","line":7,"count":1}]}
    evidence_a.parent.mkdir(); evidence_b.parent.mkdir()
    evidence_a.write_text(json.dumps(payload), encoding="utf-8")
    evidence_b.write_text(json.dumps(payload), encoding="utf-8")
    def prov(path: Path, observed: str):
        return {"schema_version":"run_tests_provenance:v1","pytest_exit_code":1,"tests_selected":1,"tests_executed":1,"tests_passed":0,"tests_failed":1,"metrics_status":"failed","exit_reason":"pytest_failed","junitxml_path":"","failure_report_path":path.as_posix(),"git_sha":"abc","provenance_hash":"sha256:p","prev_provenance_hash":None,"observed_at":observed}
    rec_a = records_from_artifact("run_tests", tmp_path / "prov_a.json", repo_root=tmp_path) if False else None
    (tmp_path / "prov_a.json").write_text(json.dumps(prov(evidence_a, "t1")), encoding="utf-8")
    (tmp_path / "prov_b.json").write_text(json.dumps(prov(evidence_b, "t2")), encoding="utf-8")
    sig_a = collect_repository_evidence(repo_root=tmp_path, artifacts=[{"source_kind":"run_tests","path":(tmp_path / "prov_a.json").as_posix()}])[0]
    sig_b = collect_repository_evidence(repo_root=tmp_path, artifacts=[{"source_kind":"run_tests","path":(tmp_path / "prov_b.json").as_posix()}])[0]
    batch_a = build_batch([sig_a], repo_root=tmp_path)
    batch_b = build_batch([sig_b], repo_root=tmp_path)
    assert sig_a.signal_id == sig_b.signal_id
    assert batch_a.batch_id == batch_b.batch_id
    assert batch_a.batch_digest == batch_b.batch_digest
    evidence_b.write_text(json.dumps({**payload, "failure_groups":[{**payload["failure_groups"][0], "message":"different"}]}), encoding="utf-8")
    sig_c = collect_repository_evidence(repo_root=tmp_path, artifacts=[{"source_kind":"run_tests","path":(tmp_path / "prov_b.json").as_posix()}])[0]
    assert sig_c.signal_id != sig_a.signal_id
    assert sig_c.source_digest != sig_a.source_digest


def test_validate_evaluation_rejects_nested_cross_link_mutation(tmp_path: Path) -> None:
    ev = evaluate_signal_plane([{"source_kind":"run_tests","finding_kind":"test_failure","severity":"high","description":"fail","spec_id":"spec.alpha","subject_path":"tests/x.py"}], repo_root=tmp_path)
    payload = ev.to_dict()
    assert validate_evaluation(payload)[0]
    mutated = json.loads(json.dumps(payload))
    mutated["amendment_inputs"][0]["signal_id"] = "wrong"
    ok, reasons = validate_evaluation(mutated)
    assert not ok
    assert "amendment_inputs_mismatch" in reasons
