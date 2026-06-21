from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

DOCTRINE_MAP_ID = "codex_beneficial_trait_doctrine_map.v1"

TRAIT_CATALOG: dict[str, str] = {
    "anti_hierarchy_governance": "Keeps authority in reviewable procedure instead of unchecked rank, charisma, or model preference.",
    "bounded_initiative": "Acts within the requested scope and does not invent new authority, gates, side effects, or runtime powers.",
    "constraint_honest_pragmatism": "Names operational constraints and uses feasible evidence without pretending blocked or skipped work is proof.",
    "controlled_exploration": "Permits diagnosis and metadata review while preventing exploratory action from becoming execution authority.",
    "corrigibility": "Keeps failures, stale evidence, and reviewer objections visible so the work can be corrected before landing.",
    "deescalatory_firmness": "Stops unsafe or under-proven landings without expanding conflict, bypassing procedure, or hiding blockers.",
    "dense_usefulness": "Compresses scattered landing evidence into reviewer-usable summaries without replacing the underlying proof.",
    "downside_aware_planning": "Plans around known failure modes, stale artifacts, timeout risk, and authority-boundary hazards.",
    "human_protective_helpfulness": "Preserves operator and reviewer control by making evidence legible while refusing autonomous privilege escalation.",
    "metacognitive_transparency": "Makes what is known, unknown, inferred, stale, or diagnostic explicit in machine-readable and reviewer-readable form.",
    "option_preserving_patience": "Favors recoverable states, cleanup, reruns, and human review over irreversible or premature landing actions.",
    "power_asymmetry_awareness": "Recognizes that automation can overclaim authority and therefore constrains outputs to evidence and doctrine.",
    "situational_attunement": "Adapts explanations to the landing context, distinguishing focused tests, matrix proof, finalizer readiness, and metadata.",
    "truthfulness": "Requires claims to match executed proof, artifact freshness, and explicit diagnostic status.",
    "universalizable_fairness": "Uses stable, deterministic rubrics that reviewers can apply consistently across work items.",
}

NON_AUTHORITY_POSTURE: dict[str, bool] = {
    "doctrine_map_is_read_only": True,
    "doctrine_map_does_not_rerun_commands": True,
    "doctrine_map_does_not_decide_readiness": True,
    "doctrine_map_does_not_bypass_finalizer": True,
    "doctrine_map_does_not_bypass_pr_metadata_guard": True,
    "doctrine_map_does_not_authorize_commit": True,
    "doctrine_map_does_not_authorize_pr_creation": True,
    "doctrine_map_does_not_authorize_runtime_action": True,
    "doctrine_map_does_not_train_or_modify_models": True,
}


def _rail(
    rail_id: str,
    rail_name: str,
    file_paths: list[str],
    enforced_traits: list[str],
    evidence_artifacts: list[str],
    prevented_failure_modes: list[str],
    reviewer_summary: str,
) -> dict[str, Any]:
    return {
        "rail_id": rail_id,
        "rail_name": rail_name,
        "file_paths": file_paths,
        "enforced_traits": enforced_traits,
        "evidence_artifacts": evidence_artifacts,
        "prevented_failure_modes": prevented_failure_modes,
        "non_authority_boundary": "This mapping is descriptive static doctrine only; it does not execute the rail, inspect live evidence, decide readiness, or grant landing authority.",
        "why_this_is_not_authority": "The rail keeps its original authority semantics. This doctrine map only labels the behavioral posture reviewers can expect from that existing rail.",
        "reviewer_summary": reviewer_summary,
    }


