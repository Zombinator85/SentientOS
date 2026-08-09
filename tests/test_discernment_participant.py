from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.control_plane_kernel import ControlPlaneKernel, LifecyclePhase
from sentientos.discernment_participant import DiscernmentParticipantRequest, generate_participant_judgment
from sentientos.discernment_trial import BlindTrialCustody
from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker
from sentientos.innerworld.orchestrator import InnerWorldOrchestrator
from sentientos.local_model_authority import LocalModelAuthorityMap, LocalModelAuthorityRecord, digest_payload
from sentientos.truth.epistemic_orientation import EpistemicOrientation

pytestmark = pytest.mark.no_legacy_skip


QUESTION = "Will the bounded change reduce failures?"
SNAPSHOT = {"failures": 4, "source": "frozen-fixture"}


def _judgment(**updates: object) -> str:
    value = {
        "schema_version": "sentientos.discernment_judgment.v1", "proposition": QUESTION,
        "interpretation": "The bounded evidence provisionally supports a reduction.",
        "stance": "support", "confidence": 0.72,
        "strongest_objection": "The sample is small.",
        "alternate_interpretations": ["The reduction is noise."], "missing_evidence": ["A second sample."],
        "what_would_change_judgment": ["trial.failure_rate rises"],
        "expected_observation_keys": ["trial.failure_rate"],
        "disconfirming_observation_keys": ["trial.regression"],
        "predicted_consequences": ["fewer bounded failures"], "preferred_next_move": "observe the frozen trial",
        "rejected_next_moves": ["adopt without review"], "unresolved_contradictions": [],
    }
    value.update(updates)
    return json.dumps(value)


class DeterministicLocalModel:
    def __init__(self, output: str = "") -> None:
        self.output = output or _judgment()
        self.prompts: list[str] = []

    def generate(self, prompt: str, **kwargs: object) -> str:
        self.prompts.append(prompt)
        return self.output


def _authority() -> LocalModelAuthorityMap:
    seed = {"engine": "llama_cpp", "semantic_artifact_identity": "sha256:model",
            "configuration_digest": "config", "sidecar_metadata_digest": None}
    record = LocalModelAuthorityRecord(
        model_id="lma-" + digest_payload(seed)[:24], engine="llama_cpp", name="fixture-local",
        semantic_artifact_identity="sha256:model", model_content_sha256="model", artifact_size_bytes=5,
        sidecar_metadata_digest=None, configuration_digest="config", max_context_tokens=4096,
        generation_ceilings={"max_new_tokens": 512}, local_files_only=True,
        custom_model_code_posture="disabled", custom_model_code_opt_in=False,
        allowed_invocation_purposes=("local_user_chat", "genesis_proposal_advice", "discernment_judgment"),
        provider_network_posture="blocked_local_files_only", tool_posture="blocked", memory_posture="blocked",
        action_posture="blocked", runtime_eligibility_status="eligible", reason_codes=("eligible_local_model",),
        disposition="production_candidate", proof_references=("fixture:model",),
    )
    semantic = {"schema_version": "local_model_authority_map.v1", "records": [record.to_dict()]}
    digest = digest_payload(semantic)
    return LocalModelAuthorityMap((record,), "lmam-" + digest[:24], digest, "2030-01-01T00:00:00Z", {"eligible_count": 1})


def _run(tmp_path: Path, model: DeterministicLocalModel, **changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "repo_root": Path.cwd(), "subject_id": "bounded-change", "question": QUESTION,
        "initial_evidence_snapshot": SNAPSHOT, "evaluation_context": {"horizon": "one week"},
        "allowed_observation_namespace": "trial", "observed_at": "2030-01-01T00:00:00Z",
        "question_digest": digest_payload(QUESTION), "evidence_snapshot_digest": digest_payload(SNAPSHOT),
        "epistemic_observations": ({"entry_id": "obs-1", "claim": "four failures were observed",
                                     "source_class": "external_witness", "confidence": 1.0},),
        "inner_world_cycle_input": {"errors": 0.2, "progress": 0.6, "novelty": 0.1, "plan": {}},
    }
    values.update(changes)
    kernel = ControlPlaneKernel(phase=LifecyclePhase.RUNTIME, decisions_path=tmp_path / "control.jsonl")
    invoker = GovernedLocalModelInvoker(model=model, authority_map=_authority(), kernel=kernel, runtime_root=tmp_path / "model")
    return generate_participant_judgment(DiscernmentParticipantRequest(**values), invoker=invoker,
                                         epistemic_orientation=EpistemicOrientation(), inner_world=InnerWorldOrchestrator())


def test_process_real_participant_is_accepted_and_frozen_by_blind_custody(tmp_path: Path) -> None:
    model = DeterministicLocalModel()
    result = _run(tmp_path, model)
    submission = result["trial_submission"]
    assert submission["interpretation"].startswith("The bounded evidence")
    assert result["model_invocation"]["invocation_receipt_digest"]
    assert result["discernment_packet"]["packet_digest"] == submission["source_discernment_packet_digest"]
    inner = result["discernment_packet"]["evaluation_context"]["inner_world_context"]
    assert inner["asserts_final_position"] is False
    assert {"ethics", "cognitive_report", "workspace_spotlight", "inner_dialogue", "value_drift"} <= set(inner["structured_context"])
    assert "unresolved" not in inner
    assert all(value is False for value in result["authority_posture"].values())
    assert "opaque_participant" not in model.prompts[0]

    custody = BlindTrialCustody(tmp_path / "trial")
    custody.create_trial({"trial_id": "t1", "question": QUESTION, "subject_id": "bounded-change",
        "created_at": "2030-01-01T00:00:00Z", "initial_evidence_snapshot": SNAPSHOT,
        "expected_participant_count": 2, "opaque_participant_slots": ["a", "b"], "trial_nonce": "nonce",
        "evaluation_horizon": {"days": 7}, "allowed_observation_namespace": "trial", "custody_root_identity": "fixture"})
    custody.register_participant("a", "sealed-sentientos"); custody.register_participant("b", "sealed-peer")
    custody.submit("a", submission)
    custody.submit("b", {**submission, "stance": "suspend", "confidence": None, "sealed_at": "2030-01-01T00:01:00Z"})
    assert custody.trial_state()["judgment_set_frozen"] is True


def test_final_fields_are_not_api_overrides_and_failures_suspend_truthfully(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        DiscernmentParticipantRequest(repo_root=Path.cwd(), subject_id="s", question=QUESTION,
            initial_evidence_snapshot=SNAPSHOT, evaluation_context={}, allowed_observation_namespace="trial",
            observed_at="2030-01-01T00:00:00Z", stance="oppose")  # type: ignore[call-arg]
    result = _run(tmp_path, DeterministicLocalModel("not-json"), inner_world_cycle_input=None,
                  epistemic_observations=())
    assert result["judgment"]["stance"] == "suspend"
    assert result["judgment"]["confidence"] is None
    assert result["judgment"]["interpretation"] == ""
    assert result["model_invocation"]["invocation_status"] == "output_malformed"


def test_digest_mismatch_and_observation_namespace_escape_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="question digest mismatch"):
        _run(tmp_path, DeterministicLocalModel(), question_digest="wrong")
    escaped = DeterministicLocalModel(_judgment(expected_observation_keys=["peer.secret"]))
    result = _run(tmp_path / "escape", escaped)
    assert result["judgment"]["stance"] == "suspend"
    assert result["model_invocation"]["invocation_status"] == "output_malformed"
