from __future__ import annotations

from pathlib import Path

import pytest

from sentientos.repository_mutation_handoff import HandoffInputError, READY, build_repository_mutation_handoff


def proposal(**overrides):
    data = {"proposal_id": "p1", "status": "approved", "summary": "Seal", "ledger_entry": "ledger-1", "approved_paths": ["a.txt"]}
    data.update(overrides)
    return data


def write(root: Path, name: str, text: str = "hello") -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_valid_approved_paths_produce_deterministic_review_only_handoff(tmp_path: Path) -> None:
    write(tmp_path, "a.txt", "one")
    first = build_repository_mutation_handoff(proposal(), repo_root=tmp_path, source_revision="abc")
    second = build_repository_mutation_handoff(proposal(), repo_root=tmp_path, source_revision="abc")
    assert first == second
    assert first["handoff_status"] == READY
    assert first["metadata_only"] is True
    for key in ("repository_mutation_authorized", "staging_performed", "commit_performed", "branch_mutation_performed", "push_performed", "pull_request_created", "network_performed", "provider_invocation_performed", "prompt_assembly_performed", "runtime_authority_expanded"):
        assert first[key] is False
    assert first["approved_path_evidence"][0]["sha256"]
    assert first["approved_path_evidence"][0]["approved_for_review"] is True


def test_changing_file_content_changes_evidence_and_digest(tmp_path: Path) -> None:
    write(tmp_path, "a.txt", "one")
    first = build_repository_mutation_handoff(proposal(), repo_root=tmp_path, source_revision="abc")
    write(tmp_path, "a.txt", "two")
    second = build_repository_mutation_handoff(proposal(), repo_root=tmp_path, source_revision="abc")
    assert first["approved_path_evidence"][0]["sha256"] != second["approved_path_evidence"][0]["sha256"]
    assert first["digest"] != second["digest"]


@pytest.mark.parametrize("status", ["pending", "proposed", "rejected", "quarantined", "incomplete"])
def test_non_approved_proposals_are_not_ready(tmp_path: Path, status: str) -> None:
    write(tmp_path, "a.txt")
    handoff = build_repository_mutation_handoff(proposal(status=status), repo_root=tmp_path)
    assert handoff["handoff_status"] != READY
    assert "proposal_not_approved" in handoff["reason_codes"]


def test_missing_approval_or_paths_are_incomplete(tmp_path: Path) -> None:
    write(tmp_path, "a.txt")
    no_ref = build_repository_mutation_handoff(proposal(ledger_entry="", approval_reference=""), repo_root=tmp_path)
    no_paths = build_repository_mutation_handoff(proposal(approved_paths=[]), repo_root=tmp_path)
    assert "missing_approval_or_ledger_reference" in no_ref["reason_codes"]
    assert "missing_explicit_approved_paths" in no_paths["reason_codes"]


@pytest.mark.parametrize("bad", ["/tmp/a", "../a", ".git/config", "*.py", "."])
def test_unsafe_paths_are_rejected(tmp_path: Path, bad: str) -> None:
    with pytest.raises(HandoffInputError):
        build_repository_mutation_handoff(proposal(approved_paths=[bad]), repo_root=tmp_path)


def test_missing_and_symlink_escape_are_not_ready(tmp_path: Path) -> None:
    missing = build_repository_mutation_handoff(proposal(approved_paths=["missing.txt"]), repo_root=tmp_path)
    assert "approved_path_missing" in missing["reason_codes"]
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(outside)
    escaped = build_repository_mutation_handoff(proposal(approved_paths=["link.txt"]), repo_root=tmp_path)
    assert escaped["handoff_status"] != READY
    assert "approved_path_not_regular_file" in escaped["reason_codes"]


def test_unapproved_dirty_files_are_absent(tmp_path: Path) -> None:
    write(tmp_path, "a.txt")
    write(tmp_path, "dirty.txt")
    handoff = build_repository_mutation_handoff(proposal(), repo_root=tmp_path)
    assert handoff["approved_paths"] == ["a.txt"]
    assert [item["path"] for item in handoff["approved_path_evidence"]] == ["a.txt"]
