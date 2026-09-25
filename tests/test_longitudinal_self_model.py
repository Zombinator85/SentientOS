from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sentientos.longitudinal_self_model import LongitudinalSelfModelError, LongitudinalSelfModelOwner
from sentientos.world_state_board import WorldStateBoardBuilder, digest, to_dict

pytestmark = pytest.mark.no_legacy_skip


NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)


def record(*, source: str = "runtime:a", subject: str = "sentientos", disposition: str = "serving",
           observed: str = "2026-09-25T11:59:00Z", model: str = "model-a", generation: str = "software-a",
           extra: dict[str, object] | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "software_generation": generation,
        "cognitive_model_id": model,
        "developmental_history_boundary": "history-10",
    }
    payload.update(extra or {})
    return {
        "source_kind": "local_model_authority", "source_id": source,
        "schema_version": "test.v1", "subject_id": subject,
        "subject_kind": "persistent_causal_system", "stage": "observation",
        "disposition": disposition, "evidence_strength": "authenticated",
        "observed_at": observed, "payload": payload,
    }


def snapshot(*records: dict[str, object]):
    return WorldStateBoardBuilder(clock=lambda: NOW).build(records)


def test_exact_source_binding_and_identical_replay_are_idempotent(tmp_path: Path) -> None:
    source = snapshot(record())
    owner = LongitudinalSelfModelOwner(tmp_path)
    first = owner.reconcile(source, tick_id="tick-1")
    second = owner.reconcile(source, tick_id="tick-replay")
    assert second == first
    assert len(owner.history()) == 1
    assert all(claim.world_state_snapshot_digest == source.digest for claim in first.claims)
    assert {claim.source_evidence_ids for claim in first.claims} == {("runtime:a",)}
    assert not any(first.authority.values())


def test_stale_evidence_is_not_current_and_disappearance_is_withdrawal(tmp_path: Path) -> None:
    owner = LongitudinalSelfModelOwner(tmp_path)
    old = owner.reconcile(snapshot(record(observed="2026-09-10T00:00:00Z")), tick_id="tick-1")
    assert all(claim.status == "historical" and claim.freshness == "stale" for claim in old.claims)
    current = owner.reconcile(snapshot(record(source="runtime:b", subject="other")), tick_id="tick-2")
    withdrawn = [claim for claim in current.claims if claim.subject_id == "sentientos"]
    assert withdrawn and all(claim.status == "withdrawn" and claim.freshness == "stale" for claim in withdrawn)


def test_contradictory_evidence_is_preserved_without_latest_wins(tmp_path: Path) -> None:
    result = LongitudinalSelfModelOwner(tmp_path).reconcile(
        snapshot(record(source="runtime:a", model="model-a"), record(source="runtime:b", model="model-b")),
        tick_id="tick-1",
    )
    model_claims = [claim for claim in result.claims if claim.predicate == "cognitive_model_identity"]
    assert {claim.value for claim in model_claims} == {"model-a", "model-b"}
    assert all(claim.status == "contradicted" and claim.contradiction_state == "contradicted" for claim in model_claims)


def test_generation_and_model_transition_preserves_historical_claims(tmp_path: Path) -> None:
    owner = LongitudinalSelfModelOwner(tmp_path)
    first = owner.reconcile(snapshot(record(model="model-a", generation="software-a")), tick_id="tick-a")
    second = owner.reconcile(snapshot(record(source="runtime:b", model="model-b", generation="software-b")), tick_id="tick-b")
    assert owner.reconstruct(1) == first
    assert owner.reconstruct(2) == second
    old = [claim for claim in second.claims if claim.value in {"model-a", "software-a"}]
    new = [claim for claim in second.claims if claim.value in {"model-b", "software-b"}]
    assert old and all(claim.status == "historical" and claim.superseded_by for claim in old)
    assert new and all(claim.status == "current" and claim.supersedes for claim in new)


def test_source_digest_mismatch_fails_closed_without_write(tmp_path: Path) -> None:
    bad = snapshot({**record(), "digest": "not-the-content-digest"})
    owner = LongitudinalSelfModelOwner(tmp_path)
    with pytest.raises(LongitudinalSelfModelError, match="provenance"):
        owner.reconcile(bad, tick_id="tick-1")
    assert owner.history() == ()


def test_malformed_snapshot_and_missing_provenance_fail_closed(tmp_path: Path) -> None:
    good = snapshot(record())
    owner = LongitudinalSelfModelOwner(tmp_path)
    with pytest.raises(LongitudinalSelfModelError, match="invalid_world_state_snapshot"):
        owner.reconcile(replace(good, digest="tampered"), tick_id="tick-1")
    source = replace(good.sources[0], source_id="")
    fact = replace(good.facts[0], source=source)
    base = {"schema_version": "world_state_board.v1", "manifest_digest": good.manifest.digest,
            "sources": [to_dict(source)], "facts": [to_dict(fact)],
            "conflicts": [to_dict(x) for x in good.conflicts], "summary": to_dict(good.summary),
            "authority": good.authority}
    missing = replace(good, sources=(source,), facts=(fact,), digest=digest(base))
    with pytest.raises(LongitudinalSelfModelError, match="provenance"):
        owner.reconcile(missing, tick_id="tick-1")
    assert owner.history() == ()


def test_authority_and_model_authored_claim_smuggling_is_rejected(tmp_path: Path) -> None:
    owner = LongitudinalSelfModelOwner(tmp_path)
    for payload in ({"authority": True}, {"permission": True}, {"model_authored_claim": "I improved"}):
        with pytest.raises(LongitudinalSelfModelError, match="smuggling"):
            owner.reconcile(snapshot(record(extra=payload)), tick_id="tick-1")
    assert owner.history() == ()


def test_atomic_interruption_leaves_no_partial_reconciliation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    owner = LongitudinalSelfModelOwner(tmp_path)
    def interrupted(*args: object, **kwargs: object) -> None:
        raise OSError("interrupted")
    monkeypatch.setattr("sentientos.longitudinal_self_model.atomic_write_json", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        owner.reconcile(snapshot(record()), tick_id="tick-1")
    assert owner.history() == ()


def test_restart_reconstruction_detects_tamper_and_retains_superseded_history(tmp_path: Path) -> None:
    owner = LongitudinalSelfModelOwner(tmp_path)
    owner.reconcile(snapshot(record()), tick_id="tick-a")
    owner.reconcile(snapshot(record(source="runtime:b", model="model-b")), tick_id="tick-b")
    restarted = LongitudinalSelfModelOwner(tmp_path)
    assert restarted.reconstruct(1) is not None
    assert any(claim.value == "model-a" for claim in restarted.reconstruct(2).claims)  # type: ignore[union-attr]
    path = sorted((tmp_path / "reconciliations").glob("*.json"))[0]
    raw = json.loads(path.read_text()); raw["tick_id"] = "tampered"; path.write_text(json.dumps(raw))
    with pytest.raises(LongitudinalSelfModelError, match="digest_mismatch"):
        restarted.history()
