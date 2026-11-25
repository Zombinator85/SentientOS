"""Audit distinct recorded experience anchors in a frozen federated corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.developmental_history_intervention_experiment import (  # noqa: E402
    DevelopmentalExperimentStore,
)
from sentientos.federated_developmental_history import (  # noqa: E402
    FederatedDevelopmentalHistoryReadView,
)
from sentientos.local_model_authority import digest_payload  # noqa: E402

MINIMUM_SOURCE_EXPERIENCES = 60


def _anchor(record: Any) -> dict[str, str] | None:
    facts = (record.candidate.get("selected_facts", ())
        if isinstance(record.candidate, Mapping) else ())
    experiments = []
    chains = []
    expectations = []
    for fact in facts:
        if not isinstance(fact, Mapping):
            continue
        subject = fact.get("subject")
        payload = fact.get("payload")
        if not isinstance(subject, Mapping):
            continue
        kind = subject.get("subject_kind")
        subject_id = subject.get("subject_id")
        if kind == "developmental_history_intervention_experiment":
            run_id = payload.get("run_id") if isinstance(payload, Mapping) else None
            if isinstance(subject_id, str) and subject_id and run_id == subject_id:
                experiments.append(subject_id)
        elif kind == "embodied_consequence_chain":
            if isinstance(subject_id, str) and subject_id:
                chains.append(subject_id)
        elif kind == "embodied_action_expectation":
            if isinstance(subject_id, str) and subject_id:
                expectations.append(subject_id)
    if len(experiments) == 1 and not chains and not expectations:
        return {"anchor_kind": "developmental_experiment_run",
            "anchor_id": experiments[0]}
    chain_facts = [fact for fact in facts if isinstance(fact, Mapping)
        and isinstance(fact.get("subject"), Mapping)
        and fact["subject"].get("subject_kind") == "embodied_consequence_chain"]
    if (not experiments and len(chains) == 1 and len(expectations) == 1
            and len(chain_facts) == 1):
        chain_payload = chain_facts[0].get("payload")
        component_source_ids = (chain_payload.get("component_source_ids")
            if isinstance(chain_payload, Mapping) else None)
        # The chain's digest-bound component list must name the expectation
        # record. Merely finding one of each fact kind does not prove they
        # belong to the same embodied event.
        if (not isinstance(component_source_ids, list)
                or expectations[0] not in component_source_ids
                or (isinstance(chain_payload, Mapping)
                    and chain_payload.get("chain_id") != chains[0])):
            return None
        return {"anchor_kind": "embodied_consequence_event",
            "anchor_id": chains[0], "related_expectation_id": expectations[0]}
    return None


def build_report(*, cycle_roots: Sequence[Path], experiment_root: Path,
        freeze_export: Path) -> dict[str, Any]:
    view = FederatedDevelopmentalHistoryReadView(cycle_roots)
    try:
        frozen = json.loads(freeze_export.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("experience_anchor_freeze_invalid") from exc
    store = DevelopmentalExperimentStore(experiment_root)
    persisted = store.load_retrieval_corpus_freeze(frozen.get("freeze_id"))
    if (persisted != frozen
            or frozen.get("corpus_manifest") !=
                view.ordinary_chat_developmental_history_corpus_manifest()):
        raise ValueError("experience_anchor_freeze_source_mismatch")
    source_snapshots = list(view.source_snapshots)

    rows: list[dict[str, Any]] = []
    anchors_to_records: dict[str, set[str]] = defaultdict(set)
    kinds = Counter()
    unanchored: list[str] = []
    for ref in view.record_refs:
        record = view.get(ref["record_id"])
        anchor = _anchor(record)
        if anchor is None:
            unanchored.append(record.record_id)
            continue
        unit_digest = hashlib.sha256(json.dumps(anchor, sort_keys=True,
            separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        anchors_to_records[unit_digest].add(record.record_id)
        kinds[anchor["anchor_kind"]] += 1
        rows.append({"record_id": record.record_id,
            "record_digest": record.record_digest,
            "experience_anchor": anchor,
            "experience_unit_digest": unit_digest,
            "source_root_ids": view.source_provenance[
                record.record_id]["source_root_ids"]})
    duplicate_anchor_groups = [sorted(record_ids)
        for record_ids in anchors_to_records.values() if len(record_ids) > 1]
    unit_count = len(anchors_to_records)
    semantic = {
        "schema_version": "sentientos.federated_experience_anchor_audit:v3",
        "corpus_freeze_id": frozen["freeze_id"],
        "corpus_freeze_digest": frozen["freeze_digest"],
        "corpus_manifest_digest": frozen["corpus_manifest_digest"],
        "source_snapshot_count": len(source_snapshots),
        "source_snapshot_digest": "sha256:" + digest_payload(source_snapshots),
        "corpus_record_count": len(frozen["corpus_manifest"]["records"]),
        "anchored_record_count": len(rows),
        "unanchored_record_count": len(unanchored),
        "unanchored_record_ids": sorted(unanchored),
        "experience_anchor_kind_counts": dict(sorted(kinds.items())),
        "distinct_experience_anchor_count": unit_count,
        "duplicate_anchor_group_count": len(duplicate_anchor_groups),
        "duplicate_anchor_record_groups": duplicate_anchor_groups,
        "minimum_distinct_source_experiences": MINIMUM_SOURCE_EXPERIENCES,
        "distinct_experience_shortfall": max(
            0, MINIMUM_SOURCE_EXPERIENCES - unit_count),
        "records": sorted(rows, key=lambda row: row["record_id"]),
        "atomic_snapshot": False,
        "inference_performed": False,
        "independence_established": False,
        "phase_a_eligibility_established": False,
        "learning_established": False,
        "authority": False,
    }
    return {**semantic, "audit_digest": "sha256:" + digest_payload(semantic)}


def verify_report(*, cycle_roots: Sequence[Path], experiment_root: Path,
        freeze_export: Path, audit_path: Path) -> dict[str, Any]:
    try:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("experience_anchor_audit_invalid") from exc
    semantic = {key: value for key, value in audit.items()
        if key != "audit_digest"}
    if audit.get("audit_digest") != "sha256:" + digest_payload(semantic):
        raise ValueError("experience_anchor_audit_digest_mismatch")
    expected = build_report(cycle_roots=cycle_roots,
        experiment_root=experiment_root, freeze_export=freeze_export)
    if audit != expected:
        raise ValueError("experience_anchor_source_inventory_mismatch")
    semantic = {"schema_version":
            "sentientos.federated_experience_anchor_verification:v3",
        "status": "verified", "audit_digest": audit["audit_digest"],
        "corpus_freeze_id": audit["corpus_freeze_id"],
        "source_snapshot_count": audit["source_snapshot_count"],
        "source_snapshot_digest": audit["source_snapshot_digest"],
        "anchored_record_count": audit["anchored_record_count"],
        "distinct_experience_anchor_count": audit[
            "distinct_experience_anchor_count"],
        "distinct_experience_shortfall": audit[
            "distinct_experience_shortfall"],
        "independence_established": False,
        "phase_a_eligibility_established": False,
        "inference_performed": False, "authority": False}
    return {**semantic,
        "verification_digest": "sha256:" + digest_payload(semantic)}


def _expand_cycle_roots(cycle_roots: Sequence[Path] | None,
        cycle_parents: Sequence[Path] | None) -> list[Path]:
    roots = list(cycle_roots or ())
    for raw_parent in cycle_parents or ():
        parent = raw_parent.expanduser()
        if parent.is_symlink():
            raise ValueError("experience_anchor_cycle_parent_symlink")
        try:
            parent = parent.resolve(strict=True)
            children = sorted(parent.iterdir(), key=lambda item: item.name)
        except (OSError, RuntimeError) as exc:
            raise ValueError("experience_anchor_cycle_parent_invalid") from exc
        if not parent.is_dir():
            raise ValueError("experience_anchor_cycle_parent_invalid")
        for child in children:
            if child.is_symlink():
                raise ValueError("experience_anchor_cycle_child_symlink")
            if (child.is_dir()
                    and (child / "resident-cognition" / "history").is_dir()
                    and (child / "resident-cognition" / "state").is_dir()):
                roots.append(child)
    normalized = [path.expanduser().resolve(strict=True) for path in roots]
    if len(normalized) != len(set(normalized)):
        raise ValueError("experience_anchor_cycle_root_duplicated")
    if len(normalized) < 2:
        raise ValueError("experience_anchor_cycle_roots_insufficient")
    return normalized


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle-root", type=Path, action="append",
        help="explicit cycle directory; repeat for each cycle")
    parser.add_argument("--cycle-parent", type=Path, action="append",
        help="parent directory; include each direct child with resident cognition history and state")
    parser.add_argument("--experiment-root", type=Path, required=True)
    parser.add_argument("--freeze-export", type=Path, required=True)
    parser.add_argument("--verification-output", type=Path,
        help="optional new file for the source-replay verification receipt")
    outputs = parser.add_mutually_exclusive_group(required=True)
    outputs.add_argument("--output", type=Path)
    outputs.add_argument("--verify", type=Path)
    args = parser.parse_args()
    cycle_roots = _expand_cycle_roots(args.cycle_root, args.cycle_parent)
    if args.verify is not None:
        result = verify_report(cycle_roots=cycle_roots,
            experiment_root=args.experiment_root,
            freeze_export=args.freeze_export, audit_path=args.verify)
        if args.verification_output is not None:
            target = args.verification_output.absolute()
            if (target.exists() or target.is_symlink()
                    or not target.parent.is_dir() or target.parent.is_symlink()):
                raise ValueError("experience_anchor_verification_output_invalid")
            with target.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(result, sort_keys=True, indent=2) + "\n")
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.verification_output is not None:
        raise ValueError("experience_anchor_verification_requires_verify_mode")
    report = build_report(cycle_roots=cycle_roots,
        experiment_root=args.experiment_root,
        freeze_export=args.freeze_export)
    if (args.output.exists() or args.output.is_symlink()
            or args.output.parent.is_symlink() or not args.output.parent.is_dir()):
        raise ValueError("experience_anchor_output_exists_or_invalid")
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items()
        if key not in {"records", "unanchored_record_ids",
            "duplicate_anchor_record_groups"}}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)},
            sort_keys=True), file=sys.stderr)
        raise SystemExit(2) from exc
