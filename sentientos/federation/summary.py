"""Federation summary creation and IO helpers."""

from __future__ import annotations

import hashlib
import json
import logging
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional

import experiment_tracker

from sentientos.cathedral.digest import CathedralDigest
from sentientos.federation.identity import NodeId

__all__ = [
    "FederationSummary",
    "CathedralState",
    "ExperimentState",
    "ConfigState",
    "SummaryIndexes",
    "CathedralIndexSnapshot",
    "ExperimentIndexSnapshot",
    "build_cathedral_index",
    "build_experiment_index",
    "build_local_summary",
    "summary_to_dict",
    "summary_from_dict",
    "summary_digest",
    "write_local_summary",
    "read_peer_summary",
]

_LOGGER = logging.getLogger("sentientos.federation.summary")
_EXPERIMENT_DSL_VERSION = "1.0"


def _get_chain_log_path() -> Path:
    """Return the experiment chain log path lazily.

    Importing :mod:`sentientos.experiments.runner` at module import time can
    create circular import issues when the federation runtime bootstraps.
    Instead, import the module on demand and fall back to a sensible default
    path if the runner cannot be loaded.
    """

    try:  # pragma: no cover - exercised indirectly via runtime
        from sentientos.experiments import runner
    except Exception:  # pragma: no cover - defensive
        return Path("experiment_chain_log.jsonl")

    chain_log_path = getattr(runner, "CHAIN_LOG_PATH", None)
    if isinstance(chain_log_path, Path):
        return chain_log_path
    if isinstance(chain_log_path, str):
        return Path(chain_log_path)
    return Path("experiment_chain_log.jsonl")


@dataclass(frozen=True)
class CathedralState:
    last_applied_id: str
    last_applied_digest: str
    ledger_height: int
    rollback_count: int


@dataclass(frozen=True)
class ExperimentState:
    total: int
    chains: int
    dsl_version: str


@dataclass(frozen=True)
class ConfigState:
    config_digest: str


@dataclass(frozen=True)
class CathedralIndexSnapshot:
    applied_ids: List[str]
    applied_digests: List[str]
    height: int


@dataclass(frozen=True)
class ExperimentIndexSnapshot:
    runs: Dict[str, int]
    chains: Dict[str, int]
    latest_ids: List[str]


@dataclass(frozen=True)
class SummaryIndexes:
    cathedral: Optional[CathedralIndexSnapshot] = None
    experiments: Optional[ExperimentIndexSnapshot] = None


@dataclass(frozen=True)
class FederationSummary:
    node_name: str
    fingerprint: str
    ts: datetime
    cathedral: CathedralState
    experiments: ExperimentState
    config: ConfigState
    meta: Dict[str, Any]
    indexes: Optional[SummaryIndexes] = None


def _coerce_mapping(value: object) -> MutableMapping[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _read_ledger_state(ledger_path: Path) -> tuple[str, int]:
    if not ledger_path.exists():
        return "", 0
    last_digest = ""
    height = 0
    try:
        for raw in ledger_path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            height += 1
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, Mapping):
                digest = entry.get("digest")
                if isinstance(digest, str):
                    last_digest = digest
    except OSError:
        return "", 0
    return last_digest, height


def _resolve_ledger_path(runtime) -> Optional[Path]:
    ledger_path = getattr(runtime, "ledger_path", None)
    if isinstance(ledger_path, Path):
        return ledger_path
    applicator = getattr(runtime, "_amendment_applicator", None)
    ledger_path = getattr(applicator, "ledger_path", None)
    if isinstance(ledger_path, Path):
        return ledger_path
    return None


def _count_chain_runs(path: Path) -> int:
    if not path.exists():
        return 0
    seen = set()
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, Mapping):
                chain_id = entry.get("chain_id")
                if isinstance(chain_id, str) and chain_id:
                    seen.add(chain_id)
    except OSError:
        return 0
    return len(seen)


