"""Passive, deterministic reconstruction of peer federation state."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from .summary import (
    CathedralIndexSnapshot,
    FederationSummary,
    SummaryIndexes,
)

__all__ = [
    "AmendmentReplay",
    "ExperimentReplay",
    "ChainReplay",
    "DreamReplay",
    "ReplayResult",
    "PassiveReplay",
]


@dataclass(frozen=True)
class AmendmentReplay:
    """Hashable snapshot of Cathedral amendments."""

    last_applied_id: str
    last_applied_digest: str
    ledger_height: int
    rollback_count: int
    applied_ids: Tuple[str, ...]
    applied_digests: Tuple[str, ...]


@dataclass(frozen=True)
class ExperimentReplay:
    """Hashable snapshot of experiment execution state."""

    total: int
    chains: int
    dsl_version: str
    run_totals: Tuple[Tuple[str, int], ...]
    latest_ids: Tuple[str, ...]


@dataclass(frozen=True)
class ChainReplay:
    """Hashable snapshot of experiment chain activity."""

    totals: Tuple[Tuple[str, int], ...]


@dataclass(frozen=True)
class DreamReplay:
    """Hashable snapshot of dreamloop metadata."""

    fields: Tuple[Tuple[str, str], ...]
    digest: str


@dataclass(frozen=True)
class ReplayResult:
    """Deterministic replay artefact produced for a node."""

    identity: str
    amendments: AmendmentReplay
    experiments: ExperimentReplay
    chains: ChainReplay
    dream: DreamReplay
    persona_digest: str
    runtime_digest: str

    def to_payload(self) -> Dict[str, Any]:
        return {
            "identity": self.identity,
            "amendments": {
                "last_applied_id": self.amendments.last_applied_id,
                "last_applied_digest": self.amendments.last_applied_digest,
                "ledger_height": self.amendments.ledger_height,
                "rollback_count": self.amendments.rollback_count,
                "applied_ids": list(self.amendments.applied_ids),
                "applied_digests": list(self.amendments.applied_digests),
            },
            "experiments": {
                "total": self.experiments.total,
                "chains": self.experiments.chains,
                "dsl_version": self.experiments.dsl_version,
                "run_totals": list(self.experiments.run_totals),
                "latest_ids": list(self.experiments.latest_ids),
            },
            "chains": {"totals": list(self.chains.totals)},
            "dream": {
                "fields": list(self.dream.fields),
                "digest": self.dream.digest,
            },
            "persona_digest": self.persona_digest,
            "runtime_digest": self.runtime_digest,
        }

    @staticmethod
    def from_payload(payload: Mapping[str, Any]) -> "ReplayResult":
        amendments = payload.get("amendments", {})
        experiments = payload.get("experiments", {})
        chains = payload.get("chains", {})
        dream = payload.get("dream", {})
        return ReplayResult(
            identity=str(payload.get("identity") or ""),
            amendments=AmendmentReplay(
                last_applied_id=str(amendments.get("last_applied_id") or ""),
                last_applied_digest=str(amendments.get("last_applied_digest") or ""),
                ledger_height=int(amendments.get("ledger_height") or 0),
                rollback_count=int(amendments.get("rollback_count") or 0),
                applied_ids=tuple(str(v) for v in amendments.get("applied_ids", []) if isinstance(v, str)),
                applied_digests=tuple(
                    str(v) for v in amendments.get("applied_digests", []) if isinstance(v, str)
                ),
            ),
            experiments=ExperimentReplay(
                total=int(experiments.get("total") or 0),
                chains=int(experiments.get("chains") or 0),
                dsl_version=str(experiments.get("dsl_version") or ""),
                run_totals=tuple(
                    (str(name), int(value))
                    for name, value in experiments.get("run_totals", [])
                    if isinstance(name, str)
                ),
                latest_ids=tuple(
                    str(value)
                    for value in experiments.get("latest_ids", [])
                    if isinstance(value, str)
                ),
            ),
            chains=ChainReplay(
                totals=tuple(
                    (str(name), int(value)) for name, value in chains.get("totals", []) if isinstance(name, str)
                ),
            ),
            dream=DreamReplay(
                fields=tuple(
                    (str(name), str(value))
                    for name, value in dream.get("fields", [])
                    if isinstance(name, str)
                ),
                digest=str(dream.get("digest") or ""),
            ),
            persona_digest=str(payload.get("persona_digest") or ""),
            runtime_digest=str(payload.get("runtime_digest") or ""),
        )


class PassiveReplay:
    """Deterministically reconstruct state from a peer summary."""

    def __init__(
        self,
        identity: str,
        summary: FederationSummary,
        registry: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.identity = identity
        self.summary = summary
        self.registry = registry or {}

    def simulate(self) -> ReplayResult:
        indexes = self.summary.indexes
        amendment = self._build_amendments(indexes)
        experiments = self._build_experiments(indexes)
        chains = self._build_chains(indexes)
        dream = self._build_dream()
        persona_digest = self._persona_digest()
        runtime_digest = str(self.summary.config.config_digest or "")
        return ReplayResult(
            identity=self.identity,
            amendments=amendment,
            experiments=experiments,
            chains=chains,
            dream=dream,
            persona_digest=persona_digest,
            runtime_digest=runtime_digest,
        )

    def _build_amendments(self, indexes: Optional[SummaryIndexes]) -> AmendmentReplay:
        cathedral: Optional[CathedralIndexSnapshot] = None
        if indexes is not None:
            cathedral = indexes.cathedral
        applied_ids: Tuple[str, ...] = tuple(cathedral.applied_ids) if cathedral else tuple()
        applied_digests: Tuple[str, ...] = tuple(cathedral.applied_digests) if cathedral else tuple()
        return AmendmentReplay(
            last_applied_id=str(self.summary.cathedral.last_applied_id or ""),
            last_applied_digest=str(self.summary.cathedral.last_applied_digest or ""),
            ledger_height=int(self.summary.cathedral.ledger_height or 0),
            rollback_count=int(self.summary.cathedral.rollback_count or 0),
            applied_ids=applied_ids,
            applied_digests=applied_digests,
        )

    def _build_experiments(self, indexes: Optional[SummaryIndexes]) -> ExperimentReplay:
        snapshot = indexes.experiments if indexes is not None else None
        if snapshot:
            run_totals = tuple(sorted((str(name), int(value)) for name, value in snapshot.runs.items()))
            latest = tuple(snapshot.latest_ids)
        else:
            run_totals = tuple()
            latest = tuple()
        return ExperimentReplay(
            total=int(self.summary.experiments.total or 0),
            chains=int(self.summary.experiments.chains or 0),
            dsl_version=str(self.summary.experiments.dsl_version or ""),
            run_totals=run_totals,
            latest_ids=latest,
        )

    def _build_chains(self, indexes: Optional[SummaryIndexes]) -> ChainReplay:
        snapshot = indexes.experiments if indexes is not None else None
        if snapshot:
            totals = tuple(sorted((str(name), int(value)) for name, value in snapshot.chains.items()))
        else:
            totals = (
                ("total", int(self.summary.experiments.chains or 0)),
            )
        return ChainReplay(totals=totals)

    def _build_dream(self) -> DreamReplay:
        dream_meta = self._meta_section("dream")
        if not dream_meta:
            dream_meta = _coerce_mapping(self.registry.get("dream"))
        normalized = tuple(
            (str(key), _coerce_meta_value(value))
            for key, value in sorted(dream_meta.items(), key=lambda item: str(item[0]))
        )
        digest = _hash_payload({key: value for key, value in normalized})
        return DreamReplay(fields=normalized, digest=digest)

    def _persona_digest(self) -> str:
        persona_meta = self._meta_section("persona")
        if not persona_meta:
            persona_meta = _coerce_mapping(self.registry.get("persona"))
        return _hash_payload(_normalise_meta(persona_meta))

    def _meta_section(self, name: str) -> Dict[str, Any]:
        meta = self.summary.meta or {}
        raw = meta.get(name)
        if isinstance(raw, Mapping):
            return {str(key): raw[key] for key in raw.keys()}
        return {}


def _coerce_mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(k): value[k] for k in value.keys()}
    return {}


def _coerce_meta_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return ""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _normalise_meta(meta: Mapping[str, Any]) -> Mapping[str, Any]:
    normalised: Dict[str, Any] = {}
    for key, value in meta.items():
        if isinstance(value, Mapping):
            normalised[str(key)] = _normalise_meta(value)
        elif isinstance(value, (list, tuple, set)):
            normalised[str(key)] = [_normalise_meta_item(item) for item in value]
        else:
            normalised[str(key)] = _normalise_meta_item(value)
    return normalised


def _normalise_meta_item(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _normalise_meta(value)
    if isinstance(value, (list, tuple, set)):
        return [_normalise_meta_item(item) for item in value]
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return repr(value)


def _hash_payload(payload: Mapping[str, Any]) -> str:
    serialised = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()
