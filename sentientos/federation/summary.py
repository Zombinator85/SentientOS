"""Federation summary creation and IO helpers."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Optional

import experiment_tracker

from sentientos.cathedral.digest import CathedralDigest
from sentientos.federation.identity import NodeId

__all__ = [
    "FederationSummary",
    "CathedralState",
    "ExperimentState",
    "ConfigState",
    "build_local_summary",
    "summary_to_dict",
    "summary_from_dict",
    "summary_digest",
    "write_local_summary",
    "read_peer_summary",
]

_LOGGER = logging.getLogger("sentientos.federation.summary")
_EXPERIMENT_DSL_VERSION = "1.0"


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
class FederationSummary:
    node_name: str
    fingerprint: str
    ts: datetime
    cathedral: CathedralState
    experiments: ExperimentState
    config: ConfigState
    meta: Dict[str, Any]


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


def build_local_summary(runtime) -> FederationSummary:
    """Construct a local :class:`FederationSummary` snapshot."""

    config = getattr(runtime, "config", getattr(runtime, "_config", {}))
    config_map = _coerce_mapping(config)
    runtime_root = Path(getattr(runtime, "runtime_root", getattr(runtime, "_runtime_root", Path("."))))
    federation_cfg = getattr(runtime, "federation_config")
    node_id: NodeId = federation_cfg.node_id

    cathedral_digest: CathedralDigest = getattr(runtime, "cathedral_digest")
    ledger_path = getattr(runtime, "ledger_path", None)
    if ledger_path is None:
        ledger_path = getattr(getattr(runtime, "_amendment_applicator", None), "ledger_path", None)
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

    from sentientos.experiments.runner import CHAIN_LOG_PATH

    chain_runs = _count_chain_runs(CHAIN_LOG_PATH)
    config_digest = _compute_config_digest(config_map)

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
    )


def summary_to_dict(summary: FederationSummary) -> Dict[str, Any]:
    payload = asdict(summary)
    payload["ts"] = summary.ts.astimezone(timezone.utc).isoformat()
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
