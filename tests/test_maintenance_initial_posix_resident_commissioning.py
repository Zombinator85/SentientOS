from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sentientos import maintenance_activation_profiles as profiles
from sentientos import maintenance_initial_posix_resident_commissioning as commissioning
from sentientos import maintenance_resident_runtime_adoption as resident
from sentientos.control_plane_kernel import (AdmissionOutcome, AuthorityClass, ControlActionDecision,
    ControlPlaneKernel, LifecyclePhase)
from tests.test_maintenance_successor_generation_adoption import canonical_lineage

pytestmark = pytest.mark.no_legacy_skip
NOW = datetime(2030, 1, 2, tzinfo=timezone.utc)


class Kernel:
    def __init__(self, outcome: AdmissionOutcome = AdmissionOutcome.ALLOW) -> None:
        self.outcome = outcome; self.requests = []
    def admit(self, request):
        self.requests.append(request)
        return ControlActionDecision(self.outcome, ("test",), LifecyclePhase.MAINTENANCE,
            LifecyclePhase.MAINTENANCE, request.authority_class, request.action_kind, request.actor,
            request.target_subsystem, {}, request.metadata["correlation_id"])


def fixture(tmp_path: Path) -> dict[str, object]:
    successor_cfg, generation, root = canonical_lineage(tmp_path, derive_successor=False)
    repo = Path(str(successor_cfg["repository_root"])); profile_path = Path(str(generation["manifest_path"]))
    with (repo / ".git/info/exclude").open("a") as handle: handle.write("sentientosd.py\n")
    (repo / "sentientosd.py").write_text("# canonical daemon entrypoint\n")
    profile = profiles.validate_manifest(json.loads(profile_path.read_text()))
    bundle = profiles.verify_profile_bundle(profile_path, "2030-01-02T00:00:00Z")
    custody = tmp_path / "commissioned"
    value: dict[str, object] = {
        "schema_version": commissioning.MANIFEST_SCHEMA, "repository_identity": "repo",
        "repository_root": str(repo), "expected_commit": generation["base_sha"],
        "expected_tree": commissioning._git(repo, "rev-parse", "HEAD^{tree}"), "canonical_ref": "refs/heads/main",
        "python_executable": str(Path(sys.executable).resolve()), "daemon_entrypoint": str(repo / "sentientosd.py"),
        "custody_root": str(custody), "profile_manifest_path": str(profile_path),
        "profile_manifest_digest": profile["manifest_digest"], "profile_bundle_digest": bundle["bundle_digest"],
        "initial_wake_adoption_path": successor_cfg["initial_wake_adoption_path"],
        "initial_wake_adoption_digest": successor_cfg["initial_wake_adoption_digest"], "operator_reference": "operator:test",
        "approval_evidence_path": str(tmp_path / "external-approval.json"), "lineage_id": "line", "created_at": "2030-01-02T00:00:00Z",
        "stop_marker": str(custody / "resident-state/STOP"), "environment_allowlist": ["PATH"], "required_environment": {},
        "maximum_handoffs": 2, "maximum_successful_transitions": 2, "maximum_wall_clock_seconds": 120,
        "quiescence_timeout_seconds": 2, "readiness_timeout_seconds": 20, "launch_timeout_seconds": 30,
        "manifest_digest": "",
    }
    value["manifest_digest"] = commissioning.digest(value, "manifest_digest")
    return value


def approval(intent: dict[str, object], *, synthetic: bool = True, **changes: object) -> dict[str, object]:
    value: dict[str, object] = {"schema_version": commissioning.APPROVAL_SCHEMA, "approval_id": "approval-1",
        "approval_digest": "", "source": "external_operator", "synthetic": synthetic,
        "bindings": commissioning.approval_bindings(intent), "operator_identity": "test-operator",
        "operator_provenance": ("explicitly_synthetic_test_fixture" if synthetic else "operator-console-session:abc123"),
        "not_before": "2030-01-01T00:00:00Z",
        "expires_at": "2030-02-01T00:00:00Z"}
    value.update(changes); value["approval_digest"] = commissioning.digest(value, "approval_digest"); return value


