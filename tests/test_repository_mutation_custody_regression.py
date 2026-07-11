from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip
from sentientos.control_plane_kernel import ControlPlaneKernel
from sentientos.repository_mutation_handoff import resolve_runtime_handoff_root
from sentientosd import RuntimeMaintenanceSurfaces, _run_maintenance_tick
from tests.test_sentientosd_runtime_closure import _ForgeDaemonStub, _GovernorStub, _MergeTrainStub, _SentinelStub, _maintenance_degradations


def test_sentientosd_static_source_has_no_autonomous_git_mutation_path() -> None:
    tree = ast.parse(Path("sentientosd.py").read_text(encoding="utf-8"))
    forbidden_names = {"git_commit_push", "runtime_mark_committed"}
    forbidden_git = {"add", "commit", "push", "branch", "checkout", "switch"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            text = ast.unparse(node)
            assert not any(name in text for name in forbidden_names)
        if isinstance(node, ast.Call):
            text = ast.unparse(node.func)
            assert not any(name in text for name in forbidden_names)
            if isinstance(node.func, ast.Attribute) and node.func.attr in {"run", "check_call", "check_output"}:
                call = ast.unparse(node)
                assert not any(f"git {verb}" in call or f"'git', '{verb}'" in call or f'"git", "{verb}"' in call for verb in forbidden_git)
            assert "pull_request" not in text.lower()


def test_runtime_handoff_emission_external_root_no_state_change_or_repo_dirty(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("approved", encoding="utf-8")
    external = tmp_path / "external-handoffs"
    digest = hashlib.sha256(b"approved").hexdigest()
    revision = "a" * 40
    monkeypatch.setattr("sentientosd.resolve_observed_source_revision", lambda _root: (revision, []))

    class Surfaces(RuntimeMaintenanceSurfaces):
        def __init__(self) -> None:
            super().__init__(repo, repository_mutation_handoff_root=external)
            self.proposals = [{"proposal_id":"p1", "status":"approved", "ledger_entry":"l", "approved_paths":["a.txt"], "approved_path_digests":{"a.txt": digest}, "approved_source_revision": revision}]
        def expand(self): return []
        def cycle(self): return {}
        def guard(self): return {}
        def monitor(self): return []
        def next_repository_mutation_handoff(self):
            from codex.amendments import RepositoryMutationHandoffPlan
            return RepositoryMutationHandoffPlan("p1", "review", "l", self.proposals[0])

    kernel = ControlPlaneKernel(runtime_governor=_GovernorStub(allow=True), decisions_path=tmp_path / "decisions.jsonl")  # type: ignore[arg-type]
    surfaces = Surfaces()
    before = sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*"))
    _run_maintenance_tick(kernel=kernel, runtime_surfaces=surfaces, contract_sentinel=_SentinelStub(), forge_daemon=_ForgeDaemonStub(), merge_train=_MergeTrainStub())  # type: ignore[arg-type]
    after = sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*"))
    artifacts = list(external.glob("*.json"))
    assert len(artifacts) == 1
    assert before == after == ["a.txt"]
    assert not (repo / "integration" / "repository_mutation_handoffs").exists()
    assert surfaces.proposals[0]["status"] == "approved"
    payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert payload["handoff_status"].endswith("ready_for_operator_review")


def test_handoff_root_inside_repository_is_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(ValueError):
        resolve_runtime_handoff_root(repo, repo / "integration" / "repository_mutation_handoffs")


def test_failed_handoff_generation_fail_stops_without_retry_or_new_goal(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    kernel = ControlPlaneKernel(runtime_governor=_GovernorStub(allow=True), decisions_path=tmp_path / "decisions.jsonl")  # type: ignore[arg-type]
    class Bad(RuntimeMaintenanceSurfaces):
        def __init__(self): super().__init__(repo, repository_mutation_handoff_root=repo)
        def expand(self): return []
        def cycle(self): return {}
        def guard(self): return {}
        def monitor(self): return []
        def next_repository_mutation_handoff(self):
            from codex.amendments import RepositoryMutationHandoffPlan
            return RepositoryMutationHandoffPlan("p", "review", "l", {"proposal_id":"p", "status":"approved", "ledger_entry":"l", "approved_paths":["missing.txt"], "approved_path_digests":{"missing.txt":"0"*64}, "approved_source_revision":"x"})
    _run_maintenance_tick(kernel=kernel, runtime_surfaces=Bad(), contract_sentinel=_SentinelStub(), forge_daemon=_ForgeDaemonStub(), merge_train=_MergeTrainStub())  # type: ignore[arg-type]
    degradations = _maintenance_degradations(tmp_path / "decisions.jsonl")
    assert len(degradations) == 1
    assert degradations[0]["surface"] == "repository_mutation_handoff"
    assert degradations[0]["retry_attempted"] is False
    assert degradations[0]["follow_up_enqueued"] is False
    assert degradations[0]["reinterpreted_as_goal"] is False


def test_environment_variable_does_not_restore_autonomous_mutation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SENTIENTOS_AUTONOMOUS_REPOSITORY_MUTATION", "1")
    test_sentientosd_static_source_has_no_autonomous_git_mutation_path()


def test_runtime_handoff_selector_requires_approved_and_review_reference(monkeypatch) -> None:
    from codex import amendments

    proposals = [
        {"proposal_id": "pending", "status": "pending", "ledger_entry": "ledger-p"},
        {"proposal_id": "rejected", "status": "rejected", "ledger_entry": "ledger-r"},
        {"proposal_id": "quarantined", "status": "quarantined", "ledger_entry": "ledger-q"},
        {"proposal_id": "no-ref", "status": "approved"},
        {"proposal_id": "ledger-entry", "status": "approved", "ledger_entry": "ledger-1"},
        {"proposal_id": "ledger-ref", "status": "approved", "ledger_reference": "ledger-ref-1"},
        {"proposal_id": "approval-ref", "status": "approved", "approval_reference": "approval-1"},
    ]

    class _Engine:
        def active_amendments(self):
            return proposals

    monkeypatch.setattr(amendments, "_runtime_amender", lambda root: _Engine())
    before = [dict(item) for item in proposals]
    plan = amendments.runtime_next_repository_mutation_handoff("integration", approved_only=True)
    assert plan is not None
    assert plan.proposal_id == "ledger-entry"
    assert plan.review_reference == "ledger-1"
    assert proposals == before


def test_runtime_handoff_selector_accepts_ledger_reference_and_approval_reference(monkeypatch) -> None:
    from codex import amendments

    class _Engine:
        def __init__(self, proposals):
            self._proposals = proposals
        def active_amendments(self):
            return self._proposals

    monkeypatch.setattr(amendments, "_runtime_amender", lambda root: _Engine([
        {"proposal_id": "no-ref", "status": "approved"},
        {"proposal_id": "ledger-ref", "status": "approved", "ledger_reference": "ledger-ref-1"},
    ]))
    plan = amendments.runtime_next_repository_mutation_handoff("integration", approved_only=True)
    assert plan is not None
    assert plan.proposal_id == "ledger-ref"
    assert plan.review_reference == "ledger-ref-1"

    monkeypatch.setattr(amendments, "_runtime_amender", lambda root: _Engine([
        {"proposal_id": "approval-ref", "status": "approved", "approval_reference": "approval-1"},
    ]))
    plan = amendments.runtime_next_repository_mutation_handoff("integration", approved_only=True)
    assert plan is not None
    assert plan.proposal_id == "approval-ref"
    assert plan.review_reference == "approval-1"
