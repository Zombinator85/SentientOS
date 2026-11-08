"""Run one bounded Hermes trial through the resident developmental cognition owner.

The body and observer are synthetic fixtures. The developmental record, cognition
observations, history ablation, model identity, and local inference receipts use
the existing governed SentientOS owners. This is not production serving evidence.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict
import subprocess
import sys
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Bind imports to this checkout even when WSL's login shell starts elsewhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

workspace = Path(os.environ.get(
    "SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE",
    str(Path.home() / ".local/state/sentientos-hermes-epistemic")))
workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
if workspace.is_symlink():
    raise SystemExit("private_experiment_workspace_cannot_be_symlink")
os.chmod(workspace, 0o700)
os.environ["SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE"] = str(workspace)

from sentientos.avatar_authoring import renderer_handoff
from sentientos.codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK,
    RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from sentientos.embodiment_self_observation import (
    EmbodimentEvidenceOwner, EmbodimentObservation, semantic_digest)
from sentientos.embodied_consequence import (
    SyntheticIndependentObserver, SyntheticRenderer, evaluate_consequence,
    make_expectation, world_state_records as consequence_world_state_records)
from sentientos.local_model_authority import (
    ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_PURPOSE, digest_payload, stream_sha256)
from sentientos.local_runtime_provisioning import semantic_digest as runtime_digest
from sentientos.resident_developmental_cognition import (
    ResidentDevelopmentalCognitionConfig, ResidentDevelopmentalCognitionOwner)
from sentientos.resident_developmental_writeback import (
    ResidentDevelopmentalWritebackController)
from sentientos.runtime_admission import (
    AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier)
from sentientos.rootless_experimental_local_model import (
    EXPERIMENT_ROOT, RootlessExperimentalError, _no_symlink_path)
from sentientos.rootless_experimental_ollama_epistemic_session import (
    RootlessExperimentalOllamaDevelopmentalSession)
from sentientos.world_state_board import WorldStateBoardBuilder


MODEL_NAME = os.environ.get("SENTIENTOS_HERMES_MODEL", "sentientos-hermes4:14b-q4km")
MANIFEST_PATH = EXPERIMENT_ROOT / "ollama-model-manifests" / (
    "f6a766d405cbb73f9ba64a59b8fb29a3418d0da0b6fad15a0ca70687413ce0ce.json")
RUN_ID = "rootless-cognition-cycle-" + uuid.uuid4().hex[:20]
RUN_ROOT = EXPERIMENT_ROOT / "developmental-cognition-cycles" / RUN_ID


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runtime_observation(model_digest: str) -> tuple[dict[str, Any], str]:
    request = urllib.request.Request("http://127.0.0.1:11434/api/version", method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=5) as response:
        payload = json.loads(response.read(4096).decode("utf-8"))
    observed = {"backend": "ollama-loopback",
        "version": str(payload.get("version", "unknown")),
        "model_manifest_digest": model_digest,
        "runtime_attestation": "local_observation_only"}
    return observed, runtime_digest(observed)


def _gpu_snapshot() -> dict[str, str] | None:
    try:
        result = subprocess.run(["nvidia-smi",
            "--query-gpu=name,memory.total,memory.used",
            "--format=csv,noheader"], capture_output=True, text=True,
            timeout=5, check=True)
        return {"sample": result.stdout.strip()[:512], "source": "nvidia-smi",
            "scope": "host_sample_not_per_invocation"}
    except Exception:
        return None


def _embodied_source() -> tuple[dict[str, Any], dict[str, Any]]:
    commanded_at = (datetime.now(timezone.utc) - timedelta(seconds=8)).isoformat()
    renderer_completed_at = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    observed_at = (datetime.now(timezone.utc) - timedelta(seconds=4)).isoformat()
    body = {"installation_identity": "synthetic-installation",
        "body_identity": "synthetic-avatar-body", "body_generation": 1,
        "artifact_sha256": "sha256:" + "a" * 64,
        "manifest_digest": "sha256:" + "b" * 64,
        "pointer_digest": "sha256:" + "c" * 64}
    handoff = renderer_handoff(body, renderer_interface_id="renderer:synthetic:v1",
        requested_pose="reach", requested_expression="neutral",
        correlation_id=RUN_ID + ":action", commanded_at=commanded_at)
    expectation = make_expectation(
        installation_body_id="synthetic-installation", body_id="synthetic-avatar-body",
        body_generation=1, body_manifest_digest=body["manifest_digest"],
        handoff_id=handoff["handoff_id"], handoff_digest=handoff["handoff_digest"],
        renderer_interface_id="renderer:synthetic:v1", requested={"pose": "reach"},
        predicted_observables={"pose": "reach"}, observable_fields=("pose",),
        comparison_policy={"pose": {"kind": "exact"}},
        expected_observation_source_class="synthetic_independent_fixture",
        correlation_id=RUN_ID + ":action", causal_principal_binding_digest=None,
        created_at=commanded_at,
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat())
    renderer_report = SyntheticRenderer(applied={"pose": "reach"},
        started_at=commanded_at, completed_at=renderer_completed_at).render_test(handoff)
    # A separately named simulated observer reports the environment result;
    # it does not trust the renderer's assertion.
    observation = SyntheticIndependentObserver(
        observer_id="synthetic-separate-environment-observer",
        observed={"pose": "idle"}, observed_at=observed_at).observe(
            expectation=expectation, handoff=handoff, report=renderer_report)
    attribution, comparison = evaluate_consequence(
        expectation=expectation, handoff=handoff, current_body=body,
        renderer_report=renderer_report, observation=observation,
        evaluated_at=observed_at)
    consequence_records = consequence_world_state_records(
        expectation=expectation, handoff=handoff, renderer_report=renderer_report,
        observation=observation, attribution=attribution, comparison=comparison)

    self_report = EmbodimentObservation(
        source_id=RUN_ID + ":synthetic-proprioception",
        source_schema="sentientos.synthetic_proprioception_observation:v1",
        source_digest=semantic_digest({"requested_pose": "reach",
            "encoder_pose": "reach", "joint_state": {"arm": 0.75},
            "source_posture": "synthetic_test"}),
        observed_at=renderer_completed_at,
        provenance_class="deterministic_synthetic_fixture", freshness="current",
        posture="synthetic_test", evidence_class="sensor_observation",
        subject_id="synthetic-avatar-body", subject_kind="robot_body",
        payload={"requested_pose": "reach", "encoder_pose": "reach",
            "joint_state": {"arm": 0.75}, "sampled_at": renderer_completed_at})
    proprioception_records = EmbodimentEvidenceOwner([self_report]).world_state_records()
    # Keep the evaluated consequence and proprioceptive-style self report
    # inside the owner's 6 KB evidence limit. The consequence itself binds the
    # separate observer identity, digest, and observed fields.
    retained_source_ids = {attribution["attribution_id"], self_report.source_id}
    selected_records = [row for row in consequence_records + proprioception_records
        if row.get("source_id") in retained_source_ids]
    snapshot = WorldStateBoardBuilder().build(selected_records)
    evidence_summary = {
        "snapshot_id": snapshot.snapshot_id, "snapshot_digest": snapshot.digest,
        "source_kinds": sorted({row["source_kind"]
            for row in consequence_records + proprioception_records}),
        "proprioception_posture": "synthetic_test_unverified_self_report",
        "consequence_classification": attribution["classification"],
        "effect_proven": attribution["effect_proven"],
        "renderer_report_pose": dict(renderer_report.applied),
        "independent_observation_pose": dict(observation.observed),
        "renderer_and_observer_separately_bound": True,
        "action_execution_posture": "synthetic_fixture_only",
    }
    return snapshot, evidence_summary


def run() -> dict[str, Any]:
    if not MANIFEST_PATH.is_file() or MANIFEST_PATH.is_symlink():
        raise RootlessExperimentalError("pinned_hermes_manifest_missing")
    manifest_digest, manifest_size = stream_sha256(MANIFEST_PATH)
    if manifest_digest != MANIFEST_PATH.stem:
        raise RootlessExperimentalError("pinned_hermes_manifest_digest_mismatch")
    RUN_ROOT.mkdir(parents=True, exist_ok=False, mode=0o700)
    _no_symlink_path(RUN_ROOT)
    runtime, runtime_sha = _runtime_observation(manifest_digest)
    binding = {"schema_version": "sentientos.rootless_experimental_cognition_session:v1",
        "session_id": "rootless-cognition-session-" + uuid.uuid4().hex[:20],
        "run_id": RUN_ID, "preregistration_digest": "0" * 64,
        "model_manifest_digest": manifest_digest,
        "runtime_bundle_digest": runtime_sha,
        "active_model_identity_digest": "0" * 64,
        "purpose": ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_PURPOSE,
        "production_authority": False,
        "eligible_as_production_serving_evidence": False}
    before_gpu = _gpu_snapshot()
    session = RootlessExperimentalOllamaDevelopmentalSession(
        model_manifest_path=MANIFEST_PATH, model_name=MODEL_NAME,
        root=RUN_ROOT, session_binding=binding)
    # Bind the session to the identity actually loaded by the governed worker.
    session.session_binding["active_model_identity_digest"] = digest_payload(
        {"identity": session.active_model_identity})
    try:
        cognition_root = RUN_ROOT / "resident-cognition"
        history_root, state_root = cognition_root / "history", cognition_root / "state"
        ledger = AdmissionLedger(state_root / "runtime_admissions.json")

        def current_sequence() -> int:
            admissions, _ = ledger.load()
            return max((item.issued_sequence for item in admissions), default=0)

        def next_sequence() -> int:
            admissions, revocations = ledger.load()
            return max([item.issued_sequence for item in admissions]
                + [item.sequence for item in revocations], default=0) + 1

        definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK:
            RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}
        writeback = ResidentDevelopmentalWritebackController(
            history_root=history_root,
            admission_verifier=RuntimeAdmissionVerifier(
                definitions=definitions, ledger=ledger),
            current_sequence=current_sequence)
        owner = ResidentDevelopmentalCognitionOwner(
            config=ResidentDevelopmentalCognitionConfig(
                history_root, state_root, ("embodiment",), 16, 4, True),
            writeback=writeback,
            admission_authority=RuntimeAdmissionAuthority(
                definitions=definitions, ledger=ledger),
            invoker=session, current_sequence=next_sequence)

        snapshot, evidence = _embodied_source()
        first = owner.run_tick(snapshot=snapshot, tick_id=RUN_ID + ":consequence")
        if not first.written_record_id:
            raise RootlessExperimentalError("governed_developmental_writeback_not_created")
        durable = owner.writeback.store.get(first.written_record_id)
        second = owner.run_tick(snapshot=snapshot, tick_id=RUN_ID + ":later-cognition")
        if not second.changed_cognition_measurement_id:
            raise RootlessExperimentalError("history_intervention_measurement_missing")
        run_payload = owner.experiments.load_run(second.changed_cognition_measurement_id)
        conditions = run_payload.get("conditions", [])
        summary = run_payload.get("summary", {})
        records = [asdict(durable)]
        source_ids = {fact.get("source", {}).get("source_id")
            for fact in records[0]["candidate"].get("selected_facts", [])
            if isinstance(fact, dict)}
        result = {
            "schema_version": "sentientos.rootless_ollama_embodied_cognition_cycle:v1",
            "run_id": RUN_ID, "status": "completed",
            "execution_posture": "rootless_experimental_nonproduction",
            "model_id": MODEL_NAME, "model_manifest_digest": manifest_digest,
            "requested_backend_seed": 42,
            "model_artifact_size_bytes": manifest_size,
            "runtime_observation": runtime, "runtime_observation_digest": runtime_sha,
            "active_model_identity": session.active_model_identity,
            "authority_map_digest": session.authority_map.map_digest,
            "authority_scope": {
                "allowed_invocation_purposes": [
                    "resident_developmental_interpretation",
                    "resident_developmental_retrieval_cognition",
                    "resident_developmental_history_intervention_experiment"],
                "ordinary_chat_allowed": False, "production_authority": False,
                "tool_or_action_authority": False},
            "body_and_observer_posture": "synthetic_rehearsal_not_live_hardware",
            "source_evidence": evidence,
            "initial_tick": {"status": first.status,
                "cognition_observation_ids": list(first.cognition_observation_ids),
                "written_record_id": first.written_record_id,
                "writeback_receipt_id": first.writeback_receipt_id,
                "record_current_truth": durable.current_truth,
                "record_authority": durable.authority,
                "record_epistemic_posture": durable.epistemic_posture,
                "selected_source_ids": sorted(item for item in source_ids if item)},
            "later_tick": {"status": second.status,
                "prior_record_ids": list(second.prior_record_ids),
                "changed_cognition_measurement_id": second.changed_cognition_measurement_id,
                "cognition_observation_ids": list(second.cognition_observation_ids)},
            "history_intervention": {"validity": run_payload.get("validity"),
                "conditions": [{"condition_id": item.get("condition_id"),
                    "output_digest": item.get("output_digest"),
                    "prompt_digest": item.get("epistemic_prompt_digest"),
                    "generation_config": item.get("generation_config"),
                    "active_model_identity": item.get("active_model_identity"),
                    "retrieved_record_ids": item.get("retrieved_record_ids"),
                    "developmental_projection_present": item.get(
                        "developmental_projection_present")}
                    for item in conditions],
                "same_history_replay": {
                    "prompt_digest_matches": (
                        len(conditions) == 3
                        and conditions[0].get("epistemic_prompt_digest")
                            == conditions[2].get("epistemic_prompt_digest")),
                    "generation_config_matches": (
                        len(conditions) == 3
                        and conditions[0].get("generation_config")
                            == conditions[2].get("generation_config")),
                    "active_model_identity_matches": (
                        len(conditions) == 3
                        and conditions[0].get("active_model_identity")
                            == conditions[2].get("active_model_identity")),
                    "output_digest_matches": (
                        len(conditions) == 3
                        and conditions[0].get("output_digest")
                            == conditions[2].get("output_digest")),
                },
                "summary": summary,
                "causal_claim_made": False,
                "interpretation": "controlled history presence/withholding association only"},
            "gpu_before": before_gpu, "gpu_after": _gpu_snapshot(),
            "governed_unload": "pending",
        }
        session.close()
        result["governed_unload"] = "governed_release_completed"
        out = RUN_ROOT / "cycle-result.json"
        result["evidence_path"] = str(out)
        out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.chmod(out, 0o600)
        return result
    finally:
        session.close()


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, sort_keys=True, indent=2))