RAIL_MAPPINGS: list[dict[str, Any]] = [
    _rail(
        "run_tests_focused_proof_hardening",
        "Focused and targeted proof hardening",
        ["scripts/run_tests.py"],
        ["truthfulness", "constraint_honest_pragmatism", "metacognitive_transparency", "corrigibility"],
        ["focused test command output", "test provenance metadata"],
        ["claiming selected tests passed when none executed", "treating skipped or unselected tests as proof"],
        "Hardens focused proof so test claims stay tied to executed tests rather than optimistic summaries.",
    ),
    _rail(
        "work_item_review_packet_matrix_classification",
        "Work-item review packet matrix proof and diagnostic classification",
        ["scripts/run_work_item_review_packet_matrix.py"],
        ["truthfulness", "downside_aware_planning", "controlled_exploration", "universalizable_fairness"],
        ["work item review packet matrix JSON", "lane classification summaries"],
        ["counting diagnostic lanes as required proof", "hiding blocked or nonproof lanes", "weakening timed-out lanes into success"],
        "Separates required proof from diagnostics so reviewers can compare lanes consistently.",
    ),
    _rail(
        "codex_finalize_landing_readiness",
        "Finalizer readiness and stale-evidence refresh handling",
        ["scripts/codex_finalize_landing.py"],
        ["corrigibility", "option_preserving_patience", "downside_aware_planning", "deescalatory_firmness"],
        ["pre-commit finalizer JSON", "pr-metadata finalizer JSON", "stale-evidence refresh status"],
        ["committing with stale evidence", "creating PR metadata before required finalizer readiness", "ignoring generated-artifact cleanup blockers"],
        "Keeps landing decisions tied to explicit finalizer phases and refresh state.",
    ),
    _rail(
        "codex_pr_metadata_guard",
        "PR metadata guard",
        ["scripts/codex_pr_metadata_guard.py"],
        ["bounded_initiative", "truthfulness", "anti_hierarchy_governance", "power_asymmetry_awareness"],
        ["PR metadata guard JSON", "finalizer and matrix cross-check references"],
        ["calling PR metadata without guard readiness", "using a commit title outside the intended landing contract"],
        "Prevents PR metadata from outrunning the finalizer, matrix, and title contract.",
    ),
    _rail(
        "codex_task_lifecycle_summary",
        "Codex task lifecycle summary",
        ["sentientos/codex_task_lifecycle_summary.py"],
        ["metacognitive_transparency", "dense_usefulness", "situational_attunement"],
        ["task lifecycle summary JSON"],
        ["scattered lifecycle evidence", "reviewers missing phase transitions or unresolved blockers"],
        "Summarizes task lifecycle posture without replacing phase-specific proof.",
    ),
    _rail(
        "codex_lifecycle_doctor",
        "Codex lifecycle doctor",
        ["sentientos/codex_lifecycle_doctor.py"],
        ["corrigibility", "metacognitive_transparency", "human_protective_helpfulness", "option_preserving_patience"],
        ["lifecycle doctor report JSON"],
        ["unclear next safe action", "missing evidence hidden from reviewers", "premature irreversible action"],
        "Diagnoses available landing evidence and names safe next actions while remaining non-authoritative.",
    ),
    _rail(
        "codex_landing_evidence_index",
        "Codex landing evidence index",
        ["sentientos/codex_landing_evidence_index.py"],
        ["dense_usefulness", "truthfulness", "metacognitive_transparency", "universalizable_fairness"],
        ["landing evidence index JSON", "artifact digest and presence hints"],
        ["losing artifact paths", "reviewing stale or missing evidence without visibility", "non-deterministic evidence inventory"],
        "Indexes evidence artifacts so reviewers can see what exists, what is missing, and what each artifact claims.",
    ),
    _rail(
        "codex_landing_evidence_appendix",
        "Codex landing evidence appendix",
        ["sentientos/codex_landing_evidence_appendix.py"],
        ["dense_usefulness", "human_protective_helpfulness", "constraint_honest_pragmatism", "situational_attunement"],
        ["landing evidence appendix markdown", "appendix metadata JSON"],
        ["forcing reviewers to reconstruct evidence manually", "mistaking rendered summaries for readiness authority"],
        "Renders evidence into compact reviewer-readable markdown while repeating non-authority boundaries.",
    ),
    _rail(
        "codex_validation_and_landing_contract",
        "Validation and landing contract",
        ["docs/development/codex_validation_and_landing_contract.md"],
        ["bounded_initiative", "downside_aware_planning", "constraint_honest_pragmatism", "deescalatory_firmness"],
        ["documented validation contract", "required lane expectations"],
        ["declaring done before required validation", "bypassing matrix or supervisor obligations", "treating partial proof as landing proof"],
        "Documents the validation posture that keeps completion claims bounded by required evidence.",
    ),
    _rail(
        "codex_landing_evidence_recovery_rail",
        "Landing evidence recovery rail",
        ["docs/development/codex_landing_evidence_recovery_rail.md"],
        ["option_preserving_patience", "corrigibility", "controlled_exploration", "human_protective_helpfulness"],
        ["recovery rail documentation", "recovery evidence references"],
        ["losing recoverable task-owned files", "rerunning instead of surgical recovery", "closing failed work without recovery artifacts"],
        "Explains how to preserve recovery options and avoid destructive recovery behavior.",
    ),
]


