"""Codex Spec Amendment and Regeneration engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

import json

from sentientos.codex_startup_guard import enforce_codex_startup


# Boundary assertion:
# This module records specification amendments and routes them for review; it does not generate policies, goals, or incentives autonomously.
# All changes require external proposals and explicit approvals; no learning or optimisation occurs here.
# See: NON_GOALS_AND_FREEZE.md §Governance freeze, NAIR_CONFORMANCE_AUDIT.md §2 (NO_GRADIENT_INVARIANT)


from .integrity_daemon import IntegrityDaemon, IntegrityViolation
from .proof_budget_governor import (
    build_governor_event,
    decide_budget,
    governor_config_from_env,
    load_pressure_state,
    save_pressure_state,
    update_pressure_state,
)
from .proposal_router import (
    CandidateResult,
    choose_candidate,
    maybe_escalate_k,
    promote_candidates,
    rank_stage_a,
    score_evaluation,
    score_evaluation_a,
    top_violation_codes,
)
from privilege_lint.reporting import (
    NarratorLink,
    PrivilegeReport,
    ReviewBoardHook,
    create_default_router,
)


__all__ = [
    "AmendmentProposal",
    "SpecAmender",
    "AmendmentReviewBoard",
    "IntegrityViolation",
    "PrivilegeViolation",
]


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


def _neutralize_expression(text: str) -> str:
    """Remove expressive verbs so review UI shows neutral tone only."""

    normalized = text
    for marker in ("Reinforce", "reinforce", "Tighten", "tighten"):
        normalized = normalized.replace(marker, "Update")
    return normalized


@dataclass
class AmendmentProposal:
    """Structured amendment proposal for an existing spec."""

    proposal_id: str
    spec_id: str
    kind: str
    status: str
    summary: str
    deltas: Dict[str, Any]
    context: Dict[str, Any]
    original_spec: Dict[str, Any]
    proposed_spec: Dict[str, Any]
    created_at: datetime = field(default_factory=_default_now)
    updated_at: datetime = field(default_factory=_default_now)
    ledger_entry: Optional[str] = None
    operator_notes: List[Dict[str, Any]] = field(default_factory=list)
    lineage: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "proposal_id": self.proposal_id,
            "spec_id": self.spec_id,
            "kind": self.kind,
            "status": self.status,
            "summary": self.summary,
            "deltas": self.deltas,
            "context": self.context,
            "original_spec": self.original_spec,
            "proposed_spec": self.proposed_spec,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "ledger_entry": self.ledger_entry,
            "operator_notes": list(self.operator_notes),
        }
        if self.lineage:
            payload["lineage"] = self.lineage
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AmendmentProposal":
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        updated_at = datetime.fromisoformat(str(payload["updated_at"]))
        return cls(
            proposal_id=str(payload["proposal_id"]),
            spec_id=str(payload["spec_id"]),
            kind=str(payload.get("kind", "amendment")),
            status=str(payload.get("status", "pending")),
            summary=str(payload.get("summary", "")),
            deltas=dict(payload.get("deltas") or {}),
            context=dict(payload.get("context") or {}),
            original_spec=dict(payload.get("original_spec") or {}),
            proposed_spec=dict(payload.get("proposed_spec") or {}),
            created_at=created_at,
            updated_at=updated_at,
            ledger_entry=payload.get("ledger_entry"),
            operator_notes=list(payload.get("operator_notes") or []),
            lineage=dict(payload.get("lineage") or {}),
        )

    def add_note(
        self,
        operator: str,
        action: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        entry = {
            "operator": operator,
            "action": action,
            "timestamp": _default_now().isoformat(),
        }
        if metadata:
            entry["metadata"] = dict(metadata)
        self.operator_notes.append(entry)


class PrivilegeViolation(RuntimeError):
    """Raised when privilege lint violations block an amendment."""

    def __init__(self, report: PrivilegeReport) -> None:
        super().__init__("Privilege lint violations detected")
        self.report = report


class SpecAmender:
    """Monitor Codex telemetry and propose spec amendments during startup orchestration."""

    DEFAULT_THRESHOLD = 3

    def __init__(
        self,
        root: Path | str = Path("integration"),
        *,
        now: Callable[[], datetime] = _default_now,
    ) -> None:
        enforce_codex_startup("SpecAmender")
        self._integration_root = Path(root)
        self._integration_root.mkdir(parents=True, exist_ok=True)
        self._spec_root = self._integration_root / "specs"
        self._amendment_root = self._spec_root / "amendments"
        self._pending_dir = self._amendment_root / "pending"
        self._approved_dir = self._amendment_root / "approved"
        self._archive_root = self._amendment_root / "archive"
        self._archive_original_root = self._archive_root / "original_specs"
        self._archive_proposal_root = self._archive_root / "proposals"
        self._rejected_dir = self._integration_root / "rejected_specs"
        for directory in (
            self._spec_root,
            self._amendment_root,
            self._pending_dir,
            self._approved_dir,
            self._archive_root,
            self._archive_original_root,
            self._archive_proposal_root,
            self._rejected_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        self._amendment_log = self._integration_root / "amendment_log.jsonl"
        self._spec_log = self._integration_root / "spec_log.jsonl"
        self._state_path = self._amendment_root / "state.json"
        self._now = now

        self._integrity_daemon = IntegrityDaemon(self._integration_root, now=now)

        self._signals: Dict[str, Dict[str, Any]] = {}
        # Definition anchor:
        # Term: "preference"
        # Frozen meaning: operator-configured weightings influencing selection, not desires or intentions.
        # See: SEMANTIC_GLOSSARY.md#preference
        self._state: Dict[str, Any] = {
            "thresholds": {},
            "preferences": {},
            "signal_history": {},
        }
        self._load_state()

    # ------------------------------------------------------------------
    # Public API
    def record_signal(
        self,
        spec_id: str,
        signal_type: str,
        metadata: Mapping[str, Any],
        *,
        current_spec: Mapping[str, Any],
    ) -> AmendmentProposal | None:
        """Record recurring telemetry and emit amendment proposals when warranted."""

        if self._has_active_amendment(spec_id):
            return None

        bucket = self._signals.setdefault(
            spec_id,
            {"signals": [], "counts": {}, "lineage": {}},
        )
        entry = {
            "kind": signal_type,
            "metadata": dict(metadata),
            "timestamp": self._now().isoformat(),
        }
        bucket["signals"].append(entry)
        bucket["counts"][signal_type] = bucket["counts"].get(signal_type, 0) + 1
        self._state["signal_history"].setdefault(spec_id, []).append(entry)
        self._save_state()

        threshold = int(
            self._state.get("thresholds", {}).get(signal_type, self.DEFAULT_THRESHOLD)
        )
        if bucket["counts"][signal_type] < threshold:
            return None

        proposal = self._draft_amendment(
            spec_id,
            bucket["signals"],
            current_spec,
            dominant_signal=signal_type,
        )
        self._signals.pop(spec_id, None)
        return proposal

    def propose_manual(
        self,
        spec_id: str,
        *,
        summary: str,
        deltas: Mapping[str, Any],
        context: Mapping[str, Any],
        original_spec: Mapping[str, Any],
        proposed_spec: Mapping[str, Any],
        kind: str = "amendment",
        lineage: Mapping[str, Any] | None = None,
    ) -> AmendmentProposal:
        """Persist a pre-computed amendment draft."""

        proposal = self._create_proposal(
            spec_id=spec_id,
            kind=kind,
            summary=summary,
            deltas=dict(deltas),
            context=dict(context),
            original_spec=dict(original_spec),
            proposed_spec=dict(proposed_spec),
            lineage=dict(lineage) if lineage else None,
        )
        return proposal

    def regenerate_spec(
        self,
        spec_id: str,
        *,
        operator: str,
        reason: str,
        current_spec: Mapping[str, Any],
    ) -> AmendmentProposal:
        """Draft a regenerated spec version linked to the previous lineage."""

        current_version = str(current_spec.get("version", "v1"))
        next_version = self._next_version(current_version)
        proposed_spec = dict(current_spec)
        proposed_spec["version"] = next_version
        proposed_spec["status"] = "regenerated"
        summary = f"Regenerate {spec_id} to recover from structural failure"
        deltas = {
            "version": {"before": current_version, "after": next_version},
            "status": {"before": current_spec.get("status"), "after": "regenerated"},
        }
        context = {
            "reason": reason,
            "operator": operator,
        }
        lineage = {
            "from_version": current_version,
            "to_version": next_version,
            "operator": operator,
            "reason": reason,
        }
        proposal = self._create_proposal(
            spec_id=spec_id,
            kind="regeneration",
            summary=summary,
            deltas=deltas,
            context=context,
            original_spec=dict(current_spec),
            proposed_spec=proposed_spec,
            lineage=lineage,
        )
        archive_path = self._archive_original_root / f"{spec_id}_{current_version}.json"
        archive_path.write_text(
            json.dumps(current_spec, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        self._append_spec_log(
            "regenerated",
            spec_id,
            {
                "from_version": current_version,
                "to_version": next_version,
                "proposal_id": proposal.proposal_id,
                "reason": reason,
            },
        )
        proposal.add_note(operator, "regenerated", {"reason": reason})
        self._persist(proposal)
        return proposal

    def load_proposal(self, proposal_id: str) -> AmendmentProposal | None:
        for directory in (
            self._pending_dir,
            self._approved_dir,
            self._rejected_dir,
            self._archive_proposal_root,
        ):
            path = directory / f"{proposal_id}.json"
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
                return AmendmentProposal.from_dict(payload)
        return None

    def list_pending(self) -> List[Dict[str, Any]]:
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(self._pending_dir.glob("*.json"))
        ]

    def active_amendments(self, spec_id: str | None = None) -> List[Dict[str, Any]]:
        items = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(self._approved_dir.glob("*.json"))
        ]
        if spec_id is None:
            return items
        return [item for item in items if item.get("spec_id") == spec_id]

    def dashboard_state(self) -> Dict[str, Any]:
        pending = [json.loads(path.read_text(encoding="utf-8")) for path in self._pending_dir.glob("*.json")]
        approved = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in self._approved_dir.glob("*.json")
        ]
        items: List[Dict[str, Any]] = []
        for payload in pending + approved:
            diff = {
                key: value
                for key, value in payload.get("deltas", {}).items()
            }
            presentation: Dict[str, Any] = {
                "summary": _neutralize_expression(str(payload.get("summary", ""))),
            }
            objective_after = diff.get("objective", {}).get("after")
            if isinstance(objective_after, str):
                presentation["objective_after"] = _neutralize_expression(objective_after)
            items.append(
                {
                    "proposal_id": payload.get("proposal_id"),
                    "spec_id": payload.get("spec_id"),
                    "status": payload.get("status"),
                    "kind": payload.get("kind"),
                    "summary": payload.get("summary"),
                    "diff": diff,
                    "context": payload.get("context", {}),
                    "ledger_entry": payload.get("ledger_entry"),
                    "presentation": presentation,
                }
            )
        return {
            "panel": "Spec Amendments",
            "pending": [item for item in items if item["status"] == "pending"],
            "approved": [item for item in items if item["status"] == "approved"],
            "items": items,
        }

    def integrity_endpoint(self) -> Dict[str, Any]:
        """Expose covenantal health snapshot for other modules."""

        return self._integrity_daemon.health()

    def edit_proposal(
        self,
        proposal_id: str,
        *,
        operator: str,
        summary: str | None = None,
        deltas: Mapping[str, Any] | None = None,
        proposed_spec: Mapping[str, Any] | None = None,
    ) -> AmendmentProposal:
        proposal = self._require(proposal_id)
        changes: Dict[str, Any] = {}
        if summary is not None and summary != proposal.summary:
            proposal.summary = summary
            changes["summary"] = summary
        if deltas is not None:
            new_deltas = dict(deltas)
            if new_deltas != proposal.deltas:
                proposal.deltas = new_deltas
                changes["deltas"] = new_deltas
        if proposed_spec is not None:
            new_spec = dict(proposed_spec)
            if new_spec != proposal.proposed_spec:
                proposal.proposed_spec = new_spec
                changes["proposed_spec"] = new_spec
        if changes:
            proposal.updated_at = self._now()
            proposal.add_note(operator, "edited", {"changes": changes})
            self._persist(proposal)
            self._append_amendment_log(
                "edited",
                proposal.spec_id,
                proposal.proposal_id,
                {"operator": operator, "changes": changes},
            )
        return proposal

    def annotate_lineage(
        self,
        proposal_id: str,
        *,
        lineage: Mapping[str, Any],
        context: Mapping[str, Any] | None = None,
    ) -> AmendmentProposal:
        """Attach lineage metadata to an existing proposal."""

        proposal = self._require(proposal_id)
        merged_lineage = dict(proposal.lineage or {})
        merged_lineage.update(dict(lineage))
        proposal.lineage = merged_lineage

        if context:
            existing_context = dict(proposal.context or {})
            existing_context.update(dict(context))
            proposal.context = existing_context

        stored = self._persist(proposal)
        self._append_amendment_log(
            "annotated",
            proposal.spec_id,
            proposal.proposal_id,
            {"lineage": merged_lineage, "context": dict(context or {})},
        )
        return AmendmentProposal.from_dict(
            json.loads(stored.read_text(encoding="utf-8"))
        )

    # ------------------------------------------------------------------
    # Internal helpers
    def _draft_amendment(
        self,
        spec_id: str,
        signals: Iterable[Mapping[str, Any]],
        current_spec: Mapping[str, Any],
        *,
        dominant_signal: str,
    ) -> AmendmentProposal:
        original = dict(current_spec)
        objective_before = str(original.get("objective", ""))
        directives_before = list(original.get("directives") or [])
        testing_before = list(original.get("testing_requirements") or [])

        descriptions = []
        for entry in signals:
            metadata = entry.get("metadata") or {}
            detail = metadata.get("detail") or metadata.get("reason")
            if detail and detail not in descriptions:
                descriptions.append(str(detail))
        if not descriptions:
            descriptions.append(f"recurring {dominant_signal} signals")

        preferences = self._state.get("preferences", {}).get(dominant_signal, {})
        approved = int(preferences.get("approved", 0))
        rejected = int(preferences.get("rejected", 0))
        verb = "Reinforce" if approved > rejected else "Tighten"

        new_objective = (
            f"{verb} {objective_before or 'the existing objective'} to cover {dominant_signal} gaps."
        )
        added_directives = [
            f"Document remediation for {dominant_signal} contexts: {', '.join(descriptions)}.",
            "Add coverage analysis checkpoints before activation to prevent silent drift.",
        ]
        added_testing = [
            f"Replay {dominant_signal} telemetry until amendment clears the recurrence queue.",
            "Ensure ledger approval is required before the amendment becomes active.",
        ]

        proposed = dict(original)
        proposed["objective"] = new_objective
        proposed["directives"] = directives_before + added_directives
        proposed["testing_requirements"] = testing_before + added_testing

        deltas = {
            "objective": {"before": objective_before, "after": new_objective},
            "directives": {
                "before": directives_before,
                "added": added_directives,
            },
            "testing_requirements": {
                "before": testing_before,
                "added": added_testing,
            },
        }
        context = {
            "signals": list(signals),
            "counts": self._aggregate_counts(signals),
            "dominant_signal": dominant_signal,
        }

        summary = f"Amend {spec_id} for {dominant_signal} coverage gaps"
        proposal = self._create_proposal(
            spec_id=spec_id,
            kind="amendment",
            summary=summary,
            deltas=deltas,
            context=context,
            original_spec=original,
            proposed_spec=proposed,
            lineage=None,
        )
        return proposal

    def _aggregate_counts(self, signals: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for entry in signals:
            kind = str(entry.get("kind"))
            counts[kind] = counts.get(kind, 0) + 1
        return counts

    def _draft_amendment_variants(
        self,
        *,
        spec_id: str,
        kind: str,
        summary: str,
        deltas: Mapping[str, Any],
        context: Mapping[str, Any],
        original_spec: Mapping[str, Any],
        proposed_spec: Mapping[str, Any],
        lineage: Mapping[str, Any] | None,
        k: int,
        seed: str,
    ) -> list[AmendmentProposal]:
        count = max(int(k), 1)
        base_directives = list((proposed_spec or {}).get("directives") or [])
        base_testing = list((proposed_spec or {}).get("testing_requirements") or [])
        variants: list[AmendmentProposal] = []
        seen: set[str] = set()
        for idx in range(count * 5):
            directives = list(base_directives)
            testing = list(base_testing)
            if directives:
                shift = idx % len(directives)
                directives = directives[shift:] + directives[:shift]
            if testing:
                shift_t = (idx // 2) % len(testing)
                testing = testing[shift_t:] + testing[:shift_t]

            variant_spec = dict(proposed_spec)
            if directives:
                variant_spec["directives"] = directives
            if testing:
                variant_spec["testing_requirements"] = testing
            lineage_payload = dict(variant_spec.get("lineage") or {})
            lineage_payload["router_variant"] = f"{idx + 1:02d}"
            if lineage_payload:
                variant_spec["lineage"] = lineage_payload
            option = idx % 3
            if option == 1:
                variant_summary = f"{summary} [candidate {idx + 1}]"
            elif option == 2:
                variant_summary = f"[candidate {idx + 1}] {summary}"
            else:
                variant_summary = summary

            signature = json.dumps(
                {
                    "summary": variant_summary,
                    "proposed_spec": variant_spec,
                    "deltas": dict(deltas),
                },
                sort_keys=True,
            )
            if signature in seen:
                continue
            seen.add(signature)

            proposal_hash = hashlib.sha256(f"{seed}:{idx}".encode("utf-8")).hexdigest()[:8]
            proposal = AmendmentProposal(
                proposal_id=f"{spec_id}-{proposal_hash}-V{len(variants) + 1}",
                spec_id=spec_id,
                kind=kind,
                status="pending",
                summary=variant_summary,
                deltas=dict(deltas),
                context=dict(context),
                original_spec=dict(original_spec),
                proposed_spec=variant_spec,
                created_at=self._now(),
                updated_at=self._now(),
                lineage=dict(lineage) if lineage else None,
            )
            variants.append(proposal)
            if len(variants) >= count:
                break
        if len(variants) < count:
            raise RuntimeError(f"Unable to draft {count} amendment variants")
        return variants

    def _create_proposal(
        self,
        *,
        spec_id: str,
        kind: str,
        summary: str,
        deltas: Mapping[str, Any],
        context: Mapping[str, Any],
        original_spec: Mapping[str, Any],
        proposed_spec: Mapping[str, Any],
        lineage: Mapping[str, Any] | None,
    ) -> AmendmentProposal:
        configured_k = max(int(os.getenv("SENTIENTOS_ROUTER_K", "3")), 1)
        configured_m = max(int(os.getenv("SENTIENTOS_ROUTER_M", "2")), 1)
        governor_config = governor_config_from_env(configured_k=configured_k, configured_m=configured_m)
        pressure_state = load_pressure_state()
        run_context = {
            "pipeline": "specamend",
            "spec_id": spec_id,
            "capability": str((context or {}).get("capability") or spec_id),
            "router_attempt": 1,
        }
        governor_decision = decide_budget(
            config=governor_config,
            pressure_state=pressure_state,
            run_context=run_context,
        )
        router_k = governor_decision.k_effective
        router_m = governor_decision.m_effective
        dominant = str((context or {}).get("dominant_signal") or kind)
        minute_bucket = self._now().strftime("%Y%m%d%H%M")
        router_seed = f"{spec_id}:{dominant}:{minute_bucket}:{router_k}"
        k_final = router_k
        escalated = False
        candidates = self._draft_amendment_variants(
            spec_id=spec_id,
            kind=kind,
            summary=summary,
            deltas=deltas,
            context=context,
            original_spec=original_spec,
            proposed_spec=proposed_spec,
            lineage=lineage,
            k=router_k,
            seed=router_seed,
        )
        stage_a_results: list[tuple[AmendmentProposal, Any]] = []
        for candidate in candidates:
            stage_a = self._integrity_daemon.evaluate_report_stage_a(candidate)
            stage_a_results.append((candidate, stage_a))

        if governor_decision.allow_escalation:
            next_k, escalated = maybe_escalate_k(
                k=router_k,
                stage_a_results=[(candidate.proposal_id, evaluation) for candidate, evaluation in stage_a_results],
            )
        else:
            next_k, escalated = router_k, False
        if escalated:
            k_final = next_k
            candidates = self._draft_amendment_variants(
                spec_id=spec_id,
                kind=kind,
                summary=summary,
                deltas=deltas,
                context=context,
                original_spec=original_spec,
                proposed_spec=proposed_spec,
                lineage=lineage,
                k=k_final,
                seed=f"{router_seed}:escalated:{k_final}",
            )
            stage_a_results = []
            for candidate in candidates:
                stage_a = self._integrity_daemon.evaluate_report_stage_a(candidate)
                stage_a_results.append((candidate, stage_a))

        promoted_ids: list[str] = []
        if governor_decision.mode != "diagnostics_only":
            promoted_ids = promote_candidates(
                [(candidate.proposal_id, evaluation) for candidate, evaluation in stage_a_results],
                m=router_m,
            )
        probe_cache = {
            candidate.proposal_id: evaluation.probe for candidate, evaluation in stage_a_results
        }
        results: list[CandidateResult] = []
        if governor_decision.mode != "diagnostics_only":
            for candidate in candidates:
                if candidate.proposal_id not in promoted_ids:
                    continue
                evaluation = self._integrity_daemon.evaluate_report_stage_b(
                    candidate,
                    probe_cache=probe_cache.get(candidate.proposal_id),
                )
                results.append(
                    CandidateResult(
                        candidate_id=candidate.proposal_id,
                        proposal=candidate,
                        evaluation=evaluation,
                        score=score_evaluation(evaluation),
                    )
                )
        if governor_decision.mode == "diagnostics_only":
            best_stage_a_candidate, best_stage_a_eval = sorted(
                stage_a_results,
                key=lambda item: rank_stage_a(item[1], candidate_id=item[0].proposal_id),
            )[0]
            selected = None
            router_status = "diagnostics_only"
            best_failure_id = best_stage_a_candidate.proposal_id
            best_failure_reason_codes = list(best_stage_a_eval.reason_codes_a)
            best_failure_score = score_evaluation_a(best_stage_a_eval)
            best_failure_violations = [dict(item) for item in best_stage_a_eval.violations_a]
        else:
            selected, router_status = choose_candidate(results)
            best_failure_id = selected.candidate_id
            best_failure_reason_codes = list(selected.evaluation.reason_codes)
            best_failure_score = selected.score
            best_failure_violations = [dict(item) for item in selected.evaluation.violations]
        stage_a_valid_count = sum(1 for _, evaluation in stage_a_results if bool(evaluation.valid_a))
        stage_b_valid_count = sum(1 for result in results if bool(result.evaluation.valid))
        router_telemetry = {
            "k_initial": configured_k,
            "k_final": k_final,
            "m": router_m if governor_decision.mode != "diagnostics_only" else 0,
            "escalated": escalated,
            "stage_a_evaluations": len(stage_a_results),
            "stage_b_evaluations": len(results),
            "stage_a_valid_count": stage_a_valid_count,
            "stage_b_valid_count": stage_b_valid_count,
            "router_status": router_status,
            "selected_candidate_id": selected.candidate_id if router_status == "selected" else None,
        }
        scorecard = {
            "router_k": configured_k,
            "router_m": configured_m,
            "router_seed": router_seed,
            "router_status": router_status,
            "router_telemetry": router_telemetry,
            "proof_budget": {
                "k": configured_k,
                "m": configured_m,
                "escalated": escalated,
                "k_final": k_final,
            },
            "governor": {
                "mode": governor_decision.mode,
                "k_effective": governor_decision.k_effective,
                "m_effective": governor_decision.m_effective,
                "allow_escalation": governor_decision.allow_escalation,
                "reasons": list(governor_decision.decision_reasons),
                "governor_version": governor_decision.governor_version,
            },
            "promoted_to_stage_b": list(promoted_ids),
            "stage_a": [
                {
                    "candidate_id": candidate.proposal_id,
                    "valid_a": evaluation.valid_a,
                    "reason_codes_a": list(evaluation.reason_codes_a),
                    "top_violation_codes_a": top_violation_codes(evaluation.violations_a),
                    "score_a": score_evaluation_a(evaluation),
                    "rank_a": rank_stage_a(evaluation, candidate_id=candidate.proposal_id),
                    "evaluation_artifact": evaluation.ledger_entry,
                }
                for candidate, evaluation in sorted(
                    stage_a_results,
                    key=lambda item: rank_stage_a(item[1], candidate_id=item[0].proposal_id),
                )
            ],
            "stage_b": [
                {
                    "candidate_id": result.candidate_id,
                    "score": result.score,
                    "rank": result.rank,
                    "valid": result.evaluation.valid,
                    "reason_codes": list(result.evaluation.reason_codes),
                    "violations": [dict(item) for item in result.evaluation.violations],
                    "top_violation_codes": top_violation_codes(result.evaluation.violations),
                    "evaluation_artifact": result.evaluation.ledger_entry,
                }
                for result in sorted(results, key=lambda item: item.rank or 999)
            ],
        }
        if router_status != "selected":
            scorecard["best_failure_id"] = best_failure_id
            scorecard["best_failure"] = {
                "reason_codes": best_failure_reason_codes,
                "score": best_failure_score,
            }
            self._append_amendment_log(
                "routing-failed",
                spec_id,
                best_failure_id,
                {"kind": kind, "summary": summary, "router_scorecard": scorecard},
            )
            self._append_amendment_log(
                "proof-budget-governor",
                spec_id,
                best_failure_id,
                build_governor_event(
                    decision=governor_decision,
                    run_context=run_context,
                    router_telemetry=router_telemetry,
                ),
            )
            pressure_state = update_pressure_state(
                prior=pressure_state,
                decision=governor_decision,
                router_telemetry=router_telemetry,
                router_status=router_status,
                run_context=run_context,
                config=governor_config,
            )
            save_pressure_state(pressure_state)
            self._append_amendment_log(
                "proof-budget",
                spec_id,
                best_failure_id,
                {
                    "event_type": "proof_budget",
                    "kind": kind,
                    "summary": summary,
                    "capability": str((context or {}).get("capability") or spec_id),
                    "run_provenance_hash": os.getenv("SENTIENTOS_RUN_PROVENANCE_HASH"),
                    "router_telemetry": dict(router_telemetry),
                },
            )
            if governor_decision.mode == "diagnostics_only":
                raise IntegrityViolation(
                    best_failure_id,
                    spec_id=spec_id,
                    reason_codes=["diagnostics_only_mode"],
                    violations=[
                        {
                            "code": "diagnostics_only_mode",
                            "detail": "Diagnostics-only mode: proof budget constrained",
                        }
                    ],
                )
            raise IntegrityViolation(
                best_failure_id,
                spec_id=spec_id,
                reason_codes=best_failure_reason_codes,
                violations=best_failure_violations,
            )

        proposal = selected.proposal
        scorecard["selected_candidate_id"] = selected.candidate_id
        proposal.add_note("router", "selected", {"router_scorecard": scorecard})
        self._persist(proposal)
        self._append_amendment_log(
            "proposed",
            proposal.spec_id,
            proposal.proposal_id,
            {"kind": kind, "summary": proposal.summary, "router_scorecard": scorecard},
        )
        self._append_amendment_log(
            "proof-budget-governor",
            proposal.spec_id,
            proposal.proposal_id,
            build_governor_event(
                decision=governor_decision,
                run_context=run_context,
                router_telemetry=router_telemetry,
            ),
        )
        pressure_state = update_pressure_state(
            prior=pressure_state,
            decision=governor_decision,
            router_telemetry=router_telemetry,
            router_status=router_status,
            run_context=run_context,
            config=governor_config,
        )
        save_pressure_state(pressure_state)
        self._append_amendment_log(
            "proof-budget",
            proposal.spec_id,
            proposal.proposal_id,
            {
                "event_type": "proof_budget",
                "kind": kind,
                "summary": proposal.summary,
                "capability": str((context or {}).get("capability") or proposal.spec_id),
                "run_provenance_hash": os.getenv("SENTIENTOS_RUN_PROVENANCE_HASH"),
                "router_telemetry": dict(router_telemetry),
            },
        )
        return proposal

    def _persist(self, proposal: AmendmentProposal) -> Path:
        proposal.updated_at = self._now()
        directory = self._directory_for_status(proposal.status)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{proposal.proposal_id}.json"
        path.write_text(
            json.dumps(proposal.to_dict(), sort_keys=True, indent=2),
            encoding="utf-8",
        )
        self._cleanup_duplicates(proposal.proposal_id, keep=path)
        return path

    def _cleanup_duplicates(self, proposal_id: str, *, keep: Path) -> None:
        for directory in (
            self._pending_dir,
            self._approved_dir,
            self._rejected_dir,
            self._archive_proposal_root,
        ):
            path = directory / f"{proposal_id}.json"
            if path == keep:
                continue
            if path.exists():
                path.unlink()

    def _directory_for_status(self, status: str) -> Path:
        if status == "pending":
            return self._pending_dir
        if status == "approved":
            return self._approved_dir
        if status == "rejected":
            return self._rejected_dir
        return self._archive_proposal_root

    def _append_amendment_log(
        self,
        event: str,
        spec_id: str,
        proposal_id: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        payload = {
            "timestamp": self._now().isoformat(),
            "event": event,
            "spec_id": spec_id,
            "proposal_id": proposal_id,
        }
        if metadata:
            payload["metadata"] = dict(metadata)
        with self._amendment_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def _append_spec_log(
        self,
        event: str,
        spec_id: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        payload = {
            "timestamp": self._now().isoformat(),
            "event": event,
            "spec_id": spec_id,
        }
        if metadata:
            payload["details"] = dict(metadata)
        with self._spec_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def _next_version(self, current: str) -> str:
        if current.startswith("v") and current[1:].isdigit():
            return f"v{int(current[1:]) + 1}"
        return "v2"

    def _has_active_amendment(self, spec_id: str) -> bool:
        for directory in (self._pending_dir, self._approved_dir):
            for path in directory.glob("*.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("spec_id") == spec_id:
                    return True
        return False

    def _load_state(self) -> None:
        if not self._state_path.exists():
            return
        payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            self._state.update(payload)

    def _save_state(self) -> None:
        self._state_path.write_text(
            json.dumps(self._state, sort_keys=True, indent=2),
            encoding="utf-8",
        )

    def _require(self, proposal_id: str) -> AmendmentProposal:
        proposal = self.load_proposal(proposal_id)
        if proposal is None:
            raise FileNotFoundError(f"Amendment {proposal_id} not found")
        return proposal


class AmendmentReviewBoard:
    """Operator workflow controller for spec amendments."""

    def __init__(
        self,
        engine: SpecAmender,
        hook: ReviewBoardHook | None = None,
    ) -> None:
        self._engine = engine
        self._hook = hook or ReviewBoardHook(
            create_default_router(), narrator=NarratorLink()
        )

    def approve(
        self,
        proposal_id: str,
        *,
        operator: str,
        ledger_entry: str | None,
    ) -> AmendmentProposal:
        if not ledger_entry:
            raise ValueError("Ledger entry required before approval")
        proposal = self._engine._require(proposal_id)
        report = self._hook.enforce(
            spec_id=proposal.spec_id,
            proposal_id=proposal.proposal_id,
        )
        if not report.passed:
            proposal.status = "quarantined"
            proposal.add_note(
                operator,
                "privilege-blocked",
                {"issues": report.issues},
            )
            self._engine._persist(proposal)
            self._engine._append_amendment_log(
                "privilege-blocked",
                proposal.spec_id,
                proposal.proposal_id,
                {"operator": operator, "issues": report.issues},
            )
            raise PrivilegeViolation(report)
        proposal.status = "approved"
        proposal.ledger_entry = ledger_entry
        proposal.add_note(operator, "approved", {"ledger_entry": ledger_entry})
        self._engine._persist(proposal)
        self._engine._append_amendment_log(
            "approved",
            proposal.spec_id,
            proposal.proposal_id,
            {"operator": operator, "ledger_entry": ledger_entry},
        )
        self._engine._update_preferences(proposal, outcome="approved")
        return proposal

    def reject(
        self,
        proposal_id: str,
        *,
        operator: str,
        reason: str | None = None,
    ) -> AmendmentProposal:
        proposal = self._engine._require(proposal_id)
        proposal.status = "rejected"
        proposal.add_note(operator, "rejected", {"reason": reason})
        self._engine._persist(proposal)
        self._engine._append_amendment_log(
            "rejected",
            proposal.spec_id,
            proposal.proposal_id,
            {"operator": operator, "reason": reason},
        )
        self._engine._update_preferences(proposal, outcome="rejected")
        return proposal

    def edit(
        self,
        proposal_id: str,
        *,
        operator: str,
        summary: str | None = None,
        deltas: Mapping[str, Any] | None = None,
        proposed_spec: Mapping[str, Any] | None = None,
    ) -> AmendmentProposal:
        return self._engine.edit_proposal(
            proposal_id,
            operator=operator,
            summary=summary,
            deltas=deltas,
            proposed_spec=proposed_spec,
        )

    def regenerate(
        self,
        spec_id: str,
        *,
        operator: str,
        reason: str,
        current_spec: Mapping[str, Any],
    ) -> AmendmentProposal:
        return self._engine.regenerate_spec(
            spec_id,
            operator=operator,
            reason=reason,
            current_spec=current_spec,
        )


# Extend SpecAmender with preference tracking utilities

def _update_preferences(self: SpecAmender, proposal: AmendmentProposal, *, outcome: str) -> None:
    context = proposal.context or {}
    signal = context.get("dominant_signal") or context.get("reason")
    if not signal:
        return
    prefs = self._state.setdefault("preferences", {})
    data = prefs.setdefault(signal, {"approved": 0, "rejected": 0})
    if outcome == "approved":
        data["approved"] = int(data.get("approved", 0)) + 1
    elif outcome == "rejected":
        data["rejected"] = int(data.get("rejected", 0)) + 1
    self._save_state()


SpecAmender._update_preferences = _update_preferences  # type: ignore[attr-defined]