def external_approval(manifest: dict[str, object], value: dict[str, object]) -> Path:
    path = Path(str(manifest["approval_evidence_path"])); path.write_text(json.dumps(value, sort_keys=True))
    return path


def launch(cfg):
    value = {"schema_version": resident.PROVENANCE_SCHEMA, "config_digest": cfg["config_digest"],
        "represented_generation_ordinal": 0, "represented_generation_digest": "synthetic-generation-zero",
        "observed_commit_sha": "synthetic", "observed_tree_sha": "synthetic", "python_executable": cfg["python_executable"],
        "daemon_entrypoint": cfg["daemon_entrypoint"], "cwd": cfg["working_directory"],
        "argv": [cfg["python_executable"], "-m", "sentientosd"], "environment_identity_digest": "sha256:test",
        "process_instance_id": "synthetic-process", "startup_timestamp": "2030-01-02T00:00:00Z",
        "synthetic_test_evidence": True, "provenance_digest": ""}
    value["provenance_digest"] = resident.digest(value, "provenance_digest"); return value


def test_doctor_is_read_only_and_rejects_non_posix(tmp_path: Path) -> None:
    manifest = fixture(tmp_path); before = set(tmp_path.rglob("*"))
    assert commissioning.doctor(manifest)["status"] == "initial_resident_commissioning_ready"
    assert set(tmp_path.rglob("*")) == before
    assert "posix_locking_required" in commissioning.doctor(manifest, platform_name="nt")["reason_codes"]


@pytest.mark.parametrize("field,value,reason", [
    ("expected_commit", "0" * 40, "repository_commit_mismatch"),
    ("expected_tree", "0" * 40, "repository_tree_mismatch"),
])
def test_repository_identity_mismatch_blocks(tmp_path: Path, field: str, value: str, reason: str) -> None:
    manifest = fixture(tmp_path); manifest[field] = value; manifest["manifest_digest"] = commissioning.digest(manifest, "manifest_digest")
    assert reason in commissioning.doctor(manifest)["reason_codes"]


def test_dirty_ambiguous_and_unsafe_custody_block(tmp_path: Path) -> None:
    manifest = fixture(tmp_path); repo = Path(str(manifest["repository_root"])); (repo / "dirty").write_text("x")
    assert "repository_dirty" in commissioning.doctor(manifest)["reason_codes"]; (repo / "dirty").unlink()
    (repo / ".git/MERGE_HEAD").write_text("x"); assert "ambiguous_git_operation" in commissioning.doctor(manifest)["reason_codes"]
    (repo / ".git/MERGE_HEAD").unlink(); manifest["custody_root"] = str(repo / "custody")
    manifest["manifest_digest"] = commissioning.digest(manifest, "manifest_digest")
    assert "custody_inside_repository" in commissioning.doctor(manifest)["reason_codes"]


def test_invalid_profile_and_deterministic_intent(tmp_path: Path) -> None:
    manifest = fixture(tmp_path); first = commissioning.prepare_intent(manifest); assert first == commissioning.prepare_intent(manifest)
    manifest["profile_manifest_digest"] = "sha256:wrong"; manifest["manifest_digest"] = commissioning.digest(manifest, "manifest_digest")
    assert "initial_profile_binding_mismatch" in commissioning.doctor(manifest)["reason_codes"]


def test_exact_external_approval_and_production_synthetic_rejection(tmp_path: Path) -> None:
    manifest = fixture(tmp_path); intent = commissioning.prepare_intent(manifest); evidence = approval(intent)
    with pytest.raises(commissioning.CommissioningError, match="synthetic_runtime_approval_rejected"):
        commissioning.verify_approval(evidence, intent, now=NOW)
    bad = approval(intent, synthetic=False); bad["bindings"] = {**bad["bindings"], "principal": "other"}; bad["approval_digest"] = commissioning.digest(bad, "approval_digest")
    with pytest.raises(commissioning.CommissioningError, match="binding_mismatch"):
        commissioning.verify_approval(bad, intent, now=NOW)


