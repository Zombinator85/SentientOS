"""Structural checks for the non-authority FIDES comparative audit.

These checks prove document shape and evidence-address validity only.  They do
not purport to prove the audit's comparative architectural judgments.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest


pytestmark = pytest.mark.no_legacy_skip


ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "architecture/fides_sentientos_comparative_invariant_audit.json"
DOC_PATH = ROOT / "docs/architecture/fides_sentientos_comparative_invariant_audit.md"

EXPECTED_MECHANISMS = {
    "content_integrity",
    "confidentiality",
    "principal_set_propagation",
    "restriction_only_remote_labels",
    "tiered_result_labeling",
    "propagation",
    "unlabeled_tool_output",
    "sink_policy",
    "variable_indirection",
    "quarantined_llm",
    "blind_forwarding",
    "exact_approval_binding",
    "one_shot_approval",
    "session_security_state",
    "audit",
    "conservative_taint_tradeoff",
}
RECOMMENDATIONS = {
    "no_change",
    "documentation_only",
    "unify_existing_invariant",
    "targeted_future_feature",
    "requires_design_decision",
    "incompatible_or_not_useful",
}
REQUIRED_SECTIONS = {
    "Executive finding",
    "Methodology and source discipline",
    "FIDES mechanism summary",
    "SentientOS existing semantics",
    "Mechanism-by-mechanism crosswalk",
    "Integrity analysis",
    "Confidentiality and principal analysis",
    "Provenance and derivation analysis",
    "Quarantine and indirection analysis",
    "Admission and approval consumption analysis",
    "Crash-window analysis",
    "Unknown and unlabeled semantics",
    "What FIDES teaches SentientOS",
    "What SentientOS should explicitly NOT copy",
    "Design questions requiring operator/architect decision",
    "Ranked-by-dependency future research questions",
    "Evidence appendix",
}
ALLOWED_CHANGED_FILES = {
    "architecture/fides_sentientos_comparative_invariant_audit.json",
    "docs/architecture/fides_sentientos_comparative_invariant_audit.md",
    "tests/test_fides_sentientos_comparative_invariant_audit.py",
}
GENERATED_TRACKED_FILES = {
    "glow/test_runs/test_run_provenance.json",
    "pulse/audit/privileged_audit.runtime.jsonl",
}


def _payload() -> dict[str, Any]:
    value = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_json_parses_and_declares_every_mechanism_exactly_once() -> None:
    payload = _payload()
    rows = payload["crosswalk"]
    assert isinstance(rows, list)
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids))
    assert set(ids) == EXPECTED_MECHANISMS
    assert set(payload["declared_comparison_set"]) == EXPECTED_MECHANISMS


def test_required_markdown_sections_exist_exactly_once() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    payload = _payload()
    assert set(payload["required_sections"]) == REQUIRED_SECTIONS
    for section in REQUIRED_SECTIONS:
        assert text.count(f"## {section}\n") == 1


def test_crosswalk_evidence_paths_exist_and_rules_are_closed() -> None:
    for row in _payload()["crosswalk"]:
        assert row["implementation_recommendation"] in RECOMMENDATIONS
        assert row["implementation_recommendation"] != "implement_now"
        assert row["source_paths"]
        assert row["test_paths"]
        for field in ("source_paths", "test_paths"):
            for relative_path in row[field]:
                assert (ROOT / relative_path).is_file(), (row["id"], relative_path)
        if row["semantic_equivalence"] == "no analogue found":
            assert "equivalent" not in row["semantic_equivalence"]
        if row["semantic_equivalence"].startswith("equivalent"):
            assert row["source_paths"] and row["test_paths"]


def test_audit_does_not_claim_forbidden_conclusions() -> None:
    raw = JSON_PATH.read_text(encoding="utf-8")
    assert "implement_now" not in raw
    conclusions = _payload()["non_conclusions"]
    assert any("universal ContentLabel" in value for value in conclusions)
    assert any("Data confidentiality is not effect authority" in value for value in conclusions)


def test_task_diff_is_confined_to_docs_structured_audit_and_its_test() -> None:
    tracked = subprocess.run(
        ["git", "diff", "--name-only", "013a0eb282715e17e19da2d2d1826ce7b07b0190"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    source_like_untracked = {
        path
        for path in untracked
        if path.endswith((".py", ".bat")) or path.startswith("sentientos/")
    }
    assert set(tracked) - GENERATED_TRACKED_FILES <= ALLOWED_CHANGED_FILES
    assert source_like_untracked <= ALLOWED_CHANGED_FILES
