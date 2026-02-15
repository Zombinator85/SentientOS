"""Tests for the GenesisForge autonomous capability expansion pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex.integrity_daemon import IntegrityDaemon
from codex.proposal_router import CandidateResult, choose_candidate, score_evaluation
from sentientos.codex_healer import RecoveryLedger
from sentientos.genesis_forge import (
    AdoptionRite,
    CovenantVow,
    DaemonManifest,
    ForgeEngine,
    GenesisForge,
    NeedSeer,
    SpecBinder,
    TelemetryStream,
    TrialRun,
)


@pytest.fixture(autouse=True)
def _codex_startup(codex_startup: None) -> None:
    yield


def _review_board(_: object, __: object) -> bool:
    return True


def test_needseer_detects_unhandled_stream(tmp_path: Path) -> None:
    telemetries = [
        TelemetryStream(
            name="vision_bus",
            capability="vision_input",
            description="Camera frames from sanctuary sensors",
            handled_by=frozenset(),
            sample_payload={"frames": 1},
        )
    ]
    vows = [
        CovenantVow(
            capability="vision_input",
            description="Every camera input must be witnessed",
        )
    ]
    seer = NeedSeer(daemons=[DaemonManifest("audio_daemon", frozenset({"audio_input"}))])
    needs = seer.scan(telemetries, vows)
    assert [need.capability for need in needs] == ["vision_input"]

    engine = ForgeEngine(existing_daemons=[DaemonManifest("audio_daemon", frozenset({"audio_input"}))])
    proposal = engine.draft(needs[0])
    assert proposal.proposed_spec["lineage"]["provenance"] == "GenesisForge"
    assert proposal.blueprint.testing_requirements == [
        "acknowledge_capability",
        "emit_success_status",
        "record_provenance_GenesisForge",
    ]


def test_trialrun_detects_malformed_handler() -> None:
    need = NeedSeer().scan(
        [TelemetryStream("vision", "vision_input", "camera", frozenset(), {"frames": 3})],
        [CovenantVow("vision_input", "camera vow")],
    )[0]
    engine = ForgeEngine()
    proposal = engine.draft(need)

    # Replace handler with malformed implementation.
    def bad_handler(_: object) -> dict[str, object]:
        return {"status": "error"}

    proposal.blueprint.handler = bad_handler
    report = TrialRun().execute(proposal.blueprint)
    assert not report.passed
    assert "capability" in report.failures[0]


def test_lineage_records_provenance(tmp_path: Path) -> None:
    telemetry = [
        TelemetryStream(
            name="vision_stream",
            capability="vision_input",
            description="Camera frames",
            handled_by=frozenset(),
            sample_payload={"frames": 5},
        )
    ]
    vows = [CovenantVow("vision_input", "Cameras must be witnessed")]

    lineage_root = tmp_path / "lineage"
    covenant_root = tmp_path / "covenant"
    live_mount = tmp_path / "live"
    codex_index = tmp_path / "codex.json"
    ledger_path = tmp_path / "ledger.jsonl"

    seer = NeedSeer()
    engine = ForgeEngine()
    integrity = IntegrityDaemon(tmp_path)
    trial = TrialRun()
    binder = SpecBinder(lineage_root=lineage_root, covenant_root=covenant_root)
    adoption = AdoptionRite(
        live_mount=live_mount,
        codex_index=codex_index,
        review_board=_review_board,
    )
    ledger = RecoveryLedger(ledger_path)
    forge = GenesisForge(
        need_seer=seer,
        forge_engine=engine,
        integrity_daemon=integrity,
        trial_run=trial,
        spec_binder=binder,
        adoption_rite=adoption,
        ledger=ledger,
    )

    outcomes = forge.expand(telemetry, vows)
    assert outcomes and outcomes[0].status == "adopted"

    lineage_entries = [json.loads(line) for line in (lineage_root / "lineage.jsonl").read_text().splitlines()]
    assert lineage_entries[0]["provenance"] == "GenesisForge"

    ledger_lines = [json.loads(line) for line in ledger_path.read_text().splitlines()]
    assert any(entry["status"] == "GenesisForge event" for entry in ledger_lines)
    proof_budget_events = [entry for entry in ledger_lines if entry["status"] == "proof_budget"]
    assert proof_budget_events
    assert proof_budget_events[-1]["details"]["event_type"] == "proof_budget"

    codex_payload = json.loads(codex_index.read_text())
    assert codex_payload[0]["provenance"] == "GenesisForge"


def test_prevents_overwriting_existing_daemon(tmp_path: Path) -> None:
    telemetry = [
        TelemetryStream(
            name="vision_stream",
            capability="vision_input",
            description="Camera frames",
            handled_by=frozenset(),
        )
    ]
    vows = [CovenantVow("vision_input", "camera vow")]

    lineage_root = tmp_path / "lineage"
    covenant_root = tmp_path / "covenant"
    live_mount = tmp_path / "live"
    codex_index = tmp_path / "codex.json"
    ledger_path = tmp_path / "ledger.jsonl"

    binder = SpecBinder(lineage_root=lineage_root, covenant_root=covenant_root)
    # Pre-create a daemon file to force an overwrite attempt.
    existing = covenant_root / "daemons" / "VisionInputGenesisDaemon.json"
    existing.write_text("{}", encoding="utf-8")

    forge = GenesisForge(
        need_seer=NeedSeer(),
        forge_engine=ForgeEngine(),
        integrity_daemon=IntegrityDaemon(tmp_path),
        trial_run=TrialRun(),
        spec_binder=binder,
        adoption_rite=AdoptionRite(
            live_mount=live_mount,
            codex_index=codex_index,
            review_board=_review_board,
        ),
        ledger=RecoveryLedger(ledger_path),
    )

    outcomes = forge.expand(telemetry, vows)
    assert outcomes[0].status == "failed"
    assert isinstance(outcomes[0].details["error"], str)
    # Original file remains untouched.
    assert existing.read_text(encoding="utf-8") == "{}"


def test_draft_variants_are_distinct_and_preserve_lineage() -> None:
    need = NeedSeer().scan(
        [TelemetryStream("vision", "vision_input", "camera", frozenset(), {"frames": 3})],
        [CovenantVow("vision_input", "camera vow")],
    )[0]
    engine = ForgeEngine()
    variants = engine.draft_variants(need, k=3, seed="vision-seed")
    assert len(variants) == 3
    payloads = {json.dumps(item.proposed_spec, sort_keys=True) for item in variants}
    assert len(payloads) == 3
    for variant in variants:
        assert variant.proposed_spec["ledger_required"] is True
        assert variant.proposed_spec["lineage"]["provenance"] == "GenesisForge"


def test_genesis_forge_refuses_when_no_admissible_candidate(tmp_path: Path) -> None:
    telemetry = [
        TelemetryStream(
            name="vision_stream",
            capability="vision_input",
            description="Camera frames",
            handled_by=frozenset(),
        )
    ]
    vows = [CovenantVow("vision_input", "camera vow")]

    forge = GenesisForge(
        need_seer=NeedSeer(),
        forge_engine=ForgeEngine(),
        integrity_daemon=IntegrityDaemon(tmp_path),
        trial_run=TrialRun(),
        spec_binder=SpecBinder(lineage_root=tmp_path / "lineage", covenant_root=tmp_path / "covenant"),
        adoption_rite=AdoptionRite(
            live_mount=tmp_path / "live",
            codex_index=tmp_path / "codex.json",
            review_board=_review_board,
        ),
        ledger=RecoveryLedger(tmp_path / "ledger.jsonl"),
    )

    class AlwaysInvalid:
        def __init__(self, base: IntegrityDaemon) -> None:
            self.base = base

        def evaluate_report_stage_a(self, proposal: object):
            result = self.base.evaluate_report_stage_a(proposal)
            result.valid_a = False
            result.reason_codes_a = ["tamper"]
            result.violations_a = [{"code": "tamper", "detail": "forced-stage-a"}]
            return result

        def evaluate_report_stage_b(self, proposal: object, *, probe_cache=None):
            result = self.base.evaluate_report_stage_b(proposal, probe_cache=probe_cache)
            result.valid = False
            result.reason_codes = ["tamper"]
            result.violations = [{"code": "tamper", "detail": "forced-stage-b"}]
            return result

        def evaluate_report(self, proposal: object):
            return self.evaluate_report_stage_b(proposal)

    forge._integrity_daemon = AlwaysInvalid(forge._integrity_daemon)  # type: ignore[assignment]
    outcomes = forge.expand(telemetry, vows)
    assert outcomes[0].status == "failed"


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
            review_board=_review_board,
        ),
        ledger=RecoveryLedger(tmp_path / "ledger.jsonl"),
    )


def test_genesis_stage_b_proof_budget_is_capped_by_m(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SENTIENTOS_ROUTER_K", "5")
    monkeypatch.setenv("SENTIENTOS_ROUTER_M", "2")
    forge = _build_forge(tmp_path)

    class CountingDaemon:
        def __init__(self, daemon: IntegrityDaemon) -> None:
            self._daemon = daemon
            self.stage_b_calls = 0

        def evaluate_report_stage_a(self, proposal: object):
            return self._daemon.evaluate_report_stage_a(proposal)

        def evaluate_report_stage_b(self, proposal: object, *, probe_cache=None):
            self.stage_b_calls += 1
            return self._daemon.evaluate_report_stage_b(proposal, probe_cache=probe_cache)

    daemon = CountingDaemon(forge._integrity_daemon)
    forge._integrity_daemon = daemon  # type: ignore[assignment]

    outcomes = forge.expand(
        [TelemetryStream("vision_stream", "vision_input", "Camera frames", frozenset())],
        [CovenantVow("vision_input", "camera vow")],
    )

    scorecard = outcomes[0].details["router_scorecard"]
    telemetry = scorecard["router_telemetry"]
    assert daemon.stage_b_calls <= 2
    assert scorecard["proof_budget"]["m"] == 2
    assert len(scorecard["promoted_to_stage_b"]) <= 2
    assert telemetry["stage_b_evaluations"] == daemon.stage_b_calls
    assert telemetry["stage_b_evaluations"] <= 2
    assert telemetry["stage_a_evaluations"] == len(scorecard["stage_a"])


def test_genesis_escalates_only_when_all_fail_stage_a(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SENTIENTOS_ROUTER_K", "3")

    class ConditionalStageADaemon:
        def __init__(self, daemon: IntegrityDaemon, *, all_fail: bool) -> None:
            self._daemon = daemon
            self._all_fail = all_fail

        def evaluate_report_stage_a(self, proposal: object):
            report = self._daemon.evaluate_report_stage_a(proposal)
            variant = str(getattr(proposal, "proposal_id", ""))
            should_fail = self._all_fail or not variant.endswith("V1")
            if should_fail:
                report.valid_a = False
                report.reason_codes_a = ["tamper"]
                report.violations_a = [{"code": "tamper", "detail": "forced-stage-a"}]
            return report

        def evaluate_report_stage_b(self, proposal: object, *, probe_cache=None):
            return self._daemon.evaluate_report_stage_b(proposal, probe_cache=probe_cache)

    forge_no_escalation = _build_forge(tmp_path / "no_escalation")
    daemon_no_escalation = ConditionalStageADaemon(forge_no_escalation._integrity_daemon, all_fail=False)
    forge_no_escalation._integrity_daemon = daemon_no_escalation  # type: ignore[assignment]
    outcomes_no_escalation = forge_no_escalation.expand(
        [TelemetryStream("vision_stream", "vision_input", "Camera frames", frozenset())],
        [CovenantVow("vision_input", "camera vow")],
    )
    budget_no_escalation = outcomes_no_escalation[0].details["router_scorecard"]["proof_budget"]
    assert budget_no_escalation["escalated"] is False
    assert budget_no_escalation["k_final"] == 3

    forge_escalation = _build_forge(tmp_path / "escalation")
    daemon_escalation = ConditionalStageADaemon(forge_escalation._integrity_daemon, all_fail=True)
    forge_escalation._integrity_daemon = daemon_escalation  # type: ignore[assignment]
    outcomes_escalation = forge_escalation.expand(
        [TelemetryStream("vision_stream", "vision_input", "Camera frames", frozenset())],
        [CovenantVow("vision_input", "camera vow")],
    )
    scorecard_escalation = outcomes_escalation[0].details["router_scorecard"]
    budget_escalation = scorecard_escalation["proof_budget"]
    telemetry_escalation = scorecard_escalation["router_telemetry"]
    assert budget_escalation["escalated"] is True
    assert budget_escalation["k_final"] == 6
    assert len(scorecard_escalation["stage_a"]) == 6
    assert telemetry_escalation["escalated"] is True
    assert telemetry_escalation["k_final"] == 6
    assert telemetry_escalation["stage_a_evaluations"] == 6


def test_genesis_selected_candidate_matches_full_proof_on_promoted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SENTIENTOS_ROUTER_K", "5")
    monkeypatch.setenv("SENTIENTOS_ROUTER_M", "2")
    forge = _build_forge(tmp_path)

    class OneAdmissibleStageBDaemon:
        def __init__(self, daemon: IntegrityDaemon) -> None:
            self._daemon = daemon
            self._stage_a_ids: set[str] = set()
            self.admissible_id: str | None = None

        def evaluate_report_stage_a(self, proposal: object):
            report = self._daemon.evaluate_report_stage_a(proposal)
            candidate_id = str(getattr(proposal, "proposal_id", ""))
            self._stage_a_ids.add(candidate_id)
            ordered = sorted(self._stage_a_ids)
            if len(ordered) >= 2:
                self.admissible_id = ordered[1]
            return report

        def evaluate_report_stage_b(self, proposal: object, *, probe_cache=None):
            report = self._daemon.evaluate_report_stage_b(proposal, probe_cache=probe_cache)
            candidate_id = str(getattr(proposal, "proposal_id", ""))
            if candidate_id != self.admissible_id:
                report.valid = False
                report.reason_codes = ["tamper"]
                report.violations = [{"code": "tamper", "detail": "forced-stage-b"}]
            return report

    daemon = OneAdmissibleStageBDaemon(forge._integrity_daemon)
    forge._integrity_daemon = daemon  # type: ignore[assignment]

    telemetry = [TelemetryStream("vision_stream", "vision_input", "Camera frames", frozenset())]
    vows = [CovenantVow("vision_input", "camera vow")]
    outcomes = forge.expand(telemetry, vows)

    scorecard = outcomes[0].details["router_scorecard"]
    promoted_ids = scorecard["promoted_to_stage_b"]
    selected_id = scorecard["selected_candidate_id"]
    assert selected_id == daemon.admissible_id

    need = forge._need_seer.scan(telemetry, vows)[0]
    proposals = forge._forge_engine.draft_variants(
        need,
        k=scorecard["proof_budget"]["k_final"],
        seed=scorecard["router_seed"],
    )
    proposal_map = {proposal.proposal_id: proposal for proposal in proposals}

    results: list[CandidateResult] = []
    for candidate_id in promoted_ids:
        proposal = proposal_map[candidate_id]
        stage_a = daemon.evaluate_report_stage_a(proposal)
        evaluation = daemon.evaluate_report_stage_b(proposal, probe_cache=stage_a.probe)
        results.append(
            CandidateResult(
                candidate_id=candidate_id,
                proposal=proposal,
                evaluation=evaluation,
                score=score_evaluation(evaluation),
            )
        )
    full_selected, status = choose_candidate(results)
    assert status == "selected"
    assert full_selected.candidate_id == selected_id
