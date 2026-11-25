"""Freeze an explicitly audited federated history corpus for Phase A.

No query, annotation, model inference, or history mutation is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

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


def _read_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("federated_freeze_lineage_audit_invalid")
    return value


def _verify_lineage(view: FederatedDevelopmentalHistoryReadView,
        audit_path: Path) -> tuple[dict[str, Any], str]:
    audit_path = audit_path.expanduser().resolve(strict=True)
    audit = _read_json(audit_path)
    expected = {row["record_id"]: row["record_digest"]
        for row in audit.get("verified_record_refs", [])
        if isinstance(row, dict) and isinstance(row.get("record_id"), str)
        and isinstance(row.get("record_digest"), str)}
    actual = {record_id: value["record_digest"] for record_id, value
        in view.source_provenance.items()}
    if (audit.get("runtime_admission_revalidated") is not True
            or audit.get("phase_a_eligibility_established") is not False
            or expected != actual
            or len(expected) != audit.get(
                "unique_fully_admitted_state_receipt_matched_record_count")):
        raise ValueError("federated_freeze_lineage_audit_mismatch")
    return audit, hashlib.sha256(audit_path.read_bytes()).hexdigest()


def _publish_binding(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink() or path.parent.is_symlink():
        raise ValueError("federated_freeze_binding_output_exists")
    if not path.parent.is_dir():
        raise ValueError("federated_freeze_binding_parent_missing")
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(value, sort_keys=True, indent=2) + "\n")
    except FileExistsError as exc:
        raise ValueError("federated_freeze_binding_output_exists") from exc


def freeze(*, cycle_roots: list[Path], experiment_root: Path,
        lineage_audit: Path, binding_output: Path,
        freeze_export: Path | None = None) -> dict[str, Any]:
    view = FederatedDevelopmentalHistoryReadView(cycle_roots)
    audit, audit_sha256 = _verify_lineage(view, lineage_audit)
    store = DevelopmentalExperimentStore(experiment_root)
    freeze_id = store.persist_retrieval_corpus_freeze(owner=view)
    frozen = store.load_retrieval_corpus_freeze(freeze_id)
    if freeze_export is not None:
        _publish_binding(freeze_export, frozen)
    manifest = view.ordinary_chat_developmental_history_corpus_manifest()
    if frozen.get("corpus_manifest") != manifest:
        raise ValueError("federated_freeze_manifest_mismatch")
    view.verify_sources_unchanged()
    provenance = view.source_provenance
    semantic = {
        "schema_version": "sentientos.federated_retrieval_corpus_freeze_binding:v1",
        "freeze_id": freeze_id,
        "freeze_digest": frozen["freeze_digest"],
        "history_state_digest": frozen["history_state_digest"],
        "corpus_manifest_digest": frozen["corpus_manifest_digest"],
        "record_count": len(manifest["records"]),
        "lineage_audit_sha256": audit_sha256,
        "lineage_audit_unique_record_count": audit[
            "unique_fully_admitted_state_receipt_matched_record_count"],
        "source_provenance_digest": "sha256:" + digest_payload(provenance),
        "source_snapshots": list(view.source_snapshots),
        "source_snapshot_digest": "sha256:" + digest_payload(
            list(view.source_snapshots)),
        "configured_semantic_embedder_model_id": frozen[
            "configured_semantic_embedder_model_id"],
        "configured_semantic_embedder_revision": frozen[
            "configured_semantic_embedder_revision"],
        "inference_performed": False,
        "generative_model_invoked": False,
        "learning_established": False,
        "authority": False,
    }
    binding = {**semantic, "binding_digest": "sha256:" + digest_payload(semantic)}
    _publish_binding(binding_output, binding)
    return {"status": "frozen", "freeze_id": freeze_id,
        "freeze_digest": frozen["freeze_digest"],
        "record_count": len(manifest["records"]),
        "history_state_digest": frozen["history_state_digest"],
        "configured_semantic_embedder_model_id": frozen[
            "configured_semantic_embedder_model_id"],
        "inference_performed": False, "authority": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle-root", type=Path, action="append", required=True,
        help="explicit rootless cognition cycle directory; repeat for each source")
    parser.add_argument("--experiment-root", type=Path, required=True)
    parser.add_argument("--lineage-audit", type=Path, required=True)
    parser.add_argument("--binding-output", type=Path, required=True)
    parser.add_argument("--freeze-export", type=Path,
        help="optional create-only copy of the immutable freeze JSON")
    args = parser.parse_args()
    result = freeze(cycle_roots=args.cycle_root,
        experiment_root=args.experiment_root,
        lineage_audit=args.lineage_audit,
        binding_output=args.binding_output,
        freeze_export=args.freeze_export)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)},
            sort_keys=True), file=sys.stderr)
        raise SystemExit(2) from exc