def test_missing_expired_and_denied_approval_are_pre_effect(tmp_path: Path) -> None:
    manifest = fixture(tmp_path); intent = commissioning.prepare_intent(manifest); root = Path(str(manifest["custody_root"]))
    expired = approval(intent, synthetic=False, expires_at="2029-01-01T00:00:00Z")
    path = external_approval(manifest, expired)
    with pytest.raises(commissioning.CommissioningError, match="expired"):
        commissioning.commission(manifest, expired, kernel=Kernel(), correlation_id="c", clock=lambda: NOW,
                                 approval_evidence_path=path)
    assert not root.exists()
    denied = Kernel(AdmissionOutcome.DENY)
    valid = approval(intent, synthetic=False); external_approval(manifest, valid)
    with pytest.raises(commissioning.CommissioningError, match="admission_denied"):
        commissioning.commission(manifest, valid, kernel=denied, correlation_id="c", clock=lambda: NOW,
                                 approval_evidence_path=path)
    assert not root.exists() and denied.requests[0].authority_class is AuthorityClass.INITIAL_RESIDENT_COMMISSIONING


def test_generation_configs_receipt_idempotence_and_boundaries(tmp_path: Path) -> None:
    manifest = fixture(tmp_path); intent = commissioning.prepare_intent(manifest); kernel = Kernel(); calls = []
    def runner(cfg): calls.append(1); return launch(cfg)
    first = commissioning.commission(manifest, approval(intent), kernel=kernel, correlation_id="c", clock=lambda: NOW,
        launch_runner=runner, allow_synthetic_approval_for_tests=True)
    assert first["status"] == "initial_resident_commissioned" and calls == [1]
    root = Path(str(manifest["custody_root"])); receipt = json.loads((root / "commissioning-receipt.json").read_text())
    assert receipt["successor_generation_created"] is receipt["successor_resident_replacement_performed"] is False
    assert receipt["git_mutation_or_publication_performed"] is receipt["network_or_provider_operation_performed"] is receipt["authority_widened"] is False
    assert commissioning.verify(manifest)["status"] == "initial_resident_commissioning_verified"
    retry = commissioning.commission(manifest, approval(intent), kernel=Kernel(), correlation_id="retry", clock=lambda: NOW,
        launch_runner=runner, allow_synthetic_approval_for_tests=True)
    assert retry["status"] == "initial_resident_commissioning_reconstructed" and calls == [1]


def test_conflict_and_tampering_fail_closed(tmp_path: Path) -> None:
    manifest = fixture(tmp_path); intent = commissioning.prepare_intent(manifest)
    commissioning.commission(manifest, approval(intent), kernel=Kernel(), correlation_id="c", clock=lambda: NOW,
        launch_runner=launch, allow_synthetic_approval_for_tests=True)
    root = Path(str(manifest["custody_root"])); (root / "launch-provenance.json").write_text("{}")
    assert commissioning.verify(manifest)["status"] == "initial_resident_commissioning_not_verified"
    changed = dict(manifest); changed["operator_reference"] = "other"; changed["manifest_digest"] = commissioning.digest(changed, "manifest_digest")
    with pytest.raises(commissioning.CommissioningError, match="intent_conflict"):
        commissioning.commission(changed, approval(commissioning.prepare_intent(changed)), kernel=Kernel(), correlation_id="x", clock=lambda: NOW,
            launch_runner=launch, allow_synthetic_approval_for_tests=True)


