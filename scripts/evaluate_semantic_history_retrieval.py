#!/usr/bin/env python3
"""Freeze, run, seal blinded reviews, or score semantic history retrieval."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentientos.developmental_history_intervention_experiment import (
    DevelopmentalExperimentStore,
    DevelopmentalHistoryInterventionError,
    MAX_EXPERIMENT_ARTIFACT_BYTES,
)
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.resident_cognitive_model_serving import (
    CONFIG_ENV as SERVING_CONFIG_ENV, ResidentCognitiveInvocationReceiptReader,
    load_config as load_serving_config,
)
from sentientos.governed_local_model_invocation import LocalModelInvoker
from sentientos.resident_developmental_cognition import (
    CONFIG_ENV as COGNITION_CONFIG_ENV, ResidentDevelopmentalCognitionOwner,
    load_config as load_cognition_config,
)
from sentientos.codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK, RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from sentientos.resident_developmental_writeback import (
    ResidentDevelopmentalWritebackController,
)
from sentientos.runtime_admission import (
    AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier,
)
from sentientos.semantic_history_retrieval_evaluation import (
    build_retrieval_consensus_template,
    build_retrieval_reviewer_template,
    make_retrieval_relevance_annotations,
)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate_json_key")
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise ValueError(f"invalid_json_constant:{value}")


def _read_json_object(path: Path, *, error_prefix: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{error_prefix}_file_not_regular")
    if path.stat().st_size > MAX_EXPERIMENT_ARTIFACT_BYTES:
        raise ValueError(f"{error_prefix}_file_unbounded")
    value = json.loads(path.read_text(encoding="utf-8"),
        object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    if not isinstance(value, dict):
        raise ValueError(f"{error_prefix}_object_required")
    return value


def _emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
        allow_nan=False))


class _ReceiptOnlyInvoker(LocalModelInvoker):
    """Provide receipt verification while rejecting all inference methods."""
    def __init__(self, reader: ResidentCognitiveInvocationReceiptReader) -> None:
        self.reader = reader

    def build_request(self, **kwargs: Any) -> NoReturn:
        raise RuntimeError("retrieval_freeze_cannot_invoke_model")

    def invoke(self, request: Any, **kwargs: Any) -> NoReturn:
        raise RuntimeError("retrieval_freeze_cannot_invoke_model")

    def verify_persisted_invocation_receipt(self, receipt_id: str,
            receipt_digest: str, **kwargs: Any) -> Mapping[str, Any]:
        return self.reader.verify_persisted_invocation_receipt(
            receipt_id, receipt_digest, **kwargs)


def _read_owner_for_experiment(*, cognition_config_path: Path,
        serving_config_path: Path) -> ResidentDevelopmentalCognitionOwner:
    config = load_cognition_config(cognition_config_path)
    if not config.enabled:
        raise ValueError("resident_cognition_disabled")
    serving_config = load_serving_config(str(serving_config_path))
    if not serving_config.enabled or not serving_config.installation_identity:
        raise ValueError("resident_serving_configuration_disabled")
    identity = InstallationIdentity.parse(serving_config.installation_identity)
    installation = InstallationStateRegistry.system().open_read_only(identity)
    reader = ResidentCognitiveInvocationReceiptReader(installation)
    ledger = AdmissionLedger(config.state_root / "runtime_admissions.json")
    definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK:
        RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}
    writeback = ResidentDevelopmentalWritebackController(
        history_root=config.history_root,
        admission_verifier=RuntimeAdmissionVerifier(
            definitions=definitions, ledger=ledger),
        current_sequence=ledger.current_sequence)
    return ResidentDevelopmentalCognitionOwner(config=config,
        writeback=writeback,
        admission_authority=RuntimeAdmissionAuthority(
            definitions=definitions, ledger=ledger),
        invoker=_ReceiptOnlyInvoker(reader),
        current_sequence=ledger.current_sequence)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze_parser = subparsers.add_parser("freeze",
        help="capture an immutable corpus freeze from resident cognition state")
    freeze_parser.add_argument("--config", type=Path,
        default=os.environ.get(COGNITION_CONFIG_ENV))
    freeze_parser.add_argument("--serving-config", type=Path,
        default=os.environ.get(SERVING_CONFIG_ENV))
    packet_parser = subparsers.add_parser("packet",
        help="print a blinded query and corpus-reference packet")
    packet_parser.add_argument("--state-root", required=True, type=Path)
    packet_parser.add_argument("--cohort-id", required=True)
    reviewer_parser = subparsers.add_parser("review-template",
        help="create one exhaustive blank-label reviewer submission")
    reviewer_parser.add_argument("--state-root", required=True, type=Path)
    reviewer_parser.add_argument("--cohort-id", required=True)
    reviewer_parser.add_argument("--reviewer-digest", required=True,
        help="externally assigned 64-character lowercase SHA-256 reviewer pseudonym")
    consensus_parser = subparsers.add_parser("consensus-template",
        help="create ordered blank consensus rows from a blinded packet")
    consensus_parser.add_argument("--state-root", required=True, type=Path)
    consensus_parser.add_argument("--cohort-id", required=True)
    record_parser = subparsers.add_parser("record",
        help="resolve one cohort-bound history record for blinded adjudication")
    record_parser.add_argument("--config", type=Path,
        default=os.environ.get(COGNITION_CONFIG_ENV))
    record_parser.add_argument("--serving-config", type=Path,
        default=os.environ.get(SERVING_CONFIG_ENV))
    record_parser.add_argument("--cohort-id", required=True)
    record_parser.add_argument("--record-id", required=True)
    pair_parser = subparsers.add_parser("review-pair",
        help="resolve one blinded query-record pair for adjudication")
    pair_parser.add_argument("--config", type=Path,
        default=os.environ.get(COGNITION_CONFIG_ENV))
    pair_parser.add_argument("--serving-config", type=Path,
        default=os.environ.get(SERVING_CONFIG_ENV))
    pair_parser.add_argument("--cohort-id", required=True)
    pair_parser.add_argument("--question-digest", required=True)
    pair_parser.add_argument("--record-id", required=True)
    seal_parser = subparsers.add_parser("seal-annotations",
        help="bind two blinded reviews and consensus to a cohort packet")
    seal_parser.add_argument("--state-root", required=True, type=Path)
    seal_parser.add_argument("--cohort-id", required=True)
    seal_parser.add_argument("--reviews", required=True, type=Path,
        help="packet-bound JSON object produced by assemble-reviews")
    assemble_parser = subparsers.add_parser("assemble-reviews",
        help="validate and combine packet-bound reviewer and consensus files")
    assemble_parser.add_argument("--state-root", required=True, type=Path)
    assemble_parser.add_argument("--cohort-id", required=True)
    assemble_parser.add_argument("--consensus", required=True, type=Path)
    assemble_parser.add_argument("--reviewer-a", required=True, type=Path)
    assemble_parser.add_argument("--reviewer-b", required=True, type=Path)
    assemble_parser.add_argument("--blind-consensus-confirmed", action="store_true",
        required=True, help="assert that blind review and consensus are complete")
    query_parser = subparsers.add_parser("queries",
        help="seal a balanced query set against an existing corpus freeze")
    query_parser.add_argument("--state-root", required=True, type=Path)
    query_parser.add_argument("--corpus-freeze-id", required=True)
    query_parser.add_argument("--query-set", required=True, type=Path,
        help="JSON object with questions/strata and either unique source-experience digests or frozen corpus record IDs")
    query_parser.add_argument("--max-input-chars", type=int, default=8000)
    run_parser = subparsers.add_parser("run",
        help="run a sealed query set (may invoke the configured embedder)")
    run_parser.add_argument("--config", type=Path,
        default=os.environ.get(COGNITION_CONFIG_ENV))
    run_parser.add_argument("--serving-config", type=Path,
        default=os.environ.get(SERVING_CONFIG_ENV))
    run_parser.add_argument("--query-set-id", required=True)
    run_parser.add_argument("--max-input-chars", type=int, default=8000)
    score_parser = subparsers.add_parser("score",
        help="score and persist a completed annotation set")
    score_parser.add_argument("--state-root", required=True, type=Path)
    score_parser.add_argument("--cohort-id", required=True)
    score_parser.add_argument("--annotations", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command in {"freeze", "record", "review-pair"} and (args.config is None
            or args.serving_config is None):
        parser.error(f"{args.command} requires --config or {COGNITION_CONFIG_ENV} and "
            f"--serving-config or {SERVING_CONFIG_ENV}")
    if args.command == "run" and (args.config is None
            or args.serving_config is None):
        parser.error(f"run requires --config or {COGNITION_CONFIG_ENV} and "
            f"--serving-config or {SERVING_CONFIG_ENV}")
    try:
        if args.command == "record":
            owner = _read_owner_for_experiment(
                cognition_config_path=args.config,
                serving_config_path=args.serving_config)
            _emit(owner.retrieval_adjudication_record(
                cohort_id=args.cohort_id, record_id=args.record_id))
            return 0
        if args.command == "review-pair":
            owner = _read_owner_for_experiment(
                cognition_config_path=args.config,
                serving_config_path=args.serving_config)
            store = DevelopmentalExperimentStore(owner.config.state_root)
            packet = store.build_retrieval_adjudication_packet(args.cohort_id)
            query = next((row for row in packet["queries"]
                if row["question_digest"] == args.question_digest), None)
            if query is None:
                raise ValueError("retrieval_adjudication_question_not_in_cohort")
            record = owner.retrieval_adjudication_record(
                cohort_id=args.cohort_id, record_id=args.record_id)
            concealed_strata = packet.get("schema_version") == (
                "sentientos.developmental_history_retrieval_adjudication_packet:v8")
            review_query = {"question_digest": query["question_digest"],
                "question": query["question"]}
            if not concealed_strata:
                review_query["preregistered_stratum"] = query[
                    "preregistered_stratum"]
            _emit({"schema_version": (
                    "sentientos.developmental_history_retrieval_review_pair:v2"
                    if concealed_strata else
                    "sentientos.developmental_history_retrieval_review_pair:v1"),
                "cohort_id": packet["cohort_id"],
                "adjudication_packet_digest": packet["packet_digest"],
                "adjudication_procedure": packet[
                    "adjudication_procedure"],
                "adjudication_procedure_digest": packet[
                    "adjudication_procedure"]["procedure_digest"],
                "target_model_identity": packet["target_model_identity"],
                "target_model_identity_digest": packet[
                    "target_model_identity_digest"],
                "query": review_query,
                "record": {"record_id": record["record_id"],
                    "record_digest": record["record_digest"],
                    "projection_digest": record["projection_digest"],
                    "record_projection": record["record_projection"]},
                "retrieval_condition_outcomes_included": False,
                "current_truth": False, "authority": False})
            return 0
        if args.command == "freeze":
            owner = _read_owner_for_experiment(
                cognition_config_path=args.config,
                serving_config_path=args.serving_config)
            store = DevelopmentalExperimentStore(owner.config.state_root)
            freeze_id = store.persist_retrieval_corpus_freeze(owner=owner)
            freeze = store.load_retrieval_corpus_freeze(freeze_id)
            _emit({"corpus_freeze_id": freeze_id,
                "freeze_digest": freeze["freeze_digest"],
                "history_state_digest": freeze["history_state_digest"],
                "corpus_manifest_digest": freeze["corpus_manifest_digest"],
                "configured_semantic_embedder_model_id":
                    freeze["configured_semantic_embedder_model_id"],
                "configured_semantic_embedder_revision":
                    freeze["configured_semantic_embedder_revision"],
                "record_count": len(freeze["corpus_manifest"]["records"]),
                "model_invoked": False, "embedder_invoked": False})
            return 0
        if args.command == "run":
            owner = _read_owner_for_experiment(
                cognition_config_path=args.config,
                serving_config_path=args.serving_config)
            store = DevelopmentalExperimentStore(owner.config.state_root)
            cohort_id = store.run_retrieval_comparison_batch(owner=owner,
                query_set_id=args.query_set_id,
                max_input_chars=args.max_input_chars)
            cohort = store.load_retrieval_comparison_cohort(cohort_id)
            _emit({"cohort_id": cohort_id,
                "cohort_digest": cohort["cohort_digest"],
                "query_set_id": cohort["query_set_id"],
                "comparison_count": len(cohort["comparison_artifact_ids"]),
                "max_input_chars": cohort["max_input_chars"],
                "semantic_embedder_identity_digest":
                    cohort["semantic_embedder_identity_digest"],
                "semantic_index_snapshot_digest":
                    cohort["semantic_index_snapshot_digest"],
                "semantic_cache_tick_digest":
                    cohort["semantic_cache_tick_digest"],
                "target_model_identity_bound": (
                    cohort["target_model_identity_digest"] is not None),
                "generative_model_invoked": False,
                "embedder_may_have_been_invoked": (
                    cohort["configured_semantic_embedder_model_id"] is not None)})
            return 0
        store = DevelopmentalExperimentStore(args.state_root)
        if args.command == "packet":
            _emit(store.build_retrieval_adjudication_packet(args.cohort_id))
            return 0
        if args.command == "review-template":
            packet = store.build_retrieval_adjudication_packet(args.cohort_id)
            _emit({"adjudication_packet_digest": packet["packet_digest"],
                "adjudication_procedure_digest": packet[
                    "adjudication_procedure"]["procedure_digest"],
                "submission": build_retrieval_reviewer_template(packet=packet,
                    reviewer_digest=args.reviewer_digest)})
            return 0
        if args.command == "consensus-template":
            packet = store.build_retrieval_adjudication_packet(args.cohort_id)
            _emit({"adjudication_packet_digest": packet["packet_digest"],
                "adjudication_procedure_digest": packet[
                    "adjudication_procedure"]["procedure_digest"],
                "annotations": build_retrieval_consensus_template(
                    packet=packet)})
            return 0
        if args.command == "assemble-reviews":
            packet = store.build_retrieval_adjudication_packet(args.cohort_id)
            cohort = store.load_retrieval_comparison_cohort(args.cohort_id)
            query_set = store.load_retrieval_query_set(cohort["query_set_id"])
            packet_digest = packet["packet_digest"]
            procedure_digest = packet[
                "adjudication_procedure"]["procedure_digest"]
            consensus_file = _read_json_object(args.consensus,
                error_prefix="consensus_template")
            reviewer_files = [_read_json_object(path,
                error_prefix="reviewer_template") for path in (
                    args.reviewer_a, args.reviewer_b)]
            if (set(consensus_file) != {"adjudication_packet_digest",
                    "adjudication_procedure_digest", "annotations"}
                    or consensus_file.get("adjudication_packet_digest") !=
                        packet_digest
                    or consensus_file.get("adjudication_procedure_digest") !=
                        procedure_digest
                    or any(set(item) != {"adjudication_packet_digest",
                        "adjudication_procedure_digest", "submission"}
                        or item.get("adjudication_packet_digest") != packet_digest
                        or item.get("adjudication_procedure_digest") !=
                            procedure_digest
                        or not isinstance(item.get("submission"), Mapping)
                        for item in reviewer_files)):
                raise ValueError("retrieval_review_template_packet_binding_invalid")
            submissions = [item["submission"] for item in reviewer_files]
            if (submissions[0].get("reviewer_digest") ==
                    submissions[1].get("reviewer_digest")):
                raise ValueError("retrieval_independent_reviewer_identity_duplicate")
            # Validate exhaustive ordered labels and consensus consistency
            # without asking reviewers' labels to satisfy hidden strata.
            make_retrieval_relevance_annotations(packet=packet,
                adjudication_procedure_digest=procedure_digest,
                annotations=consensus_file["annotations"],
                independent_reviewers=submissions,
                blind_consensus=True,
                sealed_strata=cohort["strata"],
                sealed_source_experience_digests=cohort.get(
                    "source_experience_digests"),
                sealed_source_record_bindings=isinstance(
                    query_set.get("source_experience_record_ids"), list))
            _emit({"adjudication_packet_digest": packet_digest,
                "adjudication_procedure_digest": procedure_digest,
                "annotations": consensus_file["annotations"],
                "independent_reviewers": [
                    {"adjudication_packet_digest": packet_digest,
                        "adjudication_procedure_digest": procedure_digest,
                        "submission": submission}
                    for submission in submissions],
                "blind_consensus": True})
            return 0
        if args.command == "seal-annotations":
            reviews = _read_json_object(args.reviews,
                error_prefix="independent_reviews")
            if set(reviews) != {"adjudication_packet_digest",
                    "adjudication_procedure_digest", "annotations",
                    "independent_reviewers", "blind_consensus"}:
                raise ValueError("independent_reviews_shape_invalid")
            packet = store.build_retrieval_adjudication_packet(args.cohort_id)
            cohort = store.load_retrieval_comparison_cohort(args.cohort_id)
            query_set = store.load_retrieval_query_set(cohort["query_set_id"])
            procedure_digest = packet[
                "adjudication_procedure"]["procedure_digest"]
            if (reviews.get("adjudication_packet_digest") !=
                    packet["packet_digest"]
                    or reviews.get("adjudication_procedure_digest") !=
                        procedure_digest):
                raise ValueError("independent_reviews_packet_binding_invalid")
            wrapped_reviewers = reviews["independent_reviewers"]
            if (not isinstance(wrapped_reviewers, list)
                    or len(wrapped_reviewers) != 2
                    or any(not isinstance(item, Mapping)
                        or set(item) != {"adjudication_packet_digest",
                            "adjudication_procedure_digest", "submission"}
                        or item.get("adjudication_packet_digest") !=
                            packet["packet_digest"]
                        or item.get("adjudication_procedure_digest") !=
                            procedure_digest
                        or not isinstance(item.get("submission"), Mapping)
                        for item in wrapped_reviewers)):
                raise ValueError("independent_reviewer_packet_binding_invalid")
            sealed = make_retrieval_relevance_annotations(packet=packet,
                adjudication_procedure_digest=procedure_digest,
                annotations=reviews["annotations"],
                independent_reviewers=[item["submission"]
                    for item in wrapped_reviewers],
                blind_consensus=reviews["blind_consensus"],
                sealed_strata=cohort["strata"],
                sealed_source_experience_digests=cohort.get(
                    "source_experience_digests"),
                sealed_source_record_bindings=isinstance(
                    query_set.get("source_experience_record_ids"), list))
            _emit(sealed)
            return 0
        if args.command == "queries":
            query_set = _read_json_object(args.query_set,
                error_prefix="query_set")
            has_source_digests = "source_experience_digests" in query_set
            has_source_record_ids = "source_experience_record_ids" in query_set
            if (set(query_set) - {"questions", "strata",
                    "source_experience_digests",
                    "source_experience_record_ids",
                    "target_model_identity"}
                    or not {"questions", "strata"}.issubset(query_set)
                    or has_source_digests == has_source_record_ids):
                raise ValueError("query_set_shape_invalid")
            target_identity = query_set.get("target_model_identity")
            if target_identity is not None and not isinstance(target_identity, dict):
                raise ValueError("target_model_identity_object_required")
            query_set_id = store.persist_retrieval_query_set(
                corpus_freeze_id=args.corpus_freeze_id,
                questions=query_set["questions"], strata=query_set["strata"],
                source_experience_digests=query_set.get(
                    "source_experience_digests"),
                source_experience_record_ids=query_set.get(
                    "source_experience_record_ids"),
                max_input_chars=args.max_input_chars,
                target_model_identity=target_identity)
            persisted = store.load_retrieval_query_set(query_set_id)
            _emit({"query_set_id": query_set_id,
                "query_set_digest": persisted["query_set_digest"],
                "corpus_freeze_id": persisted["corpus_freeze_id"],
                "history_state_digest": persisted["history_state_digest"],
                "configured_semantic_embedder_model_id":
                    persisted["configured_semantic_embedder_model_id"],
                "configured_semantic_embedder_revision":
                    persisted["configured_semantic_embedder_revision"],
                "max_input_chars": persisted["max_input_chars"],
                "target_model_identity_digest":
                    persisted["target_model_identity_digest"],
                "question_count": persisted["question_count"],
                "source_experience_record_bindings_preregistered": (
                    "source_experience_record_ids" in persisted),
                "stratum_counts": {stratum: persisted["strata"].count(stratum)
                    for stratum in sorted(set(persisted["strata"]))}})
            return 0
        annotations = _read_json_object(args.annotations,
            error_prefix="annotation")
        artifact_id = store.persist_retrieval_comparison_evaluation(
            cohort_id=args.cohort_id, annotations=annotations)
        artifact = store.load_retrieval_comparison_evaluation(artifact_id)
        evaluation = artifact["evaluation"]
        _emit({"artifact_id": artifact_id,
            "evaluation_schema_version": evaluation["schema_version"],
            "evaluation_digest": evaluation["evaluation_digest"],
            "sampling_assumptions": evaluation["sampling_assumptions"],
            "gate": evaluation["gate"],
            "consensus_resolution": evaluation["consensus_resolution"],
            "strata": evaluation["strata"],
            "effect_established": evaluation["effect_established"],
            "learning_established": evaluation["learning_established"],
            "authority": evaluation["authority"]})
        return 0
    except (DevelopmentalHistoryInterventionError, OSError, TypeError,
            ValueError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