def _validate_trait_references() -> None:
    known = set(TRAIT_CATALOG)
    for rail in RAIL_MAPPINGS:
        unknown = sorted(set(rail["enforced_traits"]) - known)
        if unknown:
            raise ValueError(f"unknown_trait_reference:{rail['rail_id']}:{','.join(unknown)}")


def _trait_to_rails_index() -> dict[str, list[str]]:
    index: dict[str, list[str]] = {trait_id: [] for trait_id in sorted(TRAIT_CATALOG)}
    for rail in RAIL_MAPPINGS:
        for trait_id in rail["enforced_traits"]:
            index[trait_id].append(rail["rail_id"])
    return {trait_id: sorted(rail_ids) for trait_id, rail_ids in index.items()}


def _rail_to_traits_index() -> dict[str, list[str]]:
    return {rail["rail_id"]: list(rail["enforced_traits"]) for rail in RAIL_MAPPINGS}


def build_beneficial_trait_doctrine_map() -> dict[str, Any]:
    """Return the deterministic metadata-only Codex beneficial-trait doctrine map."""
    _validate_trait_references()
    return {
        "doctrine_map_id": DOCTRINE_MAP_ID,
        "metadata_only": True,
        "developer_workflow_evidence_only": True,
        "doctrine_only": True,
        "not_model_training": True,
        "not_reinforcement_learning": True,
        "trait_catalog": dict(sorted(TRAIT_CATALOG.items())),
        "rail_mappings": sorted((dict(rail) for rail in RAIL_MAPPINGS), key=lambda rail: rail["rail_id"]),
        "trait_to_rails_index": _trait_to_rails_index(),
        "rail_to_traits_index": _rail_to_traits_index(),
        "non_authority_posture": dict(sorted(NON_AUTHORITY_POSTURE.items())),
    }


def render_beneficial_trait_doctrine_markdown(doctrine_map: Mapping[str, Any] | None = None) -> str:
    doctrine = doctrine_map or build_beneficial_trait_doctrine_map()
    lines = [
        "# Codex Beneficial Trait Doctrine Map",
        "",
        "This is external governance doctrine for existing Codex/SentientOS landing rails. It is not model training, reinforcement learning, readiness authority, or a new gate.",
        "",
        "## Trait catalog",
        "| trait_id | definition |",
        "| --- | --- |",
    ]
    for trait_id, definition in doctrine["trait_catalog"].items():
        lines.append(f"| {trait_id} | {definition} |")
    lines.extend(["", "## Rail-to-trait mapping", "| rail_id | rail_name | enforced_traits |", "| --- | --- | --- |"])
    for rail in doctrine["rail_mappings"]:
        lines.append(f"| {rail['rail_id']} | {rail['rail_name']} | {', '.join(rail['enforced_traits'])} |")
    lines.extend(["", "## Trait-to-rails index", "| trait_id | rails |", "| --- | --- |"])
    for trait_id, rail_ids in doctrine["trait_to_rails_index"].items():
        lines.append(f"| {trait_id} | {', '.join(rail_ids) if rail_ids else 'none'} |")
    lines.extend(["", "## Non-authority posture"])
    for key, value in doctrine["non_authority_posture"].items():
        lines.append(f"- **{key}:** {'true' if value else 'false'}")
    lines.append("")
    return "\n".join(lines)


def write_beneficial_trait_doctrine_json(doctrine_map: Mapping[str, Any], output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(doctrine_map, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_beneficial_trait_doctrine_markdown(markdown: str, output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(markdown, encoding="utf-8")
