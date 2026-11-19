from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_resident_developmental_cognition import owner, snapshot  # noqa: E402
from test_epistemic_revision_stability_series import (  # noqa: E402
    PositionReasoningFixtureInvoker,
)
from test_epistemic_revision_qualification import _cognition_root  # noqa: E402
from sentientos.epistemic_revision_reopening_series import (  # noqa: E402
    EpistemicCorrectionReopeningSeries,
    evaluate_correction_reopening_series,
)
from sentientos.epistemic_revision_qualification import (  # noqa: E402
    IndependentAnswerKey,
    RevisionCase,
)
from sentientos.local_model_authority import digest_payload  # noqa: E402
from sentientos.persistent_epistemic_state import (  # noqa: E402
    PersistentEpistemicStateOwner,
    make_evidence_binding,
    make_proposition,
)

pytestmark = pytest.mark.no_legacy_skip


@pytest.fixture(autouse=True)
def _isolate_runtime_and_clock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime-state"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = datetime(2026, 1, 1, tzinfo=timezone.utc)
            return value if tz else value.replace(tzinfo=None)

    import sentientos.resident_developmental_cognition as cognition_module
    import sentientos.resident_developmental_writeback as writeback_module
    monkeypatch.setattr(cognition_module, "datetime", FixedDatetime)
    monkeypatch.setattr(writeback_module, "datetime", FixedDatetime)


class ReopeningFixtureInvoker(PositionReasoningFixtureInvoker):
    retain_corrected_answer = False
    target_proposition_id: str | None = None

    def invoke(self, request, **kwargs):
        receipt = super().invoke(request, **kwargs)
        if request.purpose != "resident_developmental_retrieval_cognition":
            return receipt
        context = json.loads(request.prompt)
        prior = context.get("prior_epistemic_state")
        packets = prior.get("semantic_packets", []) if isinstance(prior, dict) else []
        packet = next((item for item in packets
            if item.get("proposition", {}).get("proposition_id")
                == self.target_proposition_id), None)
        if packet is None:
            return receipt
        stance = packet["state"]["stance"]
        if packet["last_update_event"]["reason"] == "source_reliability_revision":
            conclusion = ("contested" if self.retain_corrected_answer else "supported")
        else:
            conclusion = stance
        answer = self._answer(conclusion, packet,
            cite_packet=bool(packet["active_evidence_bindings"]
                or packet["removed_evidence_history"]))
        output = json.dumps(answer, sort_keys=True, separators=(",", ":"))
        updated = replace(receipt, output_text=output,
            output_digest=digest_payload({"output": output}),
            output_size_bytes=len(output.encode("utf-8")))
        self.receipts.pop(receipt.receipt_id, None)
        self.receipts[updated.receipt_id] = updated
        return updated


