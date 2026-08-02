from __future__ import annotations

import json
import subprocess

import pytest

from sentientos.behavioral_witness import build_witness, digest
from sentientos.task_acceptance import verify

NODE = "tests/test_task_acceptance_behavioral_witnesses.py::test_v2_acceptance_ready_with_bound_witness"
pytestmark = pytest.mark.no_legacy_skip


def _sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _case(tmp_path, *, witnesses=None, assertions=None, schema="sentientos.task_acceptance:v2"):
    sha, run = _sha(), "run-1"
    facts = {"observed": True, "disabled": False, "name": "proof", "items": [1, 2, 3],
             "counted": [1, 2], "left": 7, "right": 7, "different": 8}
    witness = build_witness(repository_sha=sha, run_id=run, node_id=NODE, contract_id="contract",
                            witness_kind="sentientos.example_proof:v1", facts=facts)
    actual = [witness] if witnesses is None else witnesses(witness)
    provenance = {"git_sha": sha, "run_id": run, "reporter_ok": True, "metrics_status": "ok",
                  "selected_node_ids": [NODE], "node_outcomes": [{"node_id": NODE, "phase": "call", "outcome": "passed"}],
                  "behavioral_witnesses": actual, "behavioral_witness_digest": digest(actual)}
    default_assertions = [
        {"op": "equals", "path": "/name", "value": "proof"}, {"op": "not_equals", "path": "/name", "value": "other"},
        {"op": "is_true", "path": "/observed"}, {"op": "is_false", "path": "/disabled"},
        {"op": "is_nonempty", "path": "/items"}, {"op": "count_equals", "path": "/counted", "value": 2},
        {"op": "same_value", "path": "/left", "other_path": "/right"},
        {"op": "different_value", "path": "/left", "other_path": "/different"},
        {"op": "ordered_subsequence", "path": "/items", "value": [1, 3]},
    ]
    required = {"node_id": NODE}
    if schema.endswith(":v2"):
        required["witness_contracts"] = [{"contract_id": "contract", "witness_kind": "sentientos.example_proof:v1",
                                           "assertions": default_assertions if assertions is None else assertions}]
    manifest = {"schema_version": schema, "task_classification": "behavior_adding", "repository_sha": sha,
                "required_nodes": [required], "successful_path_nodes": [NODE]}
    mp, pp = tmp_path / "manifest.json", tmp_path / "provenance.json"
    mp.write_text(json.dumps(manifest)); pp.write_text(json.dumps(provenance))
    return verify(mp, pp)


def test_v2_acceptance_ready_with_bound_witness(tmp_path): assert _case(tmp_path)["status"] == "task_acceptance_ready"
def test_v2_missing_witness_blocks_passing_node(tmp_path): assert "required_witness_missing" in " ".join(_case(tmp_path, witnesses=lambda _: [])["reasons"])
def test_v2_unsatisfied_assertion_blocks(tmp_path): assert "required_witness_assertion_failed" in " ".join(_case(tmp_path, assertions=[{"op":"is_false","path":"/observed"}])["reasons"])
def test_v2_conflicting_duplicate_witness_blocks(tmp_path):
    def conflict(w):
        other = dict(w); other["digest"] = "sha256:" + "0" * 64
        return [w, other]
    assert "required_witness_conflict" in " ".join(_case(tmp_path, witnesses=conflict)["reasons"])
def test_v2_wrong_node_run_or_sha_cannot_satisfy_contract(tmp_path):
    for field, value, reason in [("node_id", "other::node", "missing"), ("run_id", "old", "wrong_run"), ("repository_sha", "0"*40, "wrong_sha")]:
        result = _case(tmp_path, witnesses=lambda w, f=field, v=value: [{**w, f: v}])
        assert reason in " ".join(result["reasons"])
def test_v2_tampered_witness_digest_blocks(tmp_path): assert "digest_invalid" in " ".join(_case(tmp_path, witnesses=lambda w: [{**w,"digest":"bad"}])["reasons"])
def test_v2_unknown_operator_fails_without_execution(tmp_path, monkeypatch):
    called = []; monkeypatch.setattr("builtins.open", lambda *a, **k: called.append(a))
    result = _case(tmp_path, assertions=[{"op":"__import__","path":"/observed","value":"os.system('x')"}])
    assert "unknown_witness_assertion_operator" in " ".join(result["reasons"]); assert called == []
def test_v1_manifest_remains_backward_compatible(tmp_path): assert _case(tmp_path, schema="sentientos.task_acceptance:v1")["status"] == "task_acceptance_ready"
