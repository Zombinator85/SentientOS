#!/usr/bin/env python3
"""Run and seal a frozen federated ordinary-chat history comparison."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.evaluate_semantic_history_retrieval import (
    _read_json_object,
    _read_owner_for_experiment,
)
from work.audit_federated_experience_anchors import (
    _expand_cycle_roots,
    verify_report as verify_experience_anchor_report,
)
from sentientos.federated_history_source_manifest import (
    FederatedArchiveHistoryRecordResolver,
    complete_federated_retrieval_review_template,
    assemble_federated_retrieval_review_consensus,
    digest_payload,
    make_federated_history_source_manifest,
    make_federated_retrieval_query_set,
    make_federated_retrieval_reviewer_packet,
    score_federated_retrieval_comparison,
    source_id_for_origin,
    validate_federated_history_source_manifest,
    validate_federated_retrieval_comparison,
    validate_federated_retrieval_query_set,
    validate_federated_retrieval_reviewer_packet,
    validate_federated_retrieval_review_consensus,
    validate_federated_retrieval_review_submission,
    validate_federated_retrieval_score,
    _verified_query_experience_anchors,
)
from sentientos.federated_developmental_history import (
    FederatedDevelopmentalHistoryReadView,
)
from sentientos.federated_ordinary_chat_retrieval import (
    project_federated_candidate_record,
    run_federated_ordinary_chat_comparison,
)


def _write_new_artifact(path: Path, value: dict[str, Any]) -> None:
    target = path.absolute()
    if (target.exists() or target.is_symlink()
            or not target.parent.is_dir() or target.parent.is_symlink()):
        raise ValueError("federated_comparison_output_path_invalid")
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True,
        indent=2, allow_nan=False) + "\n").encode("utf-8")
    if len(payload) > 64 * 1024 * 1024:
        raise ValueError("federated_comparison_output_unbounded")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(str(target), flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            target.unlink()
        except OSError:
            pass
        raise


def _load_private_owners(path: Path,
        expected_source_ids: set[str] | None = None
        ) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    private_bindings = _read_json_object(path,
        error_prefix="federated_source_bindings")
    rows = private_bindings.get("sources")
    if (set(private_bindings) != {"schema_version", "sources"}
            or private_bindings["schema_version"] !=
                "sentientos.federated_semantic_history_private_source_bindings:v1"
            or not isinstance(rows, list) or not rows
            or any(not isinstance(row, dict)
                or not {"origin_key", "cognition_config", "serving_config"}
                    <= set(row)
                or set(row) - {"source_id", "origin_key",
                    "cognition_config", "serving_config"}
                or (expected_source_ids is not None
                    and "source_id" not in row) for row in rows)):
        raise ValueError("federated_source_bindings_invalid")
    normalized_rows = []
    for row in rows:
        derived_source_id = source_id_for_origin(row["origin_key"])
        if (row.get("source_id", derived_source_id) != derived_source_id):
            raise ValueError("federated_source_binding_origin_mismatch")
        normalized_rows.append((row, derived_source_id))
    normalized_source_ids = {source_id for _, source_id in normalized_rows}
    if (len(normalized_source_ids) != len(normalized_rows)
            or expected_source_ids is not None
                and normalized_source_ids != expected_source_ids):
        raise ValueError("federated_source_bindings_invalid")
    owners: dict[str, dict[str, Any]] = {}
    source_manifests = []
    for row, source_id in normalized_rows:
        owner = _read_owner_for_experiment(
            cognition_config_path=Path(row["cognition_config"]),
            serving_config_path=Path(row["serving_config"]))
        owners[source_id] = {"origin_key": row["origin_key"],
            "owner": owner}
        source_manifests.append({"origin_key": row["origin_key"],
            "corpus_manifest":
                owner.ordinary_chat_developmental_history_corpus_manifest()})
    return owners, source_manifests


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run",
        help="run both selectors over a frozen source/query set")
    run_parser.add_argument("--manifest", required=True, type=Path,
        help="validated federated source manifest JSON")
    run_parser.add_argument("--query-set", required=True, type=Path,
        help="frozen federated query set JSON")
    run_parser.add_argument("--source-bindings", required=True, type=Path,
        help="private JSON owner/config mapping; never copied into output")
    run_parser.add_argument("--output", required=True, type=Path,
        help="new comparison artifact path; existing files are not overwritten")
    run_parser.add_argument("--max-selected-records", type=int, default=8)
    freeze_sources_parser = commands.add_parser("freeze-sources",
        help="seal manifests from the current verified owner inventories")
    freeze_sources_parser.add_argument("--source-bindings", required=True,
        type=Path, help="private JSON owner/config mapping")
    freeze_sources_parser.add_argument("--output", required=True, type=Path)
    freeze_queries_parser = commands.add_parser("freeze-queries",
        help="seal balanced queries and source-experience anchors")
    freeze_queries_parser.add_argument("--manifest", required=True, type=Path)
    freeze_queries_parser.add_argument("--query-spec", required=True, type=Path,
        help="questions, strata, source refs, budget, and target model identity")
    freeze_queries_parser.add_argument("--output", required=True, type=Path)
    review_parser = commands.add_parser("review-packet",
        help="create an exhaustive blinded human annotation packet")
    review_parser.add_argument("--manifest", required=True, type=Path)
    review_parser.add_argument("--query-set", required=True, type=Path)
    review_parser.add_argument("--source-bindings", required=True, type=Path,
        help="private JSON owner/config mapping")
    review_parser.add_argument("--reviewer-digest", required=True,
        help="externally assigned 64-character lowercase SHA-256 pseudonym")
    review_parser.add_argument("--output", required=True, type=Path)
    archive_review_parser = commands.add_parser("archive-review-packet",
        help="create a blinded packet from the verified rootless history archive")
    for name in ("manifest", "query-set", "archive-binding",
            "experience-anchor-audit", "experiment-root", "freeze-export",
            "reviewer-digest", "output"):
        archive_review_parser.add_argument("--" + name, required=True,
            type=Path if name not in {"reviewer-digest"} else str)
    archive_review_parser.add_argument("--cycle-parent", type=Path,
        action="append", required=True,
        help="parent directory containing archived cognition cycle roots")
    archive_run_parser = commands.add_parser("archive-run",
        help="run frozen retrieval against the verified archive using a pinned CPU embedder")
    for name in ("manifest", "query-set", "archive-binding",
            "experience-anchor-audit", "experience-anchor-verification",
            "output"):
        archive_run_parser.add_argument("--" + name, required=True, type=Path)
    archive_cycle_args = archive_run_parser.add_mutually_exclusive_group(
        required=True)
    archive_cycle_args.add_argument("--cycle-parent", type=Path,
        action="append",
        help="parent directory containing archived cognition cycle roots")
    archive_cycle_args.add_argument("--cycle-root", type=Path,
        action="append",
        help="explicit archived cognition cycle directory; repeat per source")
    archive_run_parser.add_argument("--semantic-model-id", required=True,
        help="cached sentence-transformers model ID; inference is pinned to CPU")
    archive_run_parser.add_argument("--semantic-model-revision", required=True,
        help="immutable 40-character model commit already present in local cache")
    archive_run_parser.add_argument("--max-selected-records", type=int, default=8)
    complete_parser = commands.add_parser("complete-review",
        help="seal human labels against a blinded reviewer packet")
    complete_parser.add_argument("--manifest", required=True, type=Path)
    complete_parser.add_argument("--query-set", required=True, type=Path)
    complete_parser.add_argument("--packet", required=True, type=Path)
    complete_parser.add_argument("--labels", required=True, type=Path,
        help="JSON label file ordered exactly like the packet template")
    complete_parser.add_argument("--output", required=True, type=Path)
    consensus_parser = commands.add_parser("consensus",
        help="seal blinded adjudication of two distinct review submissions")
    for name in ("manifest", "query-set", "packet-a", "submission-a",
            "packet-b", "submission-b", "labels", "output"):
        consensus_parser.add_argument("--" + name, required=True, type=Path)
    consensus_parser.add_argument("--adjudicator-digest", required=True)
    consensus_parser.add_argument("--blind-consensus-confirmed",
        action="store_true", required=True,
        help="attest labels were adjudicated without seeing retrieval outcomes")
    score_parser = commands.add_parser("score",
        help="score a frozen comparison against validated reviewer consensus")
    for name in ("manifest", "query-set", "comparison", "packet-a",
            "submission-a", "packet-b", "submission-b", "consensus", "output"):
        score_parser.add_argument("--" + name, required=True, type=Path)
    score_parser.add_argument("--experience-anchor-audit", required=True,
        type=Path, help="verified record-to-event anchor audit for query source refs")
    score_parser.add_argument("--cycle-parent", type=Path, action="append",
        required=True, help="parent of history/state cycle directories to replay")
    score_parser.add_argument("--experiment-root", required=True, type=Path,
        help="private store containing the frozen retrieval corpus")
    score_parser.add_argument("--freeze-export", required=True, type=Path,
        help="exported frozen corpus bound by the anchor audit")
    args = parser.parse_args(argv)
    try:
        if args.command == "consensus":
            packet_a = _read_json_object(args.packet_a,
                error_prefix="federated_reviewer_packet_a")
            packet_b = _read_json_object(args.packet_b,
                error_prefix="federated_reviewer_packet_b")
            manifest = _read_json_object(args.manifest,
                error_prefix="federated_manifest")
            query_set = _read_json_object(args.query_set,
                error_prefix="federated_query_set")
            validate_federated_history_source_manifest(manifest)
            query_set = validate_federated_retrieval_query_set(
                manifest=manifest, value=query_set)
            packet_a = validate_federated_retrieval_reviewer_packet(
                manifest=manifest, query_set=query_set, value=packet_a)
            packet_b = validate_federated_retrieval_reviewer_packet(
                manifest=manifest, query_set=query_set, value=packet_b)
            if (not isinstance(packet_a.get("review_template"), dict)
                    or not isinstance(packet_b.get("review_template"), dict)):
                raise ValueError("federated_review_packet_template_missing")
            submission_a = _read_json_object(args.submission_a,
                error_prefix="federated_review_submission_a")
            submission_b = _read_json_object(args.submission_b,
                error_prefix="federated_review_submission_b")
            labels = _read_json_object(args.labels,
                error_prefix="federated_consensus_labels")
            if (set(labels) != {"schema_version", "labels"}
                    or labels.get("schema_version") !=
                        "sentientos.federated_semantic_history_review_labels:v1"
                    or not isinstance(labels.get("labels"), list)):
                raise ValueError("federated_consensus_labels_invalid")
            consensus = assemble_federated_retrieval_review_consensus(
                reviewer_a_template=packet_a["review_template"],
                reviewer_a_submission=submission_a,
                reviewer_b_template=packet_b["review_template"],
                reviewer_b_submission=submission_b,
                consensus_labels=labels["labels"],
                adjudicator_digest=args.adjudicator_digest,
                blind_consensus_confirmed=args.blind_consensus_confirmed)
            consensus = validate_federated_retrieval_review_consensus(
                reviewer_a_template=packet_a["review_template"],
                reviewer_a_submission=submission_a,
                reviewer_b_template=packet_b["review_template"],
                reviewer_b_submission=submission_b, consensus=consensus)
            _write_new_artifact(args.output, consensus)
            print(json.dumps({"consensus_digest": consensus["consensus_digest"],
                "pair_count": consensus["pair_count"],
                "initial_record_label_agreement_rate":
                    consensus["initial_record_label_agreement_rate"],
                "reviewer_independence_established": False,
                "output": str(args.output.absolute()), "authority": False},
                ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "score":
            manifest = _read_json_object(args.manifest,
                error_prefix="federated_manifest")
            query_set = _read_json_object(args.query_set,
                error_prefix="federated_query_set")
            comparison = _read_json_object(args.comparison,
                error_prefix="federated_comparison")
            packet_a = _read_json_object(args.packet_a,
                error_prefix="federated_reviewer_packet_a")
            packet_b = _read_json_object(args.packet_b,
                error_prefix="federated_reviewer_packet_b")
            validate_federated_history_source_manifest(manifest)
            query_set = validate_federated_retrieval_query_set(
                manifest=manifest, value=query_set)
            packet_a = validate_federated_retrieval_reviewer_packet(
                manifest=manifest, query_set=query_set, value=packet_a)
            packet_b = validate_federated_retrieval_reviewer_packet(
                manifest=manifest, query_set=query_set, value=packet_b)
            submission_a = _read_json_object(args.submission_a,
                error_prefix="federated_review_submission_a")
            submission_b = _read_json_object(args.submission_b,
                error_prefix="federated_review_submission_b")
            consensus = _read_json_object(args.consensus,
                error_prefix="federated_review_consensus")
            experience_anchor_audit = _read_json_object(
                args.experience_anchor_audit,
                error_prefix="federated_experience_anchor_audit")
            cycle_roots = _expand_cycle_roots(None, args.cycle_parent)
            experience_anchor_verification = verify_experience_anchor_report(
                cycle_roots=cycle_roots,
                experiment_root=args.experiment_root,
                freeze_export=args.freeze_export,
                audit_path=args.experience_anchor_audit)
            if (not isinstance(packet_a.get("review_template"), dict)
                    or not isinstance(packet_b.get("review_template"), dict)):
                raise ValueError("federated_review_packet_template_missing")
            score = score_federated_retrieval_comparison(
                manifest=manifest, query_set=query_set, comparison=comparison,
                reviewer_a_template=packet_a["review_template"],
                reviewer_a_submission=submission_a,
                reviewer_b_template=packet_b["review_template"],
                reviewer_b_submission=submission_b, consensus=consensus,
                experience_anchor_audit=experience_anchor_audit,
                experience_anchor_verification=experience_anchor_verification)
            score = validate_federated_retrieval_score(
                manifest=manifest, query_set=query_set, comparison=comparison,
                reviewer_a_template=packet_a["review_template"],
                reviewer_a_submission=submission_a,
                reviewer_b_template=packet_b["review_template"],
                reviewer_b_submission=submission_b, consensus=consensus,
                experience_anchor_audit=experience_anchor_audit,
                experience_anchor_verification=experience_anchor_verification,
                score=score)
            _write_new_artifact(args.output, score)
            print(json.dumps({"score_digest": score["score_digest"],
                "learning_established": False,
                "output": str(args.output.absolute()), "authority": False},
                ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "complete-review":
            packet = _read_json_object(args.packet,
                error_prefix="federated_reviewer_packet")
            manifest = _read_json_object(args.manifest,
                error_prefix="federated_manifest")
            query_set = _read_json_object(args.query_set,
                error_prefix="federated_query_set")
            validate_federated_history_source_manifest(manifest)
            query_set = validate_federated_retrieval_query_set(
                manifest=manifest, value=query_set)
            if (set(packet) != {"schema_version", "query_set_id",
                    "query_set_digest", "federated_manifest_digest",
                    "reviewer_digest", "review_pairs", "review_template",
                    "generative_model_invoked", "authority", "packet_digest"}
                    or packet.get("schema_version") !=
                        "sentientos.federated_semantic_history_reviewer_packet:v1"
                    or packet.get("generative_model_invoked") is not False
                    or packet.get("authority") is not False
                    or not isinstance(packet.get("review_pairs"), list)
                    or not isinstance(packet.get("review_template"), dict)):
                raise ValueError("federated_reviewer_packet_invalid")
            packet_body = {key: value for key, value in packet.items()
                if key != "packet_digest"}
            if packet.get("packet_digest") != digest_payload(packet_body):
                raise ValueError("federated_reviewer_packet_digest_mismatch")
            packet = validate_federated_retrieval_reviewer_packet(
                manifest=manifest, query_set=query_set, value=packet)
            pairs = packet["review_pairs"]
            template = packet["review_template"]
            if (not pairs or len(pairs) > 25_000
                    or len(template.get("annotations", [])) != len(pairs)
                    or template.get("review_pair_digests") !=
                        [pair.get("review_pair_digest") for pair in pairs]):
                raise ValueError("federated_reviewer_packet_roster_invalid")
            for pair, annotation in zip(pairs, template["annotations"]):
                body = {key: value for key, value in pair.items()
                    if key != "review_pair_digest"}
                if (pair.get("review_pair_digest") != digest_payload(body)
                        or any(pair.get(key) != annotation.get(key) for key in
                            ("question_digest", "record_ref_id", "record_digest"))):
                    raise ValueError("federated_reviewer_packet_pair_binding_invalid")
            label_file = _read_json_object(args.labels,
                error_prefix="federated_review_labels")
            if (set(label_file) != {"schema_version", "labels"}
                    or label_file.get("schema_version") !=
                        "sentientos.federated_semantic_history_review_labels:v1"
                    or not isinstance(label_file.get("labels"), list)):
                raise ValueError("federated_review_labels_invalid")
            submission = complete_federated_retrieval_review_template(
                template=template, labels=label_file["labels"])
            submission = validate_federated_retrieval_review_submission(
                template=template, submission=submission)
            _write_new_artifact(args.output, submission)
            print(json.dumps({"submission_digest": submission["submission_digest"],
                "packet_digest": packet["packet_digest"],
                "annotation_count": len(submission["annotations"]),
                "output": str(args.output.absolute()), "authority": False},
                ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "freeze-sources":
            _, source_manifests = _load_private_owners(args.source_bindings)
            manifest = make_federated_history_source_manifest(
                sources=source_manifests)
            validate_federated_history_source_manifest(manifest)
            _write_new_artifact(args.output, manifest)
            print(json.dumps({"federated_manifest_digest":
                manifest["federated_manifest_digest"],
                "source_count": len(manifest["sources"]),
                "record_count": sum(len(rows) for rows in source_records.values()),
                "output": str(args.output.absolute()), "authority": False},
                ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "freeze-queries":
            manifest = _read_json_object(args.manifest,
                error_prefix="federated_manifest")
            validate_federated_history_source_manifest(manifest)
            spec = _read_json_object(args.query_spec,
                error_prefix="federated_query_spec")
            required_spec = {"schema_version", "questions", "strata",
                "source_experience_refs", "max_input_chars",
                "target_model_identity"}
            if (set(spec) != required_spec
                    or spec["schema_version"] !=
                        "sentientos.federated_semantic_history_query_spec:v1"):
                raise ValueError("federated_query_spec_fields_invalid")
            query_set = make_federated_retrieval_query_set(manifest=manifest,
                questions=spec["questions"], strata=spec["strata"],
                source_experience_refs=spec["source_experience_refs"],
                max_input_chars=spec["max_input_chars"],
                target_model_identity=spec["target_model_identity"])
            query_set = validate_federated_retrieval_query_set(
                manifest=manifest, value=query_set)
            _write_new_artifact(args.output, query_set)
            print(json.dumps({"query_set_id": query_set["query_set_id"],
                "query_set_digest": query_set["query_set_digest"],
                "question_count": query_set["question_count"],
                "output": str(args.output.absolute()),
                "inference_performed": False, "authority": False},
                ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "review-packet":
            manifest = _read_json_object(args.manifest,
                error_prefix="federated_manifest")
            query_set = _read_json_object(args.query_set,
                error_prefix="federated_query_set")
            records = validate_federated_history_source_manifest(manifest)
            query_set = validate_federated_retrieval_query_set(
                manifest=manifest, value=query_set)
            owners, _ = _load_private_owners(args.source_bindings,
                expected_source_ids=set(records))
            from sentientos.federated_history_source_manifest import (
                FederatedHistoryRecordResolver,
            )
            resolver = FederatedHistoryRecordResolver(manifest=manifest,
                source_bindings=owners,
                project_record=project_federated_candidate_record)
            pairs = resolver.build_review_pairs(query_set=query_set)
            packet = make_federated_retrieval_reviewer_packet(
                manifest=manifest, query_set=query_set,
                review_pairs=pairs, reviewer_digest=args.reviewer_digest)
            packet = validate_federated_retrieval_reviewer_packet(
                manifest=manifest, query_set=query_set, value=packet)
            _write_new_artifact(args.output, packet)
            print(json.dumps({"packet_digest": packet["packet_digest"],
                "query_set_id": query_set["query_set_id"],
                "review_pair_count": len(packet["review_pairs"]),
                "reviewer_digest": packet["reviewer_digest"],
                "output": str(args.output.absolute()),
                "generative_model_invoked": False, "authority": False},
                ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "archive-review-packet":
            manifest = _read_json_object(args.manifest,
                error_prefix="federated_manifest")
            query_set = _read_json_object(args.query_set,
                error_prefix="federated_query_set")
            archive_binding = _read_json_object(args.archive_binding,
                error_prefix="federated_archive_binding")
            experience_anchor_audit = _read_json_object(
                args.experience_anchor_audit,
                error_prefix="federated_experience_anchor_audit")
            source_records = validate_federated_history_source_manifest(manifest)
            query_set = validate_federated_retrieval_query_set(
                manifest=manifest, value=query_set)
            cycle_roots = _expand_cycle_roots(None, args.cycle_parent)
            experience_anchor_verification = verify_experience_anchor_report(
                cycle_roots=cycle_roots,
                experiment_root=args.experiment_root,
                freeze_export=args.freeze_export,
                audit_path=args.experience_anchor_audit)
            _verified_query_experience_anchors(query_set=query_set,
                anchor_audit=experience_anchor_audit,
                anchor_verification=experience_anchor_verification)
            read_view = FederatedDevelopmentalHistoryReadView(cycle_roots)
            resolver = FederatedArchiveHistoryRecordResolver(
                manifest=manifest, archive_binding=archive_binding,
                experience_anchor_audit=experience_anchor_audit,
                experience_anchor_verification=experience_anchor_verification,
                read_view=read_view,
                project_record=project_federated_candidate_record)
            pairs = resolver.build_review_pairs(query_set=query_set)
            if len(pairs) != len(query_set["questions"]) * sum(
                    len(rows) for rows in source_records.values()):
                raise ValueError("federated_archive_review_pair_count_invalid")
            packet = make_federated_retrieval_reviewer_packet(
                manifest=manifest, query_set=query_set,
                review_pairs=pairs, reviewer_digest=args.reviewer_digest)
            packet = validate_federated_retrieval_reviewer_packet(
                manifest=manifest, query_set=query_set, value=packet)
            _write_new_artifact(args.output, packet)
            print(json.dumps({"packet_digest": packet["packet_digest"],
                "query_set_id": query_set["query_set_id"],
                "review_pair_count": len(packet["review_pairs"]),
                "reviewer_digest": packet["reviewer_digest"],
                "generative_model_invoked": False,
                "learning_established": False,
                "output": str(args.output.absolute()), "authority": False},
                ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "archive-run":
            manifest = _read_json_object(args.manifest,
                error_prefix="federated_manifest")
            query_set = _read_json_object(args.query_set,
                error_prefix="federated_query_set")
            archive_binding = _read_json_object(args.archive_binding,
                error_prefix="federated_archive_binding")
            experience_anchor_audit = _read_json_object(
                args.experience_anchor_audit,
                error_prefix="federated_experience_anchor_audit")
            experience_anchor_verification = _read_json_object(
                args.experience_anchor_verification,
                error_prefix="federated_experience_anchor_verification")
            validate_federated_history_source_manifest(manifest)
            query_set = validate_federated_retrieval_query_set(
                manifest=manifest, value=query_set)
            cycle_roots = _expand_cycle_roots(args.cycle_root,
                args.cycle_parent)
            _verified_query_experience_anchors(query_set=query_set,
                anchor_audit=experience_anchor_audit,
                anchor_verification=experience_anchor_verification)
            read_view = FederatedDevelopmentalHistoryReadView(cycle_roots)
            resolver = FederatedArchiveHistoryRecordResolver(
                manifest=manifest, archive_binding=archive_binding,
                experience_anchor_audit=experience_anchor_audit,
                experience_anchor_verification=experience_anchor_verification,
                read_view=read_view,
                project_record=project_federated_candidate_record)
            comparison = run_federated_ordinary_chat_comparison(
                manifest=manifest, query_set=query_set, resolver=resolver,
                semantic_model_id=args.semantic_model_id,
                semantic_model_revision=args.semantic_model_revision,
                target_model_identity=query_set["target_model_identity"],
                max_selected_records=args.max_selected_records)
            comparison = validate_federated_retrieval_comparison(
                manifest=manifest, query_set=query_set, value=comparison)
            _write_new_artifact(args.output, comparison)
            print(json.dumps({"comparison_digest": comparison["comparison_digest"],
                "query_set_id": query_set["query_set_id"],
                "query_count": len(comparison["query_results"]),
                "semantic_embedder_identity_digest":
                    comparison["semantic_embedder_identity_digest"],
                "output": str(args.output.absolute()),
                "generative_model_invoked": False,
                "semantic_embedder_device": "cpu",
                "learning_established": False, "authority": False},
                ensure_ascii=False, sort_keys=True))
            return 0
        manifest = _read_json_object(args.manifest,
            error_prefix="federated_manifest")
        query_set = _read_json_object(args.query_set,
            error_prefix="federated_query_set")
        records = validate_federated_history_source_manifest(manifest)
        query_set = validate_federated_retrieval_query_set(
            manifest=manifest, value=query_set)
        owners, _ = _load_private_owners(args.source_bindings,
            expected_source_ids=set(records))
        model_configs = set()
        for binding in owners.values():
            owner = binding["owner"]
            model_configs.add((owner.config.semantic_history_model_id,
                owner.config.semantic_history_model_revision))
        if len(model_configs) != 1:
            raise ValueError("federated_source_embedder_configuration_mismatch")
        model_id, model_revision = next(iter(model_configs))
        from sentientos.federated_history_source_manifest import (
            FederatedHistoryRecordResolver,
        )
        resolver = FederatedHistoryRecordResolver(manifest=manifest,
            source_bindings=owners,
            project_record=project_federated_candidate_record)
        comparison = run_federated_ordinary_chat_comparison(
            manifest=manifest, query_set=query_set, resolver=resolver,
            semantic_model_id=model_id,
            semantic_model_revision=model_revision,
            target_model_identity=query_set["target_model_identity"],
            max_selected_records=args.max_selected_records)
        comparison = validate_federated_retrieval_comparison(
            manifest=manifest, query_set=query_set, value=comparison)
        _write_new_artifact(args.output, comparison)
        print(json.dumps({"comparison_digest": comparison["comparison_digest"],
            "query_set_id": query_set["query_set_id"],
            "query_count": len(comparison["query_results"]),
            "semantic_embedder_identity_digest":
                comparison["semantic_embedder_identity_digest"],
            "output": str(args.output.absolute()),
            "generative_model_invoked": False,
            "semantic_embedder_may_have_been_invoked": model_id is not None,
            "authority": False, "learning_established": False},
            ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"federated retrieval comparison failed: {exc}",
            file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