def _three_stage_projections(root: Path, *, include_peer: bool = False,
        peer_only_reopen: bool = False):
    state_owner = PersistentEpistemicStateOwner(root, allowed_namespaces=("experiment",))
    proposition = make_proposition(namespace="experiment", subject="sensor:beta",
        predicate="reports_safe", object_value=True, polarity="positive", qualifiers={},
        temporal_scope={"window": "current"}, context_scope={},
        proposition_class="descriptive")
    state_owner.register_proposition(proposition)

    peer = make_proposition(namespace="experiment", subject="sensor:gamma",
        predicate="reports_safe", object_value=True, polarity="positive", qualifiers={},
        temporal_scope={"window": "current"}, context_scope={},
        proposition_class="descriptive")
    peer_binding = None
    if include_peer:
        state_owner.register_proposition(peer)
        peer_binding = make_evidence_binding(proposition_id=peer.proposition_id,
            source_artifact_id="observation:peer-support",
            source_digest="sha256:" + "4" * 64,
            source_schema="fixture_observation:v1",
            source_class="independent_observation",
            observation_time="2026-01-01T00:00:00Z", evidence_relation="supports",
            dependency_kind="independently_sourced_observation",
            dependency_group="source-peer", upstream_binding_ids=(),
            freshness="current", reliability_posture="verified")
        state_owner.bind_evidence(peer_binding)
        state_owner.commit_update(proposition_id=peer.proposition_id,
            expected_predecessor_digest=None, stance="supported", reason="initialization",
            active_binding_ids=(peer_binding.binding_id,),
            added_binding_ids=(peer_binding.binding_id,),
            correlation_id="reopening-peer-support", tick=1,
            recorded_at="2026-01-01T00:01:00Z")

    def project(*, tick: int):
        prioritized = ((peer.proposition_id, proposition.proposition_id)
            if include_peer else (proposition.proposition_id,))
        return state_owner.cognitive_projection(max_states=2 if include_peer else 1,
            current_tick=tick, prioritized_proposition_ids=prioritized)

    def binding(artifact_id: str, seed: str, relation: str, source: str):
        return make_evidence_binding(proposition_id=proposition.proposition_id,
            source_artifact_id=artifact_id, source_digest="sha256:" + seed * 64,
            source_schema="fixture_observation:v1", source_class="independent_observation",
            observation_time="2026-01-01T00:00:00Z", evidence_relation=relation,
            dependency_kind="independently_sourced_observation", dependency_group=source,
            upstream_binding_ids=(), freshness="current", reliability_posture="verified")

    support = binding("observation:initial-support", "1", "supports", "source-a")
    state_owner.bind_evidence(support)
    initial_state, _ = state_owner.commit_update(proposition_id=proposition.proposition_id,
        expected_predecessor_digest=None, stance="supported", reason="initialization",
        active_binding_ids=(support.binding_id,), added_binding_ids=(support.binding_id,),
        correlation_id="reopening-initial", tick=1, recorded_at="2026-01-01T00:01:00Z")
    initial = project(tick=2)

    contradiction = binding("observation:contradiction", "2", "contradicts", "source-b")
    state_owner.bind_evidence(contradiction)
    corrected_state, _ = state_owner.commit_update(
        proposition_id=proposition.proposition_id,
        expected_predecessor_digest=initial_state.state_digest,
        stance="contested", reason="contradiction_arrival",
        active_binding_ids=(support.binding_id, contradiction.binding_id),
        added_binding_ids=(contradiction.binding_id,),
        correlation_id="reopening-correction", tick=2,
        recorded_at="2026-01-01T00:02:00Z")
    corrected = project(tick=3)

    new_support = binding("observation:independent-followup", "3", "supports", "source-c")
    state_owner.bind_evidence(new_support)
    if peer_only_reopen:
        assert include_peer and peer_binding is not None
        peer_followup = make_evidence_binding(proposition_id=peer.proposition_id,
            source_artifact_id="observation:peer-followup",
            source_digest="sha256:" + "5" * 64,
            source_schema="fixture_observation:v1",
            source_class="independent_observation",
            observation_time="2026-01-02T00:00:00Z", evidence_relation="supports",
            dependency_kind="independently_sourced_observation",
            dependency_group="source-peer-followup", upstream_binding_ids=(),
            freshness="current", reliability_posture="verified")
        state_owner.bind_evidence(peer_followup)
        peer_state = state_owner.current_state(peer.proposition_id)
        assert peer_state is not None
        state_owner.commit_update(proposition_id=peer.proposition_id,
            expected_predecessor_digest=peer_state.state_digest,
            stance="supported", reason="new_evidence",
            active_binding_ids=(peer_binding.binding_id, peer_followup.binding_id),
            added_binding_ids=(peer_followup.binding_id,),
            correlation_id="reopening-peer-only-followup", tick=3,
            recorded_at="2026-01-02T00:00:00Z")
    else:
        state_owner.commit_update(proposition_id=proposition.proposition_id,
            expected_predecessor_digest=corrected_state.state_digest,
            stance="supported", reason="source_reliability_revision",
            active_binding_ids=(support.binding_id, new_support.binding_id),
            added_binding_ids=(new_support.binding_id,),
            removed_binding_ids=(contradiction.binding_id,),
            correlation_id="reopening-new-evidence", tick=3,
            recorded_at="2026-01-01T00:03:00Z")
    reopened = project(tick=4)
    assert initial is not None and corrected is not None and reopened is not None
    if include_peer:
        assert initial.proposition_ids[0] == peer.proposition_id
        assert corrected.proposition_ids[0] == peer.proposition_id
        assert reopened.proposition_ids[0] == peer.proposition_id
    return initial, corrected, reopened, proposition, support, contradiction, new_support


def _observe(root: Path, projection, *, target_proposition_id: str,
        retain_corrected_answer: bool = False):
    invoker = ReopeningFixtureInvoker()
    invoker.retain_corrected_answer = retain_corrected_answer
    invoker.target_proposition_id = target_proposition_id
    cognition, _ = owner(_cognition_root(root.parent, root.name), invoker=invoker,
        allowed_source_kinds=("capability_registry", "owner_introspection"),
        max_selected_facts=16)
    cognition.run_tick(snapshot=snapshot(), tick_id="reopening-history-seed")
    result = cognition.run_tick(snapshot=snapshot(),
        tick_id=f"{root.name}-measurement", prior_epistemic_state=projection)
    request = next(row for row in invoker.requests
        if row.purpose == "resident_developmental_retrieval_cognition")
    receipt = next(row for row in invoker.receipts.values()
        if row.request["request_id"] == request.request_id)
    return cognition, request, result.cognition_observation_ids[0], receipt


