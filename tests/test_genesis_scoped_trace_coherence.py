from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex.integrity_daemon import IntegrityDaemon
from sentientos.codex_healer import RecoveryLedger
from sentientos.control_plane_kernel import AdmissionOutcome, AuthorityClass
from sentientos.genesis_forge import (
    AdoptionRite,
    CovenantVow,
    ForgeEngine,
    GenesisForge,
    GenesisForgeError,
    NeedSeer,
    SpecBinder,
    TelemetryStream,
    TrialRun,
)
from sentientos.scoped_canonical_trace_coherence import evaluate_scoped_trace_completeness


@pytest.fixture(autouse=True)
def _codex_startup(codex_startup: None) -> None:
    yield


def _build_forge(tmp_path: Path) -> GenesisForge:
    return GenesisForge(
        need_seer=NeedSeer(),
        forge_engine=ForgeEngine(),
        integrity_daemon=IntegrityDaemon(tmp_path),
        trial_run=TrialRun(),
        spec_binder=SpecBinder(lineage_root=tmp_path / "lineage", covenant_root=tmp_path / "covenant"),
        adoption_rite=AdoptionRite(
            live_mount=tmp_path / "live",
            codex_index=tmp_path / "codex.json",
            review_board=lambda _proposal, _report: True,
        ),
        ledger=RecoveryLedger(tmp_path / "ledger.jsonl"),
    )


def _patch_trusted_kernel(monkeypatch: pytest.MonkeyPatch) -> None:
    class _TrustState:
        degraded_audit_trust = False
        history_state = "trusted"
        checkpoint_id = "checkpoint-test"

    class _Decision:
        def __init__(self, *, allowed: bool, reason_codes: list[str], outcome: AdmissionOutcome) -> None:
            self.allowed = allowed
            self.reason_codes = tuple(reason_codes)
            self.delegated_outcomes: dict[str, object] = {}
            self.correlation_id = "kernel-test"
            self.outcome = outcome

    class _Kernel:
        def set_phase(self, phase, *, actor="control_plane_kernel") -> None:  # noqa: ANN001
            return None

        def admit(self, request):  # noqa: ANN001
            if request.action_kind == "proof_budget":
                decision = _Decision(allowed=True, reason_codes=["admitted"], outcome=AdmissionOutcome.ALLOW)
                decision.delegated_outcomes = {
                    "proof_budget_governor": {
                        "k_effective": 3,
                        "m_effective": 2,
                        "allow_escalation": True,
                        "mode": "normal",
                        "decision_reasons": ["ok"],
                    }
                }
                return decision
            return _Decision(allowed=True, reason_codes=["admitted"], outcome=AdmissionOutcome.ALLOW)

        def admit_and_execute(self, request, *, execute=None):  # noqa: ANN001
            if request.authority_class in {
                AuthorityClass.MANIFEST_OR_IDENTITY_MUTATION,
                AuthorityClass.PROPOSAL_ADOPTION,
            }:
                return _Decision(allowed=True, reason_codes=["admitted"], outcome=AdmissionOutcome.ALLOW), execute()
            return _Decision(allowed=False, reason_codes=["not_routed"], outcome=AdmissionOutcome.DENY), None

    monkeypatch.setattr("sentientos.genesis_forge.get_control_plane_kernel", lambda: _Kernel())
    monkeypatch.setattr("sentientos.genesis_forge.evaluate_audit_trust", lambda *args, **kwargs: _TrustState())
    monkeypatch.setattr("sentientos.genesis_forge.write_audit_trust_artifacts", lambda *args, **kwargs: {})


def test_genesis_proposal_adopt_trace_is_coherent_end_to_end(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _patch_trusted_kernel(monkeypatch)
    forge = _build_forge(tmp_path)
    outcomes = forge.expand(
        [TelemetryStream("vision_stream", "vision_input", "Camera frames", frozenset())],
        [CovenantVow("vision_input", "camera vow")],
    )
    assert outcomes and outcomes[0].status == "adopted"

    trace = evaluate_scoped_trace_completeness(tmp_path)
    adopt_row = next(row for row in trace["actions"] if row["typed_action_identity"] == "sentientos.genesis.proposal_adopt")
    lineage_row = next(row for row in trace["actions"] if row["typed_action_identity"] == "sentientos.genesis.lineage_integrate")
    assert adopt_row["status"] == "trace_complete", json.dumps(adopt_row, indent=2, sort_keys=True)
    assert adopt_row["router_event"]["path_status"] == "canonical_router"
    assert adopt_row["kernel_decision"]["final_disposition"] == "allow"
    assert lineage_row["status"] == "trace_partially_fragmented", json.dumps(lineage_row, indent=2, sort_keys=True)


def test_genesis_trace_detects_missing_adoption_lineage_linkage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _patch_trusted_kernel(monkeypatch)
    forge = _build_forge(tmp_path)
    outcomes = forge.expand(
        [TelemetryStream("vision_stream", "vision_input", "Camera frames", frozenset())],
        [CovenantVow("vision_input", "camera vow")],
    )
    assert outcomes and outcomes[0].status == "adopted"
    codex_path = tmp_path / "codex.json"
    codex_payload = json.loads(codex_path.read_text(encoding="utf-8"))
    codex_payload[0].pop("lineage_admission_decision_ref", None)
    codex_path.write_text(json.dumps(codex_payload, indent=2, sort_keys=True), encoding="utf-8")

    trace = evaluate_scoped_trace_completeness(tmp_path)
    adopt_row = next(row for row in trace["actions"] if row["typed_action_identity"] == "sentientos.genesis.proposal_adopt")
    assert adopt_row["status"] == "missing_canonical_linkage", json.dumps(adopt_row, indent=2, sort_keys=True)
    assert any(item.get("kind") == "codex_missing_lineage_admission_decision_ref" for item in adopt_row["linkage_findings"])


def test_non_canonical_genesis_helper_activity_does_not_fabricate_canonical_trace(tmp_path: Path) -> None:
    binder = SpecBinder(lineage_root=tmp_path / "lineage", covenant_root=tmp_path / "covenant")
    proposal = ForgeEngine().draft(
        NeedSeer().scan(
            [TelemetryStream("vision_stream", "vision_input", "Camera frames", frozenset())],
            [CovenantVow("vision_input", "camera vow")],
        )[0]
    )
    with pytest.raises(GenesisForgeError, match="admission provenance"):
        binder.integrate(proposal, admission_provenance=None)

    trace = evaluate_scoped_trace_completeness(tmp_path)
    lineage_row = next(row for row in trace["actions"] if row["typed_action_identity"] == "sentientos.genesis.lineage_integrate")
    adopt_row = next(row for row in trace["actions"] if row["typed_action_identity"] == "sentientos.genesis.proposal_adopt")
    assert lineage_row["status"] == "trace_partially_fragmented"
    assert adopt_row["status"] == "trace_partially_fragmented"