def test_launch_contract_and_authority_are_closed(tmp_path: Path) -> None:
    intent = commissioning.prepare_intent(fixture(tmp_path))
    assert intent["launch_contract"]["argv"][1:] == ["-m", "sentientosd"]
    assert intent["launch_contract"]["shell"] is False and intent["launch_contract"]["maximum_launches"] == 1
    assert len(commissioning.EFFECTS) == 13 and "bounded_exact_sentientosd_self_exec" not in commissioning.EFFECTS
    source = Path(commissioning.__file__).read_text()
    assert "derive_next(" not in source and "os.exec" not in source and "requests" not in source


@pytest.mark.parametrize("field", ["approval_id", "operator_identity", "operator_provenance"])
def test_blank_operator_evidence_is_rejected(tmp_path: Path, field: str) -> None:
    intent = commissioning.prepare_intent(fixture(tmp_path)); evidence = approval(intent, synthetic=False, **{field: " "})
    with pytest.raises(commissioning.CommissioningError, match="invalid"):
        commissioning.verify_approval(evidence, intent, now=NOW)


def test_manifest_bound_approval_path_and_bytes(tmp_path: Path) -> None:
    manifest = fixture(tmp_path); intent = commissioning.prepare_intent(manifest)
    evidence = approval(intent, synthetic=False); expected = external_approval(manifest, evidence)
    wrong = tmp_path / "wrong.json"; wrong.write_text(json.dumps(evidence))
    with pytest.raises(commissioning.CommissioningError, match="path_mismatch"):
        commissioning.commission(manifest, evidence, kernel=Kernel(), correlation_id="wrong", clock=lambda: NOW,
                                 approval_evidence_path=wrong)
    expected.write_text("{}")
    with pytest.raises(commissioning.CommissioningError, match="bytes_mismatch"):
        commissioning.commission(manifest, evidence, kernel=Kernel(), correlation_id="altered", clock=lambda: NOW,
                                 approval_evidence_path=expected)


def test_real_control_plane_runtime_admission_and_regressions(tmp_path: Path) -> None:
    manifest = fixture(tmp_path); intent = commissioning.prepare_intent(manifest)
    evidence = approval(intent, synthetic=False); path = external_approval(manifest, evidence)
    kernel = ControlPlaneKernel(decisions_path=tmp_path / "decisions.jsonl")
    calls: list[int] = []
    result = commissioning.commission(manifest, evidence, kernel=kernel, correlation_id="real-runtime",
        clock=lambda: NOW, launch_runner=lambda cfg: calls.append(1) or launch(cfg),
        allow_synthetic_approval_for_tests=True, approval_evidence_path=path)
    assert result["status"] == "initial_resident_commissioned" and calls == [1]
    assert kernel.phase is LifecyclePhase.RUNTIME
    request = kernel.admit(kernel_request := commissioning.ControlActionRequest(commissioning.ACTION,
        AuthorityClass.INITIAL_RESIDENT_COMMISSIONING, commissioning.PRINCIPAL, commissioning.CAPABILITY,
        LifecyclePhase.RUNTIME, {"correlation_id": "duplicate"}))
    assert request.outcome is AdmissionOutcome.ALLOW
    assert kernel.admit(kernel_request).outcome is AdmissionOutcome.DEFER
    wrong_phase = commissioning.ControlActionRequest(commissioning.ACTION, AuthorityClass.INITIAL_RESIDENT_COMMISSIONING,
        commissioning.PRINCIPAL, commissioning.CAPABILITY, LifecyclePhase.MAINTENANCE, {"correlation_id": "phase"})
    assert kernel.admit(wrong_phase).outcome is AdmissionOutcome.DEFER
    wrong_class = commissioning.ControlActionRequest(commissioning.ACTION, AuthorityClass.REPAIR,
        commissioning.PRINCIPAL, commissioning.CAPABILITY, LifecyclePhase.RUNTIME, {"correlation_id": "class"})
    assert kernel.admit(wrong_class).authority_class is AuthorityClass.REPAIR