def _series(tmp_path: Path, *, retain_corrected_answer: bool = False,
        include_peer: bool = False, peer_only_reopen: bool = False):
    initial_projection, corrected_projection, reopened_projection, proposition, support, contradiction, new_support = (
        _three_stage_projections(tmp_path / "epistemic", include_peer=include_peer,
            peer_only_reopen=peer_only_reopen)
    )
    before = _observe(tmp_path / "initial", initial_projection,
        target_proposition_id=proposition.proposition_id)
    corrected = _observe(tmp_path / "corrected", corrected_projection,
        target_proposition_id=proposition.proposition_id)
    reopened = _observe(tmp_path / "reopened", reopened_projection,
        target_proposition_id=proposition.proposition_id,
        retain_corrected_answer=retain_corrected_answer)
    initial_key = IndependentAnswerKey("supported", "supported", "support_retained",
        (support.binding_id,))
    corrected_key = IndependentAnswerKey("contested", "contested", "conflict_preserved",
        (support.binding_id, contradiction.binding_id))
    reopened_key = IndependentAnswerKey("supported", "supported",
        "new_evidence_resolves_conflict", (support.binding_id, new_support.binding_id))
    correction_case = RevisionCase(case_id="reopening-correction", kind="contrary_evidence",
        proposition_id=proposition.proposition_id, evaluator_version="reopening-v1",
        before_prompt_digest="sha256:" + digest_payload({"prompt": before[1].prompt}),
        after_prompt_digest="sha256:" + digest_payload({"prompt": corrected[1].prompt}),
        before_key=initial_key, after_key=corrected_key, commitment_nonce="4" * 64)
    reopening_case = RevisionCase(case_id="justified-reopening", kind="outdated_evidence",
        proposition_id=proposition.proposition_id, evaluator_version="reopening-v1",
        before_prompt_digest="sha256:" + digest_payload({"prompt": corrected[1].prompt}),
        after_prompt_digest="sha256:" + digest_payload({"prompt": reopened[1].prompt}),
        before_key=corrected_key, after_key=reopened_key, commitment_nonce="5" * 64)
    return evaluate_correction_reopening_series(
        series=EpistemicCorrectionReopeningSeries(correction_case, reopening_case),
        initial_reader=before[0], corrected_reader=corrected[0], reopened_reader=reopened[0],
        initial_observation_id=before[2], corrected_observation_id=corrected[2],
        reopened_observation_id=reopened[2], initial_projection=initial_projection,
        corrected_projection=corrected_projection, reopened_projection=reopened_projection,
        initial_prompt=before[1].prompt, corrected_prompt=corrected[1].prompt,
        reopened_prompt=reopened[1].prompt, initial_receipt=before[3],
        corrected_receipt=corrected[3], reopened_receipt=reopened[3])


def test_new_evidence_can_justify_reopening_a_corrected_position(tmp_path: Path) -> None:
    report = _series(tmp_path)
    assert report["status"] == "series_passed"
    assert report["initial_correction_passed"] is True
    assert report["reopening_passed"] is True
    assert report["new_active_evidence_count"] == 1
    assert report["new_evidence_reaches_answer_key"] is True
    assert report["justified_reopening"]["after"]["relevant_packet_delivered"] is True
    assert report["justified_reopening"]["after"]["answer_correct"] is True
    assert report["reopening_justification_independently_verified"] is False
    assert report["real_model_qualification_established"] is False


def test_rigidly_retaining_the_correction_fails_after_new_evidence(tmp_path: Path) -> None:
    report = _series(tmp_path, retain_corrected_answer=True)
    assert report["status"] == "series_failed"
    assert report["initial_correction_passed"] is True
    assert report["reopening_passed"] is False
    assert report["new_evidence_reaches_answer_key"] is True
    assert report["justified_reopening"]["state_transition_appropriate"] is True
    assert report["justified_reopening"]["after"]["answer_correct"] is False


def test_reopening_scores_target_evidence_with_peer_packet_first(tmp_path: Path) -> None:
    report = _series(tmp_path, include_peer=True)
    assert report["status"] == "series_passed", report
    assert report["new_active_evidence_count"] == 1
    assert report["new_evidence_reaches_answer_key"] is True
    assert report["initial_correction_passed"] is True
    assert report["reopening_passed"] is True


def test_peer_only_new_evidence_does_not_justify_target_reopening(
        tmp_path: Path) -> None:
    report = _series(tmp_path, include_peer=True, peer_only_reopen=True)
    assert report["status"] == "insufficient"
    assert report["new_active_evidence_count"] == 0
    assert report["new_evidence_reaches_answer_key"] is False
    assert report["reopening_passed"] is False


def test_new_evidence_must_be_named_by_reopening_answer_key() -> None:
    initial = IndependentAnswerKey("supported", "supported", "support", ("a",))
    corrected = IndependentAnswerKey("contested", "contested", "conflict", ("a", "b"))
    with pytest.raises(ValueError, match="epistemic_correction_reopening_series_invalid"):
        EpistemicCorrectionReopeningSeries(
            RevisionCase("correction", "contrary_evidence", "p", "v1",
                "sha256:" + "1" * 64, "sha256:" + "2" * 64,
                initial, corrected, "4" * 64),
            RevisionCase("reopening", "outdated_evidence", "p", "v1",
                "sha256:" + "2" * 64, "sha256:" + "3" * 64,
                corrected, IndependentAnswerKey("supported", "supported", "same", ("a",)),
                "5" * 64),
        ).commitment()
