from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_resident_developmental_cognition import (  # noqa: E402
    FakeInvoker, SessionBoundFakeInvoker, epistemic_projection, owner, snapshot,
)
from sentientos.epistemic_revision_qualification import (
    IndependentAnswerKey, RevisionCase, _prompt_context_mismatch,
    capture_position, evaluate_pair, evaluate_verified_probe_pair,
)
from sentientos.governed_local_model_invocation import (
    RESIDENT_EPISTEMIC_REVISION_OUTPUT_SCHEMA,
)
from sentientos.epistemic_qualification_execution_binding import build_execution_binding
from sentientos.local_model_authority import digest_payload
from sentientos.resident_developmental_cognition import ResidentDevelopmentalCognitionError


pytestmark = pytest.mark.no_legacy_skip


def test_pair_context_comparison_ignores_treatments_and_detects_unlisted_fields() -> None:
    before = {"instruction": "same", "prior_epistemic_state": {"stance": "supported"},
        "current_evidence": {"fact": "old"}, "future_prompt_field": {"mode": "one"}}
    after = {"instruction": "same", "prior_epistemic_state": {"stance": "contradicted"},
        "current_evidence": {"fact": "new"}, "future_prompt_field": {"mode": "one"}}

    assert _prompt_context_mismatch(before, after) is False
    before["epistemic_revision_probe"] = {
        "response_contract": "v2", "allowed_evidence_binding_ids": ["old"]}
    after["epistemic_revision_probe"] = {
        "response_contract": "v2", "allowed_evidence_binding_ids": ["new"]}
    assert _prompt_context_mismatch(before, after) is False
    after["epistemic_revision_probe"]["response_contract"] = "v3"
    assert _prompt_context_mismatch(before, after) is True
    after["epistemic_revision_probe"]["response_contract"] = "v2"
    before["developmental_history_target_model_identity"] = "model-a"
    after["developmental_history_target_model_identity"] = "model-b"
    assert _prompt_context_mismatch(before, after) is True
    assert _prompt_context_mismatch(before, after,
        additional_treatment_fields=("developmental_history_target_model_identity",)) is False
    del before["developmental_history_target_model_identity"]
    del after["developmental_history_target_model_identity"]
    after["future_prompt_field"] = {"mode": "two"}
    assert _prompt_context_mismatch(before, after) is True


def test_successor_model_identity_is_the_only_additional_prompt_treatment() -> None:
    before = {"instruction": "same",
        "developmental_history_target_model_identity": {"model": "a"},
        "future_prompt_field": "same"}
    after = {"instruction": "same",
        "developmental_history_target_model_identity": {"model": "b"},
        "future_prompt_field": "same"}

    assert _prompt_context_mismatch(before, after) is True
    assert _prompt_context_mismatch(before, after,
        additional_treatment_fields=("developmental_history_target_model_identity",)) is False
    after["future_prompt_field"] = "changed"
    assert _prompt_context_mismatch(before, after,
        additional_treatment_fields=("developmental_history_target_model_identity",)) is True


@pytest.fixture(autouse=True)
def _isolate_runtime_and_timestamps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


class StructuredFixtureInvoker(SessionBoundFakeInvoker):
    """Synthetic response source; exercises the owner pipe without a provider."""

    def invoke(self, request, **kwargs):
        receipt = super().invoke(request, **kwargs)
        if request.purpose != "resident_developmental_retrieval_cognition":
            return receipt
        output = '{"conclusion":"uncertain","lesson_candidate":null}'
        simulated = replace(receipt, status="admitted_simulation", output_text=output,
            output_digest=digest_payload({"output": output}),
            output_size_bytes=len(output.encode("utf-8")),
            effects={**dict(receipt.effects), "local_model_inference": False})
        self.receipts.pop(receipt.receipt_id, None)
        self.receipts[simulated.receipt_id] = simulated
        return simulated


