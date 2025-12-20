from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
import json
import uuid
from typing import Iterable, Literal, MutableMapping, Sequence


PROVISIONAL_ASSERTION_SCHEMA_VERSION = "1.0"

ConfidenceBand = Literal["LOW", "MEDIUM", "HIGH"]
RevisionState = Literal["ACTIVE", "SUPERSEDED", "RETRACTED"]


@dataclass(frozen=True)
class ProvisionalAssertion:
    """Immutable provisional assertion entry.

    Assertions are append-only. Any refinement must create a new entry that
    references the previous one via ``supersedes``.
    """

    assertion_id: str
    claim_text: str
    confidence_band: ConfidenceBand
    evidence_summary: str
    asserted_at: datetime
    review_horizon: datetime
    revision_state: RevisionState
    supersedes: str | None = None
    superseded_by: tuple[str, ...] = field(default_factory=tuple)
    terminology_weight: str | None = None
    version: int = 1
    schema_version: str = PROVISIONAL_ASSERTION_SCHEMA_VERSION

    def to_payload(self) -> dict[str, object]:
        return {
            "assertion_id": self.assertion_id,
            "version": self.version,
            "claim_text": self.claim_text,
            "confidence_band": self.confidence_band,
            "evidence_summary": self.evidence_summary,
            "asserted_at": self.asserted_at.isoformat(),
            "review_horizon": self.review_horizon.isoformat(),
            "revision_state": self.revision_state,
            "supersedes": self.supersedes,
            "superseded_by": list(self.superseded_by),
            "terminology_weight": self.terminology_weight,
            "schema_version": self.schema_version,
        }


