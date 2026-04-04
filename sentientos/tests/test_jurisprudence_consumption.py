from __future__ import annotations

from pathlib import Path

from scripts.emit_contract_status import emit_contract_status
from sentientos import bounded_jurisprudence
from sentientos.jurisprudence_consumption import build_jurisprudence_consumption_summary


def test_jurisprudence_consumer_reads_explicit_rule_set() -> None:
    summary = build_jurisprudence_consumption_summary(consumer_surface="contract_status")

    assert summary["consumer_surface"] == "contract_status"
    assert summary["explicit_rule_count"] == 3
    rows = {row["decision_class"]: row for row in summary["emitted_vs_consumed"]}
    assert rows["federated_control_admission"]["consumption_state"] == "explicit_rule_consumed"
    assert rows["maintenance_admission_proof_budget"]["consumption_state"] == "explicit_rule_consumed"
    assert rows["merge_train_mergeability_protected_mutation"]["consumption_state"] == "explicit_rule_consumed"


def test_jurisprudence_consumer_marks_unresolved_classes_visible() -> None:
    summary = build_jurisprudence_consumption_summary(consumer_surface="contract_status")

    unresolved = {row["decision_class"]: row for row in summary["unresolved_classes"]}
    assert "repair_admission_cross_surface_precedence" in unresolved
    assert unresolved["repair_admission_cross_surface_precedence"]["consumption_state"] == "unresolved_no_explicit_rule"


def test_contract_status_surfaces_jurisprudence_domain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    payload = emit_contract_status(tmp_path / "glow/contracts/contract_status.json")
    domains = {item["domain_name"]: item for item in payload["contracts"] if isinstance(item, dict) and isinstance(item.get("domain_name"), str)}

    domain = domains["authority_of_judgment_jurisprudence"]
    assert domain["drift_type"] == "none"
    assert domain["mapping_gap_count"] == 0
    assert len(domain["emitted_vs_consumed"]) == 3


def test_absent_jurisprudence_mapping_does_not_create_false_authority(monkeypatch: object) -> None:
    monkeypatch.setattr(bounded_jurisprudence, "EXPLICIT_AUTHORITY_RULES", ())

    summary = build_jurisprudence_consumption_summary(consumer_surface="contract_status")

    assert summary["explicit_rule_count"] == 0
    assert summary["mapping_gap_count"] == 3
    assert all(row["consumption_state"] == "unresolved_no_explicit_rule" for row in summary["emitted_vs_consumed"])