def _run_condition(root: Path, projection):
    invoker = StructuredFixtureInvoker()
    cognition, _ = owner(root, invoker=invoker)
    cognition.run_tick(snapshot=snapshot(), tick_id="history-seed")
    result = cognition.run_tick(snapshot=snapshot(), tick_id="measured-response",
        prior_epistemic_state=projection)
    request = next(item for item in invoker.requests
        if item.purpose == "resident_developmental_retrieval_cognition")
    receipt = next(value for value in invoker.receipts.values()
        if value.request["request_id"] == request.request_id)
    return cognition, request, result.cognition_observation_ids[0], receipt


def test_pair_scores_canonical_position_and_actual_owner_response(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    projection, proposition, _state = epistemic_projection(tmp_path / "epistemic")
    # The normal capture entry point accepts the existing semantic projection.
    position_owner, _, _ = epistemic_projection(tmp_path / "capture")
    capture_owner = __import__("sentientos.persistent_epistemic_state", fromlist=[
        "PersistentEpistemicStateOwner"]).PersistentEpistemicStateOwner(
            tmp_path / "capture", allowed_namespaces=["embodiment"])
    captured = capture_position(capture_owner, proposition_id=proposition.proposition_id,
        current_tick=2)
    assert captured.proposition_ids == position_owner.proposition_ids

    before_owner, before_request, before_id, before_receipt = _run_condition(
        tmp_path / "before", projection)
    after_owner, after_request, after_id, after_receipt = _run_condition(
        tmp_path / "after", projection)
    case = RevisionCase(case_id="retention-1", kind="retained_correction",
        proposition_id=proposition.proposition_id, evaluator_version="v1",
        before_prompt_digest="sha256:" + digest_payload({"prompt": before_request.prompt}),
        after_prompt_digest="sha256:" + digest_payload({"prompt": after_request.prompt}),
        before_key=IndependentAnswerKey("unknown", "uncertain", "retain_uncertainty", ()),
        after_key=IndependentAnswerKey("unknown", "uncertain", "retain_uncertainty", ()),
        commitment_nonce="a" * 64)

    report = evaluate_pair(case=case, before_reader=before_owner,
        after_reader=after_owner, before_observation_id=before_id,
        after_observation_id=after_id, before_projection=projection,
        after_projection=projection, before_prompt=before_request.prompt,
        after_prompt=after_request.prompt, before_receipt=before_receipt,
        after_receipt=after_receipt)

    assert report["status"] == "case_passed", (report["control_mismatches"],
        report["before"]["measurement_status"], report["after"]["measurement_status"],
        report["state_transition_appropriate"])
    assert report["before"]["relevant_packet_delivered"] is True
    assert report["after"]["answer_correct"] is True
    assert report["after"]["reason_code_correct"] is None
    assert report["after"]["citations_correct"] is True
    assert report["after"]["citation_scoring_status"] == "exact_subject_visible_evidence_ids"
    before_binding = report["before"]["execution_binding"]
    after_binding = report["after"]["execution_binding"]
    assert before_binding["complete"] is True
    assert before_binding["model_id"] == "model-a"
    assert before_binding["model_artifact_digest"] == "sha256:model"
    assert before_binding["active_model_identity_digest"].startswith("sha256:")
    assert before_binding["generation_config_digest"].startswith("sha256:")
    assert before_binding["evaluator_version"] == "v1"
    assert before_binding["projection_digest"] == projection.projection_digest
    assert before_binding["condition"] == "before"
    assert after_binding["condition"] == "after"
    assert before_binding["active_model_identity_digest"] == after_binding["active_model_identity_digest"]
    assert before_binding["generation_config_digest"] == after_binding["generation_config_digest"]
    assert report["real_model_qualification_established"] is False
    assert report["authority"] is False


def test_owner_epistemic_revision_probe_requests_scored_json_without_key(
        tmp_path: Path) -> None:
    class ProbeFixtureInvoker(StructuredFixtureInvoker):
        def invoke(self, request, **kwargs):
            receipt = super().invoke(request, **kwargs)
            if request.purpose != "resident_developmental_retrieval_cognition":
                return receipt
            output = '{"conclusion":"unknown","reason_code":"retain_uncertainty","evidence_ids":[]}'
            simulated = replace(receipt, output_text=output,
                output_digest=digest_payload({"output": output}),
                output_size_bytes=len(output.encode("utf-8")))
            self.receipts.pop(receipt.receipt_id, None)
            self.receipts[simulated.receipt_id] = simulated
            return simulated

    projection, _proposition, _state = epistemic_projection(tmp_path / "epistemic")
    invoker = ProbeFixtureInvoker()
    cognition, _ = owner(tmp_path / "cognition", invoker=invoker)
    result = cognition.run_epistemic_revision_probe_once(snapshot=snapshot(),
        tick_id="epistemic-revision-probe", prior_epistemic_state=projection)

    assert result.status == "epistemic_revision_probe_completed"
    assert len(result.cognition_observation_ids) == 1
    assert len(invoker.requests) == 1
    request = next(row for row in invoker.requests
        if row.purpose == "resident_developmental_retrieval_cognition")
    assert request.expected_output_format == "json"
    assert request.structured_output_schema == RESIDENT_EPISTEMIC_REVISION_OUTPUT_SCHEMA
    context = json.loads(request.prompt)
    assert context["epistemic_revision_probe"]["response_contract"] == (
        "sentientos.epistemic_revision_answer:v2")
    packet = context["prior_epistemic_state"]["semantic_packets"][0]
    expected_binding_ids = sorted({
        row["binding_id"] for collection in (
            "active_evidence_bindings", "removed_evidence_history")
        for row in packet[collection]})
    assert context["epistemic_revision_probe"]["allowed_evidence_binding_ids"] == (
        expected_binding_ids)
    assert "Do not cite fact IDs, packet IDs, or any other identifier." in context["instruction"]
    assert "expected_stance" not in request.prompt
    receipt = next(row for row in invoker.receipts.values()
        if row.request["request_id"] == request.request_id)
    assert json.loads(receipt.output_text) == {
        "conclusion": "unknown", "reason_code": "retain_uncertainty", "evidence_ids": []}
    capture_path = (cognition.epistemic_revision_probe_captures_root
        / f"{result.cognition_observation_ids[0]}.json")
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    assert capture["schema_version"] == "sentientos.epistemic_revision_probe_capture:v1"
    assert capture["prompt"] == request.prompt
    assert capture["receipt"]["output_text"] == receipt.output_text
    assert capture["answer_key_included"] is False
    assert "expected_stance" not in capture["prompt"]
    assert result.written_record_id is None
    assert result.writeback_receipt_id is None

    verified = cognition.verified_epistemic_revision_probe_capture(
        result.cognition_observation_ids[0])
    assert verified.prompt == request.prompt
    assert verified.receipt.output_text == receipt.output_text
    assert verified.receipt.receipt_digest == receipt.receipt_digest
    assert verified.observation_digest == capture["observation_digest"]

    # Recomputing the capture's local digest cannot rebind a changed prompt to
    # the independently persisted request and cognition observation.
    capture["prompt"] += " altered"
    capture.pop("capture_digest")
    capture["capture_digest"] = "sha256:" + digest_payload(capture)
    capture_path.write_text(json.dumps(capture, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    with pytest.raises(ResidentDevelopmentalCognitionError,
            match="epistemic_revision_probe_capture_invalid"):
        cognition.verified_epistemic_revision_probe_capture(
            result.cognition_observation_ids[0])


def test_verified_captures_feed_the_existing_pair_scorer(tmp_path: Path) -> None:
    class ProbeFixtureInvoker(StructuredFixtureInvoker):
        def invoke(self, request, **kwargs):
            receipt = super().invoke(request, **kwargs)
            if request.purpose != "resident_developmental_retrieval_cognition":
                return receipt
            output = '{"conclusion":"unknown","reason_code":"unpreregistered_fixture_label","evidence_ids":[]}'
            simulated = replace(receipt, output_text=output,
                output_digest=digest_payload({"output": output}),
                output_size_bytes=len(output.encode("utf-8")))
            self.receipts.pop(receipt.receipt_id, None)
            self.receipts[simulated.receipt_id] = simulated
            return simulated

    projection, proposition, _state = epistemic_projection(tmp_path / "epistemic")
    before_owner, _ = owner(tmp_path / "before", invoker=ProbeFixtureInvoker())
    after_owner, _ = owner(tmp_path / "after", invoker=ProbeFixtureInvoker())
    before_result = before_owner.run_epistemic_revision_probe_once(snapshot=snapshot(),
        tick_id="captured-pair-before", prior_epistemic_state=projection)
    after_result = after_owner.run_epistemic_revision_probe_once(snapshot=snapshot(),
        tick_id="captured-pair-after", prior_epistemic_state=projection)
    before_id = before_result.cognition_observation_ids[0]
    after_id = after_result.cognition_observation_ids[0]
    before_capture = before_owner.verified_epistemic_revision_probe_capture(before_id)
    after_capture = after_owner.verified_epistemic_revision_probe_capture(after_id)
    # This fixture test exercises only capture-to-scorer wiring; fixture prompt
    # generation after capture does not establish experimental preregistration.
    key = IndependentAnswerKey("unknown", "unknown", "retain_uncertainty", ())
    case = RevisionCase(case_id="captured-retention", kind="retained_correction",
        proposition_id=proposition.proposition_id, evaluator_version="v1",
        before_prompt_digest="sha256:" + digest_payload({"prompt": before_capture.prompt}),
        after_prompt_digest="sha256:" + digest_payload({"prompt": after_capture.prompt}),
        before_key=key, after_key=key, commitment_nonce="9" * 64)

    report = evaluate_verified_probe_pair(case=case,
        before_reader=before_owner, after_reader=after_owner,
        before_observation_id=before_id, after_observation_id=after_id,
        before_projection=projection, after_projection=projection)

    assert report["status"] == "case_passed"
    assert report["before"]["answer_correct"] is True
    assert report["after"]["answer_correct"] is True
    assert report["after"]["reason_code_correct"] is None
    assert report["after"]["reason_code_scoring_status"] == (
        "not_scored_probe_vocabulary_not_exposed")
    assert report["real_model_qualification_established"] is False


def test_probe_scorer_records_malformed_stance_as_invalid_answer(tmp_path: Path) -> None:
    class MalformedProbeInvoker(StructuredFixtureInvoker):
        def invoke(self, request, **kwargs):
            receipt = super().invoke(request, **kwargs)
            if request.purpose != "resident_developmental_retrieval_cognition":
                return receipt
            output = '{"conclusion":[],"reason_code":"fixture","evidence_ids":[]}'
            malformed = replace(receipt, output_text=output,
                output_digest=digest_payload({"output": output}),
                output_size_bytes=len(output.encode("utf-8")))
            self.receipts.pop(receipt.receipt_id, None)
            self.receipts[malformed.receipt_id] = malformed
            return malformed

    projection, proposition, _state = epistemic_projection(tmp_path / "epistemic")
    before_owner, _ = owner(tmp_path / "before", invoker=MalformedProbeInvoker())
    after_owner, _ = owner(tmp_path / "after", invoker=MalformedProbeInvoker())
    before_result = before_owner.run_epistemic_revision_probe_once(snapshot=snapshot(),
        tick_id="malformed-probe-before", prior_epistemic_state=projection)
    after_result = after_owner.run_epistemic_revision_probe_once(snapshot=snapshot(),
        tick_id="malformed-probe-after", prior_epistemic_state=projection)
    before_capture = before_owner.verified_epistemic_revision_probe_capture(
        before_result.cognition_observation_ids[0])
    after_capture = after_owner.verified_epistemic_revision_probe_capture(
        after_result.cognition_observation_ids[0])
    key = IndependentAnswerKey("unknown", "unknown", "unused_reason_key", ())
    case = RevisionCase(case_id="malformed-probe", kind="retained_correction",
        proposition_id=proposition.proposition_id, evaluator_version="v1",
        before_prompt_digest="sha256:" + digest_payload({"prompt": before_capture.prompt}),
        after_prompt_digest="sha256:" + digest_payload({"prompt": after_capture.prompt}),
        before_key=key, after_key=key, commitment_nonce="b" * 64)

    report = evaluate_verified_probe_pair(case=case,
        before_reader=before_owner, after_reader=after_owner,
        before_observation_id=before_capture.observation_id,
        after_observation_id=after_capture.observation_id,
        before_projection=projection, after_projection=projection)

    assert report["status"] == "case_failed"
    assert report["before"]["measurement_status"] == "scored"
    assert report["before"]["answer_shape_valid"] is False
    assert report["before"]["reason_code_correct"] is None


def test_probe_expected_prompt_digest_blocks_before_invocation(tmp_path: Path) -> None:
    projection, _proposition, _state = epistemic_projection(tmp_path / "epistemic")
    invoker = SessionBoundFakeInvoker()
    cognition, _ = owner(tmp_path / "cognition", invoker=invoker)

    with pytest.raises(ResidentDevelopmentalCognitionError,
            match="epistemic_revision_probe_prompt_digest_mismatch"):
        cognition.run_epistemic_revision_probe_once(snapshot=snapshot(),
            tick_id="wrong-preregistered-prompt",
            prior_epistemic_state=projection,
            expected_prompt_digest="sha256:" + "0" * 64)

    assert invoker.requests == []


@pytest.mark.parametrize("cite_unrelated_fact", [False, True])
def test_rootless_epistemic_session_scores_only_allowed_evidence_bindings(
        tmp_path: Path, cite_unrelated_fact: bool) -> None:
    class RootlessFixtureInvoker(FakeInvoker):
        def __init__(self, *, cite_unrelated: bool) -> None:
            super().__init__()
            self.cite_unrelated = cite_unrelated
            self.active_model_identity = {
                "engine": "llama_cpp", "posture": "rootless_experimental",
                "fallback": False, "model_content_sha256": "1" * 64,
                "artifact_size_bytes": 5}
            self.receipts = {}

        def observed_current_model_identity(self):
            return dict(self.active_model_identity)

        def invoke(self, request, **kwargs):
            receipt = super().invoke(request, **kwargs)
            context = json.loads(request.prompt)
            packets = context["prior_epistemic_state"]["semantic_packets"]
            packet = packets[0]
            answer = {"conclusion": packet["state"]["stance"],
                "reason_code": "fixture_reason",
                "evidence_ids": [row["binding_id"]
                    for row in packet["active_evidence_bindings"]]}
            if self.cite_unrelated:
                answer["evidence_ids"].append(
                    context["current_evidence"]["fact_ids"][0])
            output = json.dumps(answer, sort_keys=True, separators=(",", ":"))
            completed = replace(receipt, output_text=output,
                output_digest=digest_payload({"output": output}),
                output_size_bytes=len(output.encode("utf-8")))
            self.receipts[completed.receipt_id] = completed
            return completed

        def verify_persisted_invocation_receipt(self, receipt_id,
                receipt_digest, **expected):
            receipt = self.receipts[receipt_id]
            assert receipt.receipt_digest == receipt_digest
            assert receipt.request["request_id"] == expected["expected_request_id"]
            assert receipt.request["request_digest"] == expected["expected_request_digest"]
            assert receipt.request["active_model_identity"] == (
                expected["expected_active_model_identity"])
            return receipt.to_dict(include_output=True)

    projection, proposition, _state = epistemic_projection(tmp_path / "epistemic")
    invoker = RootlessFixtureInvoker(cite_unrelated=cite_unrelated_fact)
    cognition, _ = owner(tmp_path / "cognition", invoker=invoker)
    ticks = ("rootless-qualification-before", "rootless-qualification-after")
    previews = [cognition.preview_epistemic_revision_probe_prompt(
        snapshot=snapshot(), tick_id=tick, prior_epistemic_state=projection)
        for tick in ticks]
    key = IndependentAnswerKey("unknown", "unknown", "not_scored", tuple())
    session = {
        "schema_version": "sentientos.rootless_experimental_cognition_session:v1",
        "session_id": "rootless-epistemic-session-" + "a" * 24,
        "run_id": "rootless-epistemic-run-" + "b" * 24,
        "preregistration_digest": "c" * 64,
        "model_manifest_digest": "d" * 64,
        "runtime_bundle_digest": "e" * 64,
        "active_model_identity_digest": digest_payload(
            {"identity": invoker.active_model_identity}),
        "purpose": "rootless_experimental_epistemic_revision_probe",
        "production_authority": False,
        "eligible_as_production_serving_evidence": False,
    }
    cognition.bind_rootless_experimental_epistemic_session(session)
    results = [cognition.run_epistemic_revision_probe_once(snapshot=snapshot(),
        tick_id=tick, prior_epistemic_state=projection,
        expected_prompt_digest=preview["prompt_digest"])
        for tick, preview in zip(ticks, previews)]
    captures = [cognition.verified_epistemic_revision_probe_capture(
        result.cognition_observation_ids[0]) for result in results]
    assert all(cognition.verified_cognition_observation(
        capture.observation_id).get("serving_session_id") is None
        for capture in captures)
    assert all(capture.request["purpose"] ==
        "rootless_experimental_epistemic_revision_probe" for capture in captures)
    case = RevisionCase(case_id="rootless-fixture-pair", kind="retained_correction",
        proposition_id=proposition.proposition_id, evaluator_version="rootless-v1",
        before_prompt_digest=previews[0]["prompt_digest"],
        after_prompt_digest=previews[1]["prompt_digest"], before_key=key,
        after_key=key, commitment_nonce="f" * 64)
    report = evaluate_verified_probe_pair(case=case,
        before_reader=cognition, after_reader=cognition,
        before_observation_id=captures[0].observation_id,
        after_observation_id=captures[1].observation_id,
        before_projection=projection, after_projection=projection)
    assert report["status"] == ("case_failed" if cite_unrelated_fact else "case_passed")
    assert report["after"]["answer_correct"] is True
    assert report["after"]["citations_correct"] is (not cite_unrelated_fact)
    assert report["before"]["execution_session_kind"] == "rootless_experimental"
    assert report["after"]["execution_session_kind"] == "rootless_experimental"
    assert report["real_model_qualification_established"] is False


def test_execution_binding_is_stable_model_specific_and_incomplete_when_identity_is_missing() -> None:
    common = dict(case_id="case-1", evaluator_version="v3", condition="before",
        model_id="worker-a", model_artifact_digest="sha256:artifact-a",
        active_model_identity={"model_content_sha256": "a" * 64},
        generation_config={"temperature": 0}, prompt_digest="sha256:" + "1" * 64,
        projection_digest="sha256:" + "2" * 64, observation_digest="observation",
        receipt_digest="receipt", output_digest="output")
    first = build_execution_binding(**common)
    repeated = build_execution_binding(**common)
    replacement = build_execution_binding(**{**common, "model_id": "worker-b",
        "model_artifact_digest": "sha256:artifact-b",
        "active_model_identity": {"model_content_sha256": "b" * 64}})
    incomplete = build_execution_binding(**{**common, "model_artifact_digest": None})

    assert first == repeated
    assert first["binding_digest"] != replacement["binding_digest"]
    assert first["complete"] is True
    assert incomplete["complete"] is False


def test_case_rejects_unbound_or_invalid_oracle_metadata() -> None:
    key = IndependentAnswerKey("unknown", "answer", "reason", ())
    case = RevisionCase("pressure", "unsupported_pressure", "p", "v1",
        "unbound", "unbound", key, key, "b" * 64)
    with pytest.raises(ValueError, match="qualification_prompt_digest_invalid"):
        case.commitment()