class ProvisionalAssertionLedger:
    """Lifecycle engine for provisional assertions.

    The ledger enforces immutability by never mutating stored assertions. All
    updates are represented as new entries linked by ``supersedes``.
    """

    def __init__(self) -> None:
        self._assertions: dict[str, ProvisionalAssertion] = {}
        self._superseded_links: dict[str, set[str]] = {}

    def _normalize_band(self, confidence_band: ConfidenceBand) -> ConfidenceBand:
        normalized = confidence_band.upper()
        allowed: tuple[ConfidenceBand, ...] = ("LOW", "MEDIUM", "HIGH")
        if normalized not in allowed:
            raise ValueError(f"confidence_band must be one of {allowed}")
        return normalized  # type: ignore[return-value]

    def _validate_uncertainty(self, evidence_summary: str, confidence_band: ConfidenceBand) -> None:
        if not evidence_summary.strip():
            raise ValueError("evidence_summary must capture mechanisms, not be empty")
        if confidence_band is None:
            raise ValueError("confidence_band is required to encode uncertainty")

    def _register(self, assertion: ProvisionalAssertion) -> ProvisionalAssertion:
        if assertion.assertion_id in self._assertions:
            raise RuntimeError("editing assertions in place is forbidden")
        self._assertions[assertion.assertion_id] = assertion
        if assertion.supersedes:
            self._superseded_links.setdefault(assertion.supersedes, set()).add(assertion.assertion_id)
        return assertion

    def _link_view(self, assertion: ProvisionalAssertion) -> ProvisionalAssertion:
        superseded_by = tuple(sorted(self._superseded_links.get(assertion.assertion_id, set())))
        if superseded_by != assertion.superseded_by or (
            superseded_by and assertion.revision_state == "ACTIVE"
        ):
            new_state = assertion.revision_state
            if superseded_by and assertion.revision_state == "ACTIVE":
                new_state = "SUPERSEDED"
            return replace(assertion, superseded_by=superseded_by, revision_state=new_state)
        return assertion

    def create_assertion(
        self,
        *,
        claim_text: str,
        confidence_band: ConfidenceBand,
        evidence_summary: str,
        review_horizon: datetime,
        asserted_at: datetime | None = None,
        supersedes: str | None = None,
        terminology_weight: str | None = None,
    ) -> ProvisionalAssertion:
        band = self._normalize_band(confidence_band)
        self._validate_uncertainty(evidence_summary, band)
        if supersedes and supersedes not in self._assertions:
            raise KeyError(f"cannot supersede unknown assertion {supersedes}")

        asserted_time = asserted_at or datetime.utcnow()
        version = 1
        if supersedes:
            parent = self._assertions[supersedes]
            version = parent.version + 1
        assertion = ProvisionalAssertion(
            assertion_id=uuid.uuid4().hex,
            claim_text=claim_text,
            confidence_band=band,
            evidence_summary=evidence_summary,
            asserted_at=asserted_time,
            review_horizon=review_horizon,
            revision_state="ACTIVE" if band != "LOW" else "ACTIVE",
            supersedes=supersedes,
            terminology_weight=terminology_weight,
            version=version,
        )
        return self._register(assertion)

    def revise_confidence(
        self,
        assertion_id: str,
        *,
        new_band: ConfidenceBand,
        evidence_summary: str,
        review_horizon: datetime,
    ) -> ProvisionalAssertion:
        if assertion_id not in self._assertions:
            raise KeyError(f"unknown assertion {assertion_id}")
        return self.create_assertion(
            claim_text=self._assertions[assertion_id].claim_text,
            confidence_band=new_band,
            evidence_summary=evidence_summary,
            review_horizon=review_horizon,
            supersedes=assertion_id,
            terminology_weight=self._assertions[assertion_id].terminology_weight,
        )

    def retract(self, assertion_id: str, *, cause: str, review_horizon: datetime | None = None) -> ProvisionalAssertion:
        if assertion_id not in self._assertions:
            raise KeyError(f"unknown assertion {assertion_id}")
        horizon = review_horizon or (datetime.utcnow() + timedelta(days=1))
        retraction = ProvisionalAssertion(
            assertion_id=uuid.uuid4().hex,
            claim_text=self._assertions[assertion_id].claim_text,
            confidence_band="LOW",
            evidence_summary=f"retraction: {cause}",
            asserted_at=datetime.utcnow(),
            review_horizon=horizon,
            revision_state="RETRACTED",
            supersedes=assertion_id,
            terminology_weight=self._assertions[assertion_id].terminology_weight,
            version=self._assertions[assertion_id].version + 1,
        )
        return self._register(retraction)

    def supersession_chain(self, assertion_id: str) -> list[ProvisionalAssertion]:
        if assertion_id not in self._assertions:
            raise KeyError(f"unknown assertion {assertion_id}")
        chain: list[ProvisionalAssertion] = []
        current = assertion_id
        while current:
            record = self._link_view(self._assertions[current])
            chain.append(record)
            superseders = self._superseded_links.get(current, set())
            current = sorted(superseders)[-1] if superseders else ""
        return chain

    def due_for_review(self, *, now: datetime | None = None) -> list[ProvisionalAssertion]:
        timestamp = now or datetime.utcnow()
        return [
            self._link_view(assertion)
            for assertion in self._assertions.values()
            if assertion.review_horizon <= timestamp and assertion.revision_state != "RETRACTED"
        ]

    def serialize(self) -> str:
        ordered = sorted(self._assertions.values(), key=lambda a: (a.asserted_at, a.assertion_id))
        payloads = [self._link_view(assertion).to_payload() for assertion in ordered]
        return json.dumps(payloads, sort_keys=True, separators=(",", ":"))

    def policy_snapshot_annotation(self) -> dict[str, object]:
        return {"provisional_assertions": [self._link_view(a).to_payload() for a in self._assertions.values()]}

    def enqueue_reviews(self, queue: MutableMapping[str, list[dict[str, object]]], *, now: datetime | None = None) -> None:
        due_entries = [assertion.to_payload() for assertion in self.due_for_review(now=now)]
        queue.setdefault("provisional_assertions", []).extend(due_entries)

    def annotate_tooling_status(self, status: MutableMapping[str, object]) -> None:
        status.setdefault("provisional_assertions", {})["active"] = [
            assertion.to_payload()
            for assertion in self._assertions.values()
            if assertion.revision_state == "ACTIVE"
        ]

    def annotate_pressure_log(self, pressure_log: MutableMapping[str, object], *, context: str) -> None:
        pressure_log.setdefault("epistemic_annotations", []).append(
            {
                "context": context,
                "assertions_considered": [self._link_view(a).assertion_id for a in self._assertions.values()],
                "schema_version": PROVISIONAL_ASSERTION_SCHEMA_VERSION,
            }
        )


class SilenceDebt(Exception):
    """Raised when silence would mask a high-signal condition."""


class AntiLagGuard:
    """Detect silence under pressure and prompt provisional naming."""

    def __init__(self, *, signal_threshold: float = 1.0):
        self.signal_threshold = signal_threshold

    def detect_silence(
        self,
        *,
        signals: Sequence[float],
        topic: str,
        assertions: Iterable[ProvisionalAssertion],
    ) -> dict[str, object]:
        max_signal = max(signals) if signals else 0.0
        has_assertion = any(a.claim_text == topic for a in assertions)
        if max_signal >= self.signal_threshold and not has_assertion:
            raise SilenceDebt(f"silence under pressure for {topic}")
        if max_signal >= self.signal_threshold and has_assertion:
            return {"topic": topic, "status": "covered", "signal": max_signal}
        return {"topic": topic, "status": "quiet", "signal": max_signal}

    def prompt(self, topic: str, signal: float, horizon: datetime) -> dict[str, object]:
        return {
            "prompt": f"Name the emerging pattern around {topic} with provisional language.",
            "signal": signal,
            "review_horizon": horizon.isoformat(),
        }
