"""Deterministic drift deltas between replayed federation states."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Mapping

from .replay import AmendmentReplay, ChainReplay, DreamReplay, ExperimentReplay, ReplayResult

ReplaySeverity = Literal["none", "low", "medium", "high"]

__all__ = ["ReplaySeverity", "DeltaResult", "compute_delta"]


@dataclass(frozen=True)
class DeltaResult:
    severity: ReplaySeverity
    amendment: Dict[str, Any] = field(default_factory=dict)
    experiment: Dict[str, Any] = field(default_factory=dict)
    chain: Dict[str, Any] = field(default_factory=dict)
    dream: Dict[str, Any] = field(default_factory=dict)
    runtime: Dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "amendment": dict(self.amendment),
            "experiment": dict(self.experiment),
            "chain": dict(self.chain),
            "dream": dict(self.dream),
            "runtime": dict(self.runtime),
        }

    @staticmethod
    def from_payload(payload: Mapping[str, Any]) -> "DeltaResult":
        return DeltaResult(
            severity=str(payload.get("severity") or "none"),
            amendment=dict(payload.get("amendment", {})),
            experiment=dict(payload.get("experiment", {})),
            chain=dict(payload.get("chain", {})),
            dream=dict(payload.get("dream", {})),
            runtime=dict(payload.get("runtime", {})),
        )


def compute_delta(local: ReplayResult, remote: ReplayResult) -> DeltaResult:
    amendment = _diff_amendments(local.amendments, remote.amendments)
    experiment = _diff_experiments(local.experiments, remote.experiments)
    chain = _diff_chain(local.chains, remote.chains)
    dream = _diff_dream(local.dream, remote.dream, local.persona_digest, remote.persona_digest)
    runtime = _diff_runtime(local.runtime_digest, remote.runtime_digest)

    severity = _derive_severity(amendment, experiment, chain, dream, runtime)
    return DeltaResult(
        severity=severity,
        amendment=amendment,
        experiment=experiment,
        chain=chain,
        dream=dream,
        runtime=runtime,
    )


def _diff_amendments(local: AmendmentReplay, remote: AmendmentReplay) -> Dict[str, Any]:
    diff: Dict[str, Any] = {}
    local_ids = tuple(local.applied_ids)
    remote_ids = tuple(remote.applied_ids)
    if local_ids != remote_ids:
        missing = sorted(set(local_ids) - set(remote_ids))
        unexpected = sorted(set(remote_ids) - set(local_ids))
        if missing:
            diff["missing_amendments"] = tuple(missing)
        if unexpected:
            diff["unexpected_amendments"] = tuple(unexpected)
        if not missing and not unexpected:
            diff["sequence_mismatch"] = True
    if local.last_applied_digest != remote.last_applied_digest:
        diff["digest_mismatch"] = {
            "local": local.last_applied_digest,
            "remote": remote.last_applied_digest,
        }
    if local.ledger_height != remote.ledger_height:
        diff["ledger_mismatch"] = {
            "local": local.ledger_height,
            "remote": remote.ledger_height,
        }
    if local.rollback_count != remote.rollback_count:
        diff["rollback_mismatch"] = {
            "local": local.rollback_count,
            "remote": remote.rollback_count,
        }
    return diff


def _diff_experiments(local: ExperimentReplay, remote: ExperimentReplay) -> Dict[str, Any]:
    diff: Dict[str, Any] = {}
    if local.dsl_version != remote.dsl_version:
        diff["dsl_version_mismatch"] = {
            "local": local.dsl_version,
            "remote": remote.dsl_version,
        }
    if local.total != remote.total:
        diff["run_total_mismatch"] = {
            "local": local.total,
            "remote": remote.total,
        }
    if local.run_totals != remote.run_totals:
        diff["sequence_mismatch"] = True
    local_ids = tuple(local.latest_ids)
    remote_ids = tuple(remote.latest_ids)
    if local_ids != remote_ids:
        missing = sorted(set(local_ids) - set(remote_ids))
        unexpected = sorted(set(remote_ids) - set(local_ids))
        if missing:
            diff["missing_experiments"] = tuple(missing)
        if unexpected:
            diff["unexpected_experiments"] = tuple(unexpected)
        if not missing and not unexpected:
            diff.setdefault("sequence_mismatch", True)
    return diff


def _diff_chain(local: ChainReplay, remote: ChainReplay) -> Dict[str, Any]:
    diff: Dict[str, Any] = {}
    if local.totals != remote.totals:
        paired = {name: value for name, value in local.totals}
        paired_remote = {name: value for name, value in remote.totals}
        diff["sequence_mismatch"] = True
        for key in sorted(set(paired) | set(paired_remote)):
            if paired.get(key) != paired_remote.get(key):
                diff.setdefault("chain_delta", {})[key] = {
                    "local": paired.get(key, 0),
                    "remote": paired_remote.get(key, 0),
                }
    return diff


def _diff_dream(
    local: DreamReplay,
    remote: DreamReplay,
    local_persona: str,
    remote_persona: str,
) -> Dict[str, Any]:
    diff: Dict[str, Any] = {}
    if local.digest != remote.digest:
        diff["reflection_divergence"] = True
        diff["dream_fields"] = {
            "local": list(local.fields),
            "remote": list(remote.fields),
        }
    if local_persona != remote_persona:
        diff["persona_digest_mismatch"] = {
            "local": local_persona,
            "remote": remote_persona,
        }
    return diff


def _diff_runtime(local_digest: str, remote_digest: str) -> Dict[str, Any]:
    if local_digest == remote_digest:
        return {}
    return {
        "config_digest_mismatch": {
            "local": local_digest,
            "remote": remote_digest,
        }
    }


def _derive_severity(
    amendment: Mapping[str, Any],
    experiment: Mapping[str, Any],
    chain: Mapping[str, Any],
    dream: Mapping[str, Any],
    runtime: Mapping[str, Any],
) -> ReplaySeverity:
    if runtime or amendment:
        return "high"
    if experiment or chain:
        return "medium"
    if dream:
        return "low"
    return "none"