def _normalise_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _normalise_value(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalise_value(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _compute_config_digest(config: Mapping[str, Any]) -> str:
    serialised = json.dumps(_normalise_value(config), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def _hash_summary_payload(payload: Mapping[str, Any]) -> str:
    serialised = json.dumps(_normalise_value(payload), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def _positive_int(value: Any) -> int:
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return 0
    return coerced if coerced > 0 else 0


def _string_list(value: object) -> List[str]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        return []
    result: List[str] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if text:
                result.append(text)
    return result


def build_cathedral_index(
    runtime,
    limit: int,
    *,
    ledger_height: Optional[int] = None,
) -> Optional[CathedralIndexSnapshot]:
    """Return a bounded snapshot of recent Cathedral amendments."""

    try:
        window = max(0, int(limit))
    except (TypeError, ValueError):
        window = 0
    if window <= 0:
        return None
    ledger_path = _resolve_ledger_path(runtime)
    if not isinstance(ledger_path, Path) or not ledger_path.exists():
        return None

    applied_ids: deque[str] = deque(maxlen=window)
    applied_digests: deque[str] = deque(maxlen=window)
    counted_height = 0

    try:
        for raw in ledger_path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            counted_height += 1
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, Mapping):
                continue
            event = str(entry.get("event") or "").strip().lower()
            if event and event not in {"apply", "application"}:
                continue
            amendment_id = entry.get("amendment_id")
            digest = entry.get("digest")
            if isinstance(amendment_id, str):
                text = amendment_id.strip()
                if text:
                    applied_ids.append(text)
            if isinstance(digest, str):
                digest_text = digest.strip()
                if digest_text:
                    applied_digests.append(digest_text)
    except OSError:
        return None

    height_value = ledger_height if ledger_height is not None else counted_height
    return CathedralIndexSnapshot(
        applied_ids=list(applied_ids),
        applied_digests=list(applied_digests),
        height=max(0, int(height_value)),
    )


def build_experiment_index(
    runtime,
    limit: int,
    *,
    experiments: Optional[Iterable[Mapping[str, Any]]] = None,
) -> Optional[ExperimentIndexSnapshot]:
    """Return a bounded snapshot of recent experiment activity."""

    try:
        window = max(0, int(limit))
    except (TypeError, ValueError):
        window = 0
    if window <= 0:
        return None

    if experiments is None:
        try:
            records: List[Mapping[str, Any]] = list(experiment_tracker.list_experiments())
        except Exception:  # pragma: no cover - defensive
            records = []
    else:
        records = [record for record in experiments if isinstance(record, Mapping)]

    latest_ids: deque[str] = deque(maxlen=window)
    runs_total = 0
    runs_successful = 0

    def _sort_key(record: Mapping[str, Any]) -> tuple[str, str]:
        proposed = str(record.get("proposed_at") or "")
        exp_id = str(record.get("id") or "")
        return proposed, exp_id

    for record in sorted(records, key=_sort_key):
        triggers = _positive_int(record.get("triggers"))
        successes = _positive_int(record.get("success"))
        runs_total += triggers
        runs_successful += min(triggers, successes)
        exp_id = str(record.get("id") or "").strip()
        if exp_id:
            latest_ids.append(exp_id)

    runs_failed = max(0, runs_total - runs_successful)

    chains_total = 0
    chains_completed = 0
    chains_aborted = 0
    chain_log_path = _get_chain_log_path()
    if chain_log_path.exists():
        try:
            for raw in chain_log_path.read_text(encoding="utf-8").splitlines():
                if not raw.strip():
                    continue
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, Mapping):
                    continue
                if str(entry.get("event") or "") != "chain_complete":
                    continue
                chains_total += 1
                outcome = str(entry.get("outcome") or "").strip().lower()
                if outcome == "success":
                    chains_completed += 1
                else:
                    chains_aborted += 1
        except OSError:
            pass

    runs = {
        "total": runs_total,
        "successful": runs_successful,
        "failed": runs_failed,
    }
    chains = {
        "total": chains_total,
        "completed": chains_completed,
        "aborted": chains_aborted,
    }

    return ExperimentIndexSnapshot(runs=runs, chains=chains, latest_ids=list(latest_ids))


def build_local_summary(runtime) -> FederationSummary:
    """Construct a local :class:`FederationSummary` snapshot."""

    config = getattr(runtime, "config", getattr(runtime, "_config", {}))
    config_map = _coerce_mapping(config)
    runtime_root = Path(getattr(runtime, "runtime_root", getattr(runtime, "_runtime_root", Path("."))))
    federation_cfg = getattr(runtime, "federation_config")
    node_id: NodeId = federation_cfg.node_id

    cathedral_digest: CathedralDigest = getattr(runtime, "cathedral_digest")
    ledger_path = _resolve_ledger_path(runtime)
    if isinstance(ledger_path, Path):
        last_digest, height = _read_ledger_state(ledger_path)
    else:
        last_digest, height = "", 0
    rollback_count = getattr(cathedral_digest, "rollbacks", 0)

    try:
        experiments = experiment_tracker.list_experiments()
    except Exception:  # pragma: no cover - defensive
        experiments = []
    total_experiments = len(experiments)

    chain_log_path = _get_chain_log_path()
    chain_runs = _count_chain_runs(chain_log_path)
    config_digest = _compute_config_digest(config_map)

    indexes: Optional[SummaryIndexes] = None
    if getattr(federation_cfg, "enabled", False):
        cathedral_index = build_cathedral_index(runtime, getattr(federation_cfg, "max_cathedral_ids", 0), ledger_height=height)
        experiment_index = build_experiment_index(runtime, getattr(federation_cfg, "max_experiment_ids", 0), experiments=experiments)
        if cathedral_index or experiment_index:
            indexes = SummaryIndexes(cathedral=cathedral_index, experiments=experiment_index)

    return FederationSummary(
        node_name=node_id.name,
        fingerprint=node_id.fingerprint,
        ts=datetime.now(timezone.utc),
        cathedral=CathedralState(
            last_applied_id=getattr(cathedral_digest, "last_applied_id", "") or "",
            last_applied_digest=last_digest,
            ledger_height=height,
            rollback_count=int(rollback_count),
        ),
        experiments=ExperimentState(
            total=total_experiments,
            chains=chain_runs,
            dsl_version=_EXPERIMENT_DSL_VERSION,
        ),
        config=ConfigState(config_digest=config_digest),
        meta={"runtime_root": str(runtime_root)},
        indexes=indexes,
    )


def summary_to_dict(summary: FederationSummary) -> Dict[str, Any]:
    payload = asdict(summary)
    payload["ts"] = summary.ts.astimezone(timezone.utc).isoformat()
    indexes_value = payload.get("indexes")
    if indexes_value is None:
        payload.pop("indexes", None)
    else:
        cathedral_index = indexes_value.get("cathedral") if isinstance(indexes_value, Mapping) else None
        experiments_index = indexes_value.get("experiments") if isinstance(indexes_value, Mapping) else None
        if not cathedral_index and not experiments_index:
            payload.pop("indexes", None)
    return payload


def summary_from_dict(data: Mapping[str, Any]) -> FederationSummary:
    ts_value = data.get("ts")
    if isinstance(ts_value, str):
        ts = datetime.fromisoformat(ts_value)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    else:
        ts = datetime.now(timezone.utc)
    cathedral_data = data.get("cathedral", {})
    experiments_data = data.get("experiments", {})
    config_data = data.get("config", {})
    meta_source = data.get("meta")
    meta: Dict[str, Any]
    if isinstance(meta_source, Mapping):
        meta = {str(k): meta_source[k] for k in meta_source.keys()}
    else:
        meta = {}

    indexes = _parse_indexes(data.get("indexes"))

    return FederationSummary(
        node_name=str(data.get("node_name") or ""),
        fingerprint=str(data.get("fingerprint") or ""),
        ts=ts,
        cathedral=CathedralState(
            last_applied_id=str(cathedral_data.get("last_applied_id") or ""),
            last_applied_digest=str(cathedral_data.get("last_applied_digest") or ""),
            ledger_height=int(cathedral_data.get("ledger_height") or 0),
            rollback_count=int(cathedral_data.get("rollback_count") or 0),
        ),
        experiments=ExperimentState(
            total=int(experiments_data.get("total") or 0),
            chains=int(experiments_data.get("chains") or 0),
            dsl_version=str(experiments_data.get("dsl_version") or ""),
        ),
        config=ConfigState(config_digest=str(config_data.get("config_digest") or "")),
        meta=meta,
        indexes=indexes,
    )


def summary_digest(summary: FederationSummary) -> str:
    payload = summary_to_dict(summary)
    payload.pop("ts", None)
    payload.pop("meta", None)
    return _hash_summary_payload(payload)


def write_local_summary(summary: FederationSummary, path: str) -> None:
    payload = summary_to_dict(summary)
    payload["digest"] = summary_digest(summary)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True)
    target.write_text(text, encoding="utf-8")


def read_peer_summary(path: str) -> Optional[FederationSummary]:
    target = Path(path)
    if not target.exists():
        return None
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError:
        _LOGGER.error("Failed to read peer summary", exc_info=True)
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        _LOGGER.error("Peer summary at %s is not valid JSON", target)
        return None
    if not isinstance(data, Mapping):
        _LOGGER.error("Peer summary at %s is not a mapping", target)
        return None
    digest = data.get("digest")
    if not isinstance(digest, str) or not digest:
        _LOGGER.error("Peer summary at %s missing digest", target)
        return None
    summary = summary_from_dict(data)
    expected = summary_digest(summary)
    if digest != expected:
        _LOGGER.error("Digest mismatch for peer summary at %s", target)
        return None
    return summary


def _parse_indexes(data: object) -> Optional[SummaryIndexes]:
    if not isinstance(data, Mapping):
        return None
    cathedral = _parse_cathedral_index(data.get("cathedral"))
    experiments = _parse_experiment_index(data.get("experiments"))
    if not cathedral and not experiments:
        return None
    return SummaryIndexes(cathedral=cathedral, experiments=experiments)


def _parse_cathedral_index(value: object) -> Optional[CathedralIndexSnapshot]:
    if not isinstance(value, Mapping):
        return None
    applied_ids = _string_list(value.get("applied_ids"))
    applied_digests = _string_list(value.get("applied_digests"))
    height = _positive_int(value.get("height"))
    return CathedralIndexSnapshot(applied_ids=applied_ids, applied_digests=applied_digests, height=height)


def _parse_experiment_index(value: object) -> Optional[ExperimentIndexSnapshot]:
    if not isinstance(value, Mapping):
        return None
    runs_source = value.get("runs")
    if not isinstance(runs_source, Mapping):
        runs_source = {}
    chains_source = value.get("chains")
    if not isinstance(chains_source, Mapping):
        chains_source = {}
    runs = {
        "total": _positive_int(runs_source.get("total")),
        "successful": _positive_int(runs_source.get("successful")),
        "failed": _positive_int(runs_source.get("failed")),
    }
    chains = {
        "total": _positive_int(chains_source.get("total")),
        "completed": _positive_int(chains_source.get("completed")),
        "aborted": _positive_int(chains_source.get("aborted")),
    }
    latest_ids = _string_list(value.get("latest_ids"))
    return ExperimentIndexSnapshot(runs=runs, chains=chains, latest_ids=latest_ids)
