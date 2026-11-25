"""Global-union adapters for the ordinary-chat history retrieval policy."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .resident_developmental_cognition import (
    ORDINARY_CHAT_HISTORY_RETRIEVAL_POLICY_ID,
    SEMANTIC_HISTORY_MIN_COSINE_SIMILARITY,
    _HISTORY_DECISION_NEGATION_TERMS,
    _HISTORY_DECISION_PREDICATE_TERMS,
    _digest,
    _history_context_packet,
    _ordinary_chat_history_instruction,
    _ordinary_chat_history_search_document,
    cognition_query_terms,
)
from .local_model_authority import digest_payload
from . import resident_developmental_cognition as _resident


def project_federated_candidate_record(record: Mapping[str, Any]
        ) -> Mapping[str, Any]:
    """Keep the admitted candidate semantics needed by the shared selector."""
    candidate = record.get("candidate")
    created_at = record.get("created_at")
    epistemic_posture = record.get("epistemic_posture")
    if not isinstance(candidate, Mapping) or not isinstance(created_at, str):
        raise ValueError("federated_history_candidate_missing")
    return {"candidate": dict(candidate), "created_at": created_at,
        "epistemic_posture": epistemic_posture}


def make_federated_ordinary_chat_selectors(*, query_set: Mapping[str, Any],
        semantic_model_id: str | None, semantic_model_revision: str | None,
        target_model_identity: Mapping[str, Any] | None = None
        ) -> dict[str, Any]:
    """Build global selectors using the ordinary-chat document and rank rules.

    The bounded older-history sampler is seeded by the frozen query-set
    identity. Semantic embeddings retain the production CPU identity check.
    This adapter has no cache side effects, so the comparison measures the
    current source-bound corpus and query only.
    """
    query_set_digest = query_set.get("query_set_digest")
    frozen_target_identity = query_set.get("target_model_identity")
    frozen_target_identity_digest = query_set.get("target_model_identity_digest")
    supplied_target_identity_digest = (None if target_model_identity is None else
        "sha256:" + digest_payload(dict(target_model_identity)))
    if (not isinstance(query_set_digest, str)
            or len(query_set_digest) != 71
            or not query_set_digest.startswith("sha256:")
            or target_model_identity != frozen_target_identity
            or supplied_target_identity_digest != frozen_target_identity_digest
            or (semantic_model_id is not None and
                (not isinstance(semantic_model_id, str) or not semantic_model_id))
            or (semantic_model_revision is not None and
                (not isinstance(semantic_model_revision, str)
                    or not semantic_model_revision))
            or ((semantic_model_id is None) !=
                (semantic_model_revision is None))):
        raise ValueError("federated_ordinary_chat_selector_config_invalid")

    expected_identity = (None if semantic_model_id is None else {
        "schema_version": "sentientos.semantic_embedder_identity:v1",
        "provider": "sentence-transformers", "model_id": semantic_model_id,
        "revision": semantic_model_revision, "device": "cpu"})
    expected_identity_raw_digest = (None if expected_identity is None else
        hashlib.sha256(json.dumps(expected_identity, sort_keys=True,
            separators=(",", ":")).encode("utf-8")).hexdigest())
    expected_identity_digest = (None if expected_identity_raw_digest is None else
        "sha256:" + expected_identity_raw_digest)

    def score(question: str, candidates: Sequence[Mapping[str, Any]],
            max_selected_records: int, max_input_chars: int,
            retrieval_policy_id: str, *, semantic_scores: Mapping[Any, float]
            ) -> list[Mapping[str, str]]:
        candidates = tuple(sorted(candidates, key=lambda row: (
            row["record_projection"]["created_at"], row["source_id"],
            row["record_id"])))
        terms = cognition_query_terms(question)
        keys = [(row["source_id"], row["record_id"]) for row in candidates]
        weights: dict[Any, dict[str, int]] = {}
        correction_targets: dict[Any, set[tuple[str, str, str, str]]] = {}
        for key, row in zip(keys, candidates):
            projection = row.get("record_projection")
            candidate = projection.get("candidate") if isinstance(
                projection, Mapping) else None
            if not isinstance(candidate, Mapping):
                raise ValueError("federated_ordinary_chat_candidate_projection_invalid")
            row_weights, _, targets = _ordinary_chat_history_search_document(
                candidate=candidate, target_model_identity=target_model_identity)
            weights[key] = row_weights
            if targets:
                # Include source identity because local conversation IDs may
                # repeat across independently admitted owners.
                correction_targets[key] = {(key[0], *target) for target in targets}
        document_frequency = {term: sum(term in row_weights
                for row_weights in weights.values()) for term in terms}
        query_decision_polarity = bool(terms & _HISTORY_DECISION_PREDICATE_TERMS)
        query_is_negative_decision = bool(terms & _HISTORY_DECISION_NEGATION_TERMS)
        ranked = []
        for order, key in enumerate(keys):
            row_weights = weights[key]
            shared = terms & row_weights.keys()
            relevance_score = sum(row_weights[term] *
                (math.log((max(1, len(weights)) + 1) /
                    (document_frequency[term] + 0.5)) + 1) ** 2
                for term in sorted(shared))
            record_mentions_decision = bool(
                row_weights.keys() & _HISTORY_DECISION_PREDICATE_TERMS)
            if relevance_score or key in semantic_scores:
                record_is_negative_decision = (
                    record_mentions_decision and bool(
                        row_weights.keys() & _HISTORY_DECISION_NEGATION_TERMS))
                polarity_match = int(not query_decision_polarity or
                    (not record_mentions_decision and not query_is_negative_decision)
                    or query_is_negative_decision == record_is_negative_decision)
                ranked.append((polarity_match, relevance_score,
                    semantic_scores.get(key, 0.0), order, key))
        ranked.sort(reverse=True)

        parent = {key: key for key in keys}
        def find(key: Any) -> Any:
            root = key
            while parent[root] != root:
                root = parent[root]
            while parent[key] != key:
                next_key = parent[key]
                parent[key] = root
                key = next_key
            return root
        def join(first: Any, second: Any) -> None:
            first_root, second_root = find(first), find(second)
            if first_root != second_root:
                parent[second_root] = first_root

        records_by_target: dict[tuple[str, str, str, str], list[Any]] = {}
        for key, targets in correction_targets.items():
            for target in targets:
                records_by_target.setdefault(target, []).append(key)
        for target_keys in records_by_target.values():
            for key in target_keys[1:]:
                join(target_keys[0], key)
        unit_members: dict[Any, list[Any]] = {}
        for key in keys:
            unit_members.setdefault(find(key), []).append(key)
        score_by_key = {row[4]: row[1] for row in ranked}
        semantic_by_key = {row[4]: row[2] for row in ranked}
        polarity_by_key = {row[4]: row[0] for row in ranked}
        units = []
        for members in unit_members.values():
            relevance = max((score_by_key.get(key, 0.0) for key in members),
                default=0.0)
            semantic_score = max((semantic_by_key.get(key, 0.0)
                for key in members), default=0.0)
            polarity = max((polarity_by_key.get(key, 0) for key in members),
                default=0)
            newest = max(keys.index(key) for key in members)
            if relevance > 0 or any(key in semantic_scores for key in members):
                units.append((polarity, relevance, semantic_score, newest, members))
        units.sort(key=lambda row: row[:4], reverse=True)
        selected: list[Any] = []
        selected_set: set[Any] = set()
        for _polarity, _relevance, _semantic, _newest, members in units:
            if len(selected) + len(members) > max_selected_records:
                continue
            selected.extend(members)
            selected_set.update(members)
        recent_units = sorted(unit_members.values(),
            key=lambda members: max(keys.index(key) for key in members),
            reverse=True)
        for members in recent_units:
            if len(selected) >= max_selected_records:
                break
            if any(key in selected_set for key in members):
                continue
            if len(selected) + len(members) > max_selected_records:
                continue
            selected.extend(members)
            selected_set.update(members)
        # Production emits least-to-most relevant as a complete suffix so
        # downstream input-budget truncation retains the strongest records.
        selected.sort(key=lambda key: (polarity_by_key.get(key, 0),
            score_by_key.get(key, 0.0), semantic_by_key.get(key, 0.0),
            keys.index(key)))
        ref_by_key = {(row["source_id"], row["record_id"]): row
            for row in candidates}
        ranked_refs = [{"source_id": ref_by_key[key]["source_id"],
            "record_id": ref_by_key[key]["record_id"],
            "record_digest": ref_by_key[key]["record_digest"]}
            for key in selected]
        target_identity_digest = (hashlib.sha256(json.dumps(
            dict(target_model_identity), sort_keys=True, separators=(",", ":"),
            ensure_ascii=False).encode("utf-8")).hexdigest()
            if isinstance(target_model_identity, Mapping)
                and target_model_identity else None)
        records_by_key = {(row["source_id"], row["record_id"]): row
            for row in candidates}
        for count in range(len(ranked_refs), 0, -1):
            selected_refs = ranked_refs[:count]
            packets = []
            for ref in selected_refs:
                row = records_by_key[(ref["source_id"], ref["record_id"])]
                projection = row["record_projection"]
                record = {"record_id": row["record_id"],
                    "record_digest": row["record_digest"],
                    "created_at": projection["created_at"],
                    "epistemic_posture": projection["epistemic_posture"],
                    "candidate": projection["candidate"]}
                packet = _history_context_packet(record,
                    include_source_evidence_context=False,
                    compact_for_input_budget=True,
                    omit_historical_embodiment_details=True,
                    relevance_query=question,
                    target_model_identity=target_model_identity)
                packet["source_id"] = ref["source_id"]
                packet["source_qualified_record_digest"] = ref["record_digest"]
                packets.append(packet)
            selection = {"schema_version":
                    "sentientos.ordinary_chat_developmental_history_selection:v3",
                "policy": "federated_global_question_ranked_prefix:v1",
                "retrieval_policy_id": retrieval_policy_id,
                "target_model_identity_digest": target_identity_digest,
                "history_state_digest": query_set[
                    "federated_manifest_digest"],
                "available_records": ranked_refs,
                "selected_records": selected_refs,
                "omitted_records": ranked_refs[count:],
                "omitted_records_digest": _digest(ranked_refs[count:]),
                "omission_reason": "ordinary_prompt_budget"
                    if count < len(ranked_refs) else None}
            selection["selection_digest"] = digest_payload(selection)
            context = {"schema_version":
                    "sentientos.ordinary_chat_developmental_history_context:v1",
                "instruction": (_ordinary_chat_history_instruction() +
                    " Federated records can reuse local record IDs across sources; "
                    "cite the containing source_id and record_id together."),
                "developmental_history": packets, "selection": selection,
                "historical_only": True, "current_truth": False,
                "authority": False, "mutation_performed": False}
            encoded = json.dumps(context, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"))
            if len(encoded) <= max_input_chars:
                return selected_refs
        return []

    def lexical_selector(question: str, candidates: Sequence[Mapping[str, Any]],
            max_selected_records: int, max_input_chars: int
            ) -> Sequence[Mapping[str, str]]:
        policy = lexical_policy_id + ":max_selected_records:" + str(
            max_selected_records)
        return score(question, candidates, max_selected_records,
            max_input_chars, policy, semantic_scores={})

    def semantic_selector(question: str, candidates: Sequence[Mapping[str, Any]],
            max_selected_records: int, max_input_chars: int
            ) -> Sequence[Mapping[str, str]] | None:
        if expected_identity is None:
            return None
        candidates = tuple(sorted(candidates, key=lambda row: (
            row["record_projection"]["created_at"], row["source_id"],
            row["record_id"])))
        terms = cognition_query_terms(question)
        recent = list(reversed(candidates[-192:]))
        older = list(candidates[:-192])
        older_lexical = [row for row in reversed(older)
            if (projection := row.get("record_projection"))
            and isinstance(projection, Mapping)
            and isinstance((candidate := projection.get("candidate")), Mapping)
            and (terms & _ordinary_chat_history_search_document(
                candidate=candidate, target_model_identity=target_model_identity)[0].keys())][:32]
        older_lexical_keys = {(row["source_id"], row["record_id"])
            for row in older_lexical}
        older_pool = [row for row in older if (row["source_id"], row["record_id"])
            not in older_lexical_keys]
        sample_count = min(64 - len(older_lexical), len(older_pool))
        question_text = question
        phase_seed = int.from_bytes(hashlib.sha256(json.dumps([
            question_text[:4000], "federated:" + query_set_digest],
            ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            ).digest()[:8], "big")
        sample_phase = phase_seed % len(older_pool) if older_pool else 0
        sampled = ([older_pool[(sample_phase + ((2 * index + 1)
            * len(older_pool)) // (2 * sample_count)) % len(older_pool)]
            for index in range(sample_count)] if sample_count else [])
        semantic_candidates = list(dict.fromkeys(
            (row["source_id"], row["record_id"]) for row in
            recent + older_lexical + sampled))
        row_by_key = {(row["source_id"], row["record_id"]): row
            for row in candidates}
        texts = []
        for key in semantic_candidates:
            candidate = row_by_key[key]["record_projection"].get("candidate")
            if not isinstance(candidate, Mapping):
                raise ValueError("federated_ordinary_chat_candidate_projection_invalid")
            _, text, _ = _ordinary_chat_history_search_document(
                candidate=candidate, target_model_identity=target_model_identity)
            texts.append(text)
        included = [(key, text) for key, text in zip(semantic_candidates, texts)
            if text.strip()]
        if not included:
            return None
        try:
            from semantic_embeddings import encode_semantic
            embedded = encode_semantic([question_text[:4000]] +
                [text for _, text in included], model_id=semantic_model_id,
                revision=semantic_model_revision)
        except Exception:
            return None
        if (embedded is None or not isinstance(embedded.identity, Mapping)
                or dict(embedded.identity) != expected_identity
                or embedded.identity_digest != expected_identity_raw_digest
                or len(embedded.vectors) != len(included) + 1):
            return None
        query_vector = embedded.vectors[0]
        semantic_scores = {}
        for (key, _), vector in zip(included, embedded.vectors[1:]):
            similarity = sum(a * b for a, b in zip(query_vector, vector))
            if similarity >= SEMANTIC_HISTORY_MIN_COSINE_SIMILARITY:
                semantic_scores[key] = similarity
        return score(question, candidates, max_selected_records,
            max_input_chars, semantic_policy_id +
                ":max_selected_records:" + str(max_selected_records),
            semantic_scores=semantic_scores)

    package_root = Path(_resident.__file__).parent
    implementation_sources = (Path(__file__), Path(_resident.__file__),
        package_root / "federated_history_source_manifest.py",
        Path(__file__).resolve().parents[1] / "semantic_embeddings.py",
        package_root / "cognition_retrieval.py")
    source_bodies = [source.read_bytes() for source in implementation_sources]
    source_digest = hashlib.sha256(b"".join(
        len(body).to_bytes(8, "big") + body for body in source_bodies
    )).hexdigest()
    lexical_policy_id = ORDINARY_CHAT_HISTORY_RETRIEVAL_POLICY_ID + ":federated_global:v1"
    semantic_policy_id = ("ordinary_chat_global_semantic_rank:v1:" +
        (expected_identity_digest or "unavailable"))
    return {"lexical_selector": lexical_selector,
        "semantic_selector": semantic_selector,
        "lexical_policy_id": lexical_policy_id,
        "semantic_policy_id": semantic_policy_id,
        "retrieval_implementation_digest": "sha256:" + source_digest,
        "semantic_embedder_identity_digest": expected_identity_digest}


def run_federated_ordinary_chat_comparison(*, manifest: Mapping[str, Any],
        query_set: Mapping[str, Any], resolver: Any,
        semantic_model_id: str | None, semantic_model_revision: str | None,
        target_model_identity: Mapping[str, Any] | None = None,
        max_selected_records: int = 8) -> dict[str, Any]:
    """Execute the frozen federated query set with production ordinary-chat selectors."""
    from .federated_history_source_manifest import (
        run_federated_retrieval_comparison,
    )
    selectors = make_federated_ordinary_chat_selectors(
        query_set=query_set, semantic_model_id=semantic_model_id,
        semantic_model_revision=semantic_model_revision,
        target_model_identity=target_model_identity)
    selectors["lexical_policy_id"] += (
        f":max_selected_records:{max_selected_records}")
    selectors["semantic_policy_id"] += (
        f":max_selected_records:{max_selected_records}")
    return run_federated_retrieval_comparison(manifest=manifest,
        query_set=query_set, resolver=resolver,
        max_selected_records=max_selected_records,
        **selectors)
