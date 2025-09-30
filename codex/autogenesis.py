"""Autogenesis loop for SentientOS amendments.

This module wires together the SpecAmender so it can originate its own
amendment proposals when recurring telemetry gaps are detected.

It introduces four collaborators:

* :class:`GapScanner` – normalises telemetry inputs (logs, tests, covenant
  probes) and routes them into the amendment pipeline.
* :class:`SelfAmender` – bridges the scanner with :class:`~codex.amendments.SpecAmender`
  and ensures every generated proposal passes through the integrity gate.
* :class:`LineageWriter` – records provenance that clearly indicates the
  proposal was auto-authored by SentientOS rather than an operator.
* :class:`ReviewSymmetry` – mirrors the human review flow by ensuring the
  AmendmentReviewBoard remains the arbiter for self-authored amendments and
  narrates outcomes for dashboards.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, MutableMapping

import copy
import json

from .amendments import AmendmentProposal, AmendmentReviewBoard, SpecAmender


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class AutogenesisContext:
    """Context payload returned when a self-authored amendment is drafted."""

    proposal: AmendmentProposal
    lineage: Mapping[str, Any]
    metadata: Mapping[str, Any]


class GapScanner:
    """Monitor telemetry sources and surface recurring gaps."""

    def __init__(
        self,
        self_amender: "SelfAmender",
        *,
        spec_loader: Callable[[str], Mapping[str, Any]],
        now: Callable[[], datetime] = _default_now,
    ) -> None:
        self._self_amender = self_amender
        self._spec_loader = spec_loader
        self._now = now

    # ------------------------------------------------------------------
    # Telemetry ingestion helpers
    def observe_log_failure(
        self,
        spec_id: str,
        message: str,
        detail: str,
        *,
        severity: str = "error",
        metadata: Mapping[str, Any] | None = None,
    ) -> AutogenesisContext | None:
        payload = {
            "message": message,
            "detail": detail,
            "severity": severity,
            "recorded_at": self._now().isoformat(),
        }
        if metadata:
            payload.update(dict(metadata))
        return self._dispatch(
            spec_id,
            signal_type="log_failure",
            channel="logs",
            metadata=payload,
        )

    def observe_test_failure(
        self,
        spec_id: str,
        test_name: str,
        failure_reason: str,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> AutogenesisContext | None:
        payload = {
            "test": test_name,
            "reason": failure_reason,
            "recorded_at": self._now().isoformat(),
        }
        if metadata:
            payload.update(dict(metadata))
        return self._dispatch(
            spec_id,
            signal_type="test_failure",
            channel="tests",
            metadata=payload,
        )

    def observe_covenant_probe(
        self,
        spec_id: str,
        probe: str,
        finding: str,
        *,
        severity: str = "alert",
        metadata: Mapping[str, Any] | None = None,
    ) -> AutogenesisContext | None:
        payload = {
            "probe": probe,
            "finding": finding,
            "severity": severity,
            "recorded_at": self._now().isoformat(),
        }
        if metadata:
            payload.update(dict(metadata))
        return self._dispatch(
            spec_id,
            signal_type="covenant_gap",
            channel="covenant",
            metadata=payload,
        )

    # ------------------------------------------------------------------
    # Internal utilities
    def _dispatch(
        self,
        spec_id: str,
        *,
        signal_type: str,
        channel: str,
        metadata: Mapping[str, Any],
    ) -> AutogenesisContext | None:
        current_spec = self._resolve_spec(spec_id)
        result = self._self_amender.process_signal(
            spec_id,
            signal_type,
            metadata,
            current_spec=current_spec,
            channel=channel,
        )
        return result

    def _resolve_spec(self, spec_id: str) -> Mapping[str, Any]:
        payload = self._spec_loader(spec_id)
        if payload is None:
            raise FileNotFoundError(f"Spec {spec_id} not found for autogenesis scan")
        return copy.deepcopy(dict(payload))


class LineageWriter:
    """Attach provenance markers to self-authored amendments."""

    def __init__(
        self,
        engine: SpecAmender,
        *,
        author: str = "sentientos.autogenesis",
        now: Callable[[], datetime] = _default_now,
    ) -> None:
        self._engine = engine
        self._author = author
        self._now = now

    def compose(
        self,
        *,
        spec_id: str,
        signal: str,
        channel: str,
        metadata: Mapping[str, Any],
    ) -> Dict[str, Any]:
        return {
            "author": self._author,
            "spec_id": spec_id,
            "signal": signal,
            "channel": channel,
            "generated_at": self._now().isoformat(),
            "metadata": dict(metadata),
        }

    def apply(
        self,
        proposal: AmendmentProposal,
        *,
        lineage: Mapping[str, Any],
        channel: str,
        signal: str,
        metadata: Mapping[str, Any],
    ) -> AmendmentProposal:
        context_update = {
            "autogenesis": {
                "channel": channel,
                "signal": signal,
                "metadata": dict(metadata),
            }
        }
        return self._engine.annotate_lineage(
            proposal.proposal_id,
            lineage=lineage,
            context=context_update,
        )


class ReviewSymmetry:
    """Ensure self-authored amendments share the human review lane."""

    def __init__(
        self,
        *,
        root: Path | str,
        board: AmendmentReviewBoard,
        now: Callable[[], datetime] = _default_now,
    ) -> None:
        self._root = Path(root)
        self._board = board
        self._now = now
        self._log_path = self._root / "dashboard" / "autogenesis_log.jsonl"
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._tracked: set[str] = set()
        self._wrap_board()

    def register(
        self,
        proposal: AmendmentProposal,
        *,
        lineage: Mapping[str, Any],
    ) -> None:
        self._tracked.add(proposal.proposal_id)
        self._write_event(
            proposal,
            stage="proposed",
            lineage=lineage,
            message="Autogenesis event: self-authored amendment drafted.",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    def _wrap_board(self) -> None:
        if getattr(self._board, "_autogenesis_wrapped", False):
            return

        original_approve = self._board.approve
        original_reject = self._board.reject

        def approve_wrapper(
            proposal_id: str,
            *,
            operator: str,
            ledger_entry: str | None,
        ) -> AmendmentProposal:
            proposal = original_approve(
                proposal_id,
                operator=operator,
                ledger_entry=ledger_entry,
            )
            if proposal.proposal_id in self._tracked:
                self._write_event(
                    proposal,
                    stage="adopted",
                    lineage=proposal.lineage or {},
                    message="Autogenesis event: self-authored amendment adopted.",
                )
            return proposal

        def reject_wrapper(
            proposal_id: str,
            *,
            operator: str,
            reason: str | None = None,
        ) -> AmendmentProposal:
            proposal = original_reject(
                proposal_id,
                operator=operator,
                reason=reason,
            )
            if proposal.proposal_id in self._tracked:
                self._write_event(
                    proposal,
                    stage="rejected",
                    lineage=proposal.lineage or {},
                    message="Autogenesis event: self-authored amendment rejected.",
                )
            return proposal

        self._board.approve = approve_wrapper  # type: ignore[assignment]
        self._board.reject = reject_wrapper  # type: ignore[assignment]
        setattr(self._board, "_autogenesis_wrapped", True)

    def _write_event(
        self,
        proposal: AmendmentProposal,
        *,
        stage: str,
        lineage: Mapping[str, Any],
        message: str,
    ) -> None:
        payload: MutableMapping[str, Any] = {
            "timestamp": self._now().isoformat(),
            "proposal_id": proposal.proposal_id,
            "spec_id": proposal.spec_id,
            "stage": stage,
            "message": message,
            "lineage": dict(lineage),
        }
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")


class SelfAmender:
    """Bridge between telemetry scans and the amendment pipeline."""

    def __init__(
        self,
        engine: SpecAmender,
        *,
        lineage_writer: LineageWriter,
        review_symmetry: ReviewSymmetry,
    ) -> None:
        self._engine = engine
        self._lineage = lineage_writer
        self._review = review_symmetry

    def process_signal(
        self,
        spec_id: str,
        signal_type: str,
        metadata: Mapping[str, Any],
        *,
        current_spec: Mapping[str, Any],
        channel: str,
    ) -> AutogenesisContext | None:
        enriched = dict(metadata)
        enriched.setdefault("channel", channel)
        enriched.setdefault("origin", "GapScanner")
        proposal = self._engine.record_signal(
            spec_id,
            signal_type,
            enriched,
            current_spec=current_spec,
        )
        if proposal is None:
            return None
        lineage = self._lineage.compose(
            spec_id=spec_id,
            signal=signal_type,
            channel=channel,
            metadata=enriched,
        )
        proposal = self._lineage.apply(
            proposal,
            lineage=lineage,
            channel=channel,
            signal=signal_type,
            metadata=enriched,
        )
        self._review.register(proposal, lineage=lineage)
        return AutogenesisContext(proposal=proposal, lineage=lineage, metadata=enriched)

    def submit_manual(
        self,
        spec_id: str,
        *,
        summary: str,
        deltas: Mapping[str, Any],
        context: Mapping[str, Any],
        original_spec: Mapping[str, Any],
        proposed_spec: Mapping[str, Any],
        channel: str = "manual",
        signal: str = "self_override",
    ) -> AutogenesisContext:
        enriched_context = dict(context)
        enriched_context.setdefault("origin", "SelfAmender")
        enriched_context.setdefault("channel", channel)
        proposal = self._engine.propose_manual(
            spec_id,
            summary=summary,
            deltas=deltas,
            context=enriched_context,
            original_spec=original_spec,
            proposed_spec=proposed_spec,
            kind="amendment",
        )
        lineage = self._lineage.compose(
            spec_id=spec_id,
            signal=signal,
            channel=channel,
            metadata=enriched_context,
        )
        proposal = self._lineage.apply(
            proposal,
            lineage=lineage,
            channel=channel,
            signal=signal,
            metadata=enriched_context,
        )
        self._review.register(proposal, lineage=lineage)
        return AutogenesisContext(proposal=proposal, lineage=lineage, metadata=enriched_context)

