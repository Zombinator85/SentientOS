from __future__ import annotations

import json
from pathlib import Path

import pytest

from work.rootless_history_boundary_campaign import (
    _admission_boundary_preserves,
    _cognition_recovery_state_boundary,
    _cognition_recovery_state_preserves,
    _load_plan,
    _plan_model_identity_digests,
    create_plan,
)


def _history_root(tmp_path: Path) -> Path:
    root = tmp_path / "history"
    (root / "records").mkdir(parents=True)
    (root / "receipts").mkdir()
    return root


def _plan(tmp_path: Path) -> dict[str, object]:
    return create_plan(
        history_root=_history_root(tmp_path),
        campaign_id="rootless-history-campaign-0123456789abcdefabcd",
        task_family_id="rootless_integer_affine_transfer_low_range_v6",
        model_identity_digests=["a" * 64, "b" * 64],
        ordered_cycle_ids=[
            "rootless-cognition-cycle-0123456789abcdefabcd",
            "rootless-cognition-cycle-1123456789abcdefabcd",
        ],
        task_generation_seeds=[1001, 1002],
        backend_seeds=[43, 44],
    )


def test_campaign_plan_pins_model_identity_per_backend_seed(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    assert plan["schema_version"] == (
        "sentientos.rootless_history_boundary_campaign_plan:v5")
    assert plan["ordered_model_identity_digests"] == ["a" * 64, "b" * 64]
    assert _plan_model_identity_digests(plan) == ["a" * 64, "b" * 64]

    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    assert _load_plan(path) == plan


def _admission_boundary(*, admissions: list[tuple[str, str, int]],
        revocations: list[tuple[str, str, int]], sha: str) -> dict[str, object]:
    return {
        "schema_version": "sentientos.rootless_history_campaign_admission_boundary:v1",
        "sha256": sha * 64,
        "size_bytes": 128,
        "admission_count": len(admissions),
        "revocation_count": len(revocations),
        "admission_bindings": [{
            "admission_id": identifier,
            "binding_digest": "sha256:" + digest * 64,
            "issued_sequence": sequence,
        } for identifier, digest, sequence in admissions],
        "revocation_bindings": [{
            "revocation_id": identifier,
            "binding_digest": "sha256:" + digest * 64,
            "sequence": sequence,
        } for identifier, digest, sequence in revocations],
        "atomic_snapshot": False,
    }


def test_admission_chain_allows_new_entries_and_revocations() -> None:
    previous = _admission_boundary(
        admissions=[("admission-a", "a", 1)],
        revocations=[], sha="1")
    current = _admission_boundary(
        admissions=[("admission-a", "a", 1), ("admission-b", "b", 2)],
        revocations=[("revocation-a", "c", 3)], sha="2")

    assert _admission_boundary_preserves(previous, current)


@pytest.mark.parametrize("changed", [
    _admission_boundary(admissions=[], revocations=[], sha="2"),
    _admission_boundary(
        admissions=[("admission-a", "f", 1)], revocations=[], sha="2"),
    _admission_boundary(
        admissions=[("admission-a", "a", 1)],
        revocations=[], sha="2"),
])
def test_admission_chain_detects_removal_or_mutation(
        changed: dict[str, object]) -> None:
    previous = _admission_boundary(
        admissions=[("admission-a", "a", 1)],
        revocations=[("revocation-a", "c", 3)], sha="1")

    assert not _admission_boundary_preserves(previous, changed)


def _write_recovery_state(state_root: Path, *, tick_id: str,
        observation_body: str,
        additional_tick_ids: tuple[str, ...] = (),
        additional_observation: bool = False,
        receipt_id: str | None = None) -> dict[str, object]:
    from sentientos.local_model_authority import digest_payload
    state_root.mkdir(parents=True, exist_ok=True)
    observations = state_root / "cognition_observations"
    observations.mkdir(exist_ok=True)
    row = {"tick_id": tick_id, "receipt_id": None, "record_id": None}
    rows = [row, *({"tick_id": item, "receipt_id": None, "record_id": None}
        for item in additional_tick_ids)]
    body = {"schema": "sentientos.resident_developmental_cognition_state:v2",
        "processed_selection_ids": [], "completed_ticks": rows,
        "incomplete_ticks": []}
    value = {**body, "state_digest": "sha256:" + digest_payload(body)}
    (state_root / "composition_state.json").write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        newline="\n")
    observation = {"schema_version": "test_observation:v1",
        "inference_receipt_id": receipt_id, "body": observation_body}
    (observations / "devcog-0123456789abcdef01234567.json").write_text(
        json.dumps(observation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    if receipt_id is not None:
        receipt_path = (state_root.parent.parent / "inference-custody"
            / "receipts" / f"{receipt_id}.json")
        receipt_path.parent.mkdir(parents=True)
        receipt_path.write_text("{\"receipt_id\":\"" + receipt_id + "\"}\n",
            encoding="utf-8", newline="\n")
    if additional_observation:
        observation = {"schema_version": "test_observation:v1",
            "inference_receipt_id": None, "body": "observation-appended\n"}
        (observations / "devcog-1123456789abcdef01234567.json").write_text(
            json.dumps(observation, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
    return _cognition_recovery_state_boundary(state_root)  # type: ignore[return-value]


def test_recovery_state_boundary_tracks_tick_order_and_observations(
        tmp_path: Path) -> None:
    state = _write_recovery_state(tmp_path / "state",
        tick_id="tick-source-1", observation_body="observation-v1\n")

    assert state["schema_version"] == (
        "sentientos.rootless_cognition_recovery_state:v1")
    assert _cognition_recovery_state_preserves(state, state)


def test_recovery_state_preservation_allows_appended_ticks_and_observations(
        tmp_path: Path) -> None:
    previous = _write_recovery_state(tmp_path / "previous",
        tick_id="tick-source-1", observation_body="observation-v1\n")
    current = _write_recovery_state(tmp_path / "current",
        tick_id="tick-source-1", observation_body="observation-v1\n",
        additional_tick_ids=("tick-next",), additional_observation=True)

    assert _cognition_recovery_state_preserves(previous, current)


def test_v5_plan_pins_recovery_state_boundary(tmp_path: Path) -> None:
    history_root = _history_root(tmp_path)
    recovery_state = _write_recovery_state(tmp_path / "state",
        tick_id="tick-source-1", observation_body="observation-v1\n")
    plan = create_plan(
        history_root=history_root,
        campaign_id="rootless-history-campaign-0123456789abcdefabcd",
        task_family_id="rootless_integer_affine_transfer_low_range_v6",
        model_identity_digests=["a" * 64, "b" * 64],
        ordered_cycle_ids=[
            "rootless-cognition-cycle-0123456789abcdefabcd",
            "rootless-cognition-cycle-1123456789abcdefabcd",
        ],
        task_generation_seeds=[1001, 1002],
        backend_seeds=[43, 44],
    )
    path = tmp_path / "recovery-plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    assert plan["initial_cognition_recovery_state"] == recovery_state
    assert _load_plan(path) == plan


def test_recovery_boundary_includes_receipts_referenced_by_observations(
        tmp_path: Path) -> None:
    receipt_id = "lmrec-0123456789abcdef01234567"
    state_root = tmp_path / "cycle" / "resident-cognition" / "state"
    boundary = _write_recovery_state(state_root,
        tick_id="tick-source-1", observation_body="uses receipt",
        receipt_id=receipt_id)
    relative = f"inference-custody/receipts/{receipt_id}.json"

    assert relative in {row["path"] for row in boundary["files"]}
    (tmp_path / "cycle" / relative).unlink()
    with pytest.raises(ValueError, match="observation_receipt_missing"):
        _cognition_recovery_state_boundary(state_root)


def test_recovery_state_preservation_rejects_tick_or_observation_rewrite(
        tmp_path: Path) -> None:
    previous = _write_recovery_state(tmp_path / "previous",
        tick_id="tick-source-1", observation_body="observation-v1\n")
    changed_tick = _write_recovery_state(tmp_path / "changed-tick",
        tick_id="tick-rewritten", observation_body="observation-v1\n")
    changed_observation = _write_recovery_state(tmp_path / "changed-observation",
        tick_id="tick-source-1", observation_body="observation-v2\n")

    assert not _cognition_recovery_state_preserves(previous, changed_tick)
    assert not _cognition_recovery_state_preserves(previous, changed_observation)


def test_admission_boundary_accepts_namespaced_binding_digests(
        tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    plan["initial_runtime_admission_ledger"] = {
        "schema_version": "sentientos.rootless_history_campaign_admission_boundary:v1",
        "sha256": "c" * 64,
        "size_bytes": 128,
        "admission_count": 1,
        "revocation_count": 0,
        "admission_bindings": [{
            "admission_id": "resident-admission-test-1",
            "binding_digest": "sha256:" + "d" * 64,
            "issued_sequence": 1,
        }],
        "revocation_bindings": [],
        "atomic_snapshot": False,
    }
    from sentientos.local_model_authority import digest_payload
    unsigned = {key: value for key, value in plan.items() if key != "plan_digest"}
    plan["plan_digest"] = digest_payload(unsigned)
    path = tmp_path / "admission-plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")

    assert _load_plan(path) == plan


def test_campaign_plan_rejects_missing_per_cycle_identity(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="model_identity_digest_invalid"):
        create_plan(
            history_root=_history_root(tmp_path),
            campaign_id="rootless-history-campaign-0123456789abcdefabcd",
            task_family_id="rootless_integer_affine_transfer_low_range_v6",
            model_identity_digests=["a" * 64],
            ordered_cycle_ids=[
                "rootless-cognition-cycle-0123456789abcdefabcd",
                "rootless-cognition-cycle-1123456789abcdefabcd",
            ],
            task_generation_seeds=[1001, 1002],
            backend_seeds=[43, 44],
        )


def test_legacy_v2_plan_keeps_single_identity_binding(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    legacy = {key: value for key, value in plan.items()
        if key not in {"ordered_model_identity_digests",
            "initial_runtime_admission_ledger", "initial_cognition_recovery_state",
            "plan_digest"}}
    legacy["schema_version"] = "sentientos.rootless_history_boundary_campaign_plan:v2"
    legacy["model_identity_digest"] = "a" * 64
    from sentientos.local_model_authority import digest_payload
    legacy["plan_digest"] = digest_payload(legacy)
    path = tmp_path / "legacy-plan.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")

    assert _plan_model_identity_digests(_load_plan(path)) == ["a" * 64, "a" * 64]


def test_v3_plan_remains_readable_without_admission_boundary(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    legacy = {key: value for key, value in plan.items()
        if key not in {"initial_runtime_admission_ledger",
            "initial_cognition_recovery_state", "plan_digest"}}
    legacy["schema_version"] = "sentientos.rootless_history_boundary_campaign_plan:v3"
    from sentientos.local_model_authority import digest_payload
    legacy["plan_digest"] = digest_payload(legacy)
    path = tmp_path / "v3-plan.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")

    assert _plan_model_identity_digests(_load_plan(path)) == ["a" * 64, "b" * 64]
