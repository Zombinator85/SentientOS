"""Service Level Objective evaluation for SentientOS."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

try:  # pragma: no cover - optional dependency
    import yaml
except ModuleNotFoundError:  # pragma: no cover - fallback to built-ins
    yaml = None  # type: ignore[assignment]

from .metrics import MetricsRegistry
from .storage import get_data_root


@dataclass(frozen=True)
class SLODefinition:
    name: str
    description: str
    target: float
    measure: str
    direction: str
    unit: str | None = None


@dataclass(frozen=True)
class SLOStatus:
    definition: SLODefinition
    value: float
    ok: bool
    message: str


def _load_default_definitions() -> list[SLODefinition]:
    return [
        SLODefinition(
            name="admin_api_availability",
            description="Admin API availability over rolling 24h",
            target=0.999,
            measure="admin_availability",
            direction=">=",
        ),
        SLODefinition(
            name="rehearsal_success_ratio",
            description="Successful rehearsal decisions per 24h",
            target=0.98,
            measure="rehearsal_success_ratio",
            direction=">=",
        ),
        SLODefinition(
            name="council_quorum_latency_p95",
            description="Council quorum latency p95 (seconds)",
            target=2.0,
            measure="council_latency_p95",
            direction="<=",
            unit="s",
        ),
        SLODefinition(
            name="critic_disagreement_rate",
            description="Critic disagreement rate over rolling hour",
            target=0.05,
            measure="critic_disagreement_rate",
            direction="<=",
        ),
        SLODefinition(
            name="hungry_eyes_retrain_freshness",
            description="Hungry Eyes retrain freshness in days",
            target=7.0,
            measure="hungry_eyes_freshness",
            direction="<=",
            unit="d",
        ),
    ]


def _load_yaml_definitions(path: Path) -> list[SLODefinition]:
    if yaml is None:
        return []
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    entries = payload.get("slos") if isinstance(payload, Mapping) else None
    if not isinstance(entries, Sequence):
        return []
    definitions: list[SLODefinition] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        try:
            definition = SLODefinition(
                name=str(entry["name"]),
                description=str(entry.get("description", "")),
                target=float(entry.get("target", 0.0)),
                measure=str(entry.get("measure", entry["name"])),
                direction=str(entry.get("direction", ">=")).strip(),
                unit=str(entry.get("unit")) if entry.get("unit") else None,
            )
        except Exception:
            continue
        definitions.append(definition)
    return definitions


def load_definitions() -> list[SLODefinition]:
    candidates = [Path.cwd() / "config.slos.yaml", get_data_root() / "config.slos.yaml"]
    for candidate in candidates:
        if candidate.exists():
            loaded = _load_yaml_definitions(candidate)
            if loaded:
                return loaded
    return _load_default_definitions()


def _counter_total(snapshot: Mapping[str, float], prefix: str) -> float:
    total = 0.0
    for key, value in snapshot.items():
        if not key.startswith(prefix):
            continue
        total += float(value)
    return total


def _hist_samples(snapshot: Mapping[str, Sequence[float]], name: str) -> list[float]:
    for key, values in snapshot.items():
        if key.startswith(name):
            return list(values)
    return []


def _p95(samples: Sequence[float]) -> float:
    if not samples:
        return 0.0
    sorted_values = sorted(float(x) for x in samples)
    index = int(0.95 * (len(sorted_values) - 1))
    return sorted_values[index]


def evaluate(
    metrics: MetricsRegistry,
    modules: Mapping[str, Mapping[str, object]] | None = None,
    *,
    definitions: Sequence[SLODefinition] | None = None,
) -> list[SLOStatus]:
    definitions = list(definitions or load_definitions())
    snapshot = metrics.snapshot()
    counters = snapshot.get("counters", {})
    histograms = snapshot.get("histograms", {})
    modules = modules or {}
    statuses: list[SLOStatus] = []
    for definition in definitions:
        value = _compute_value(definition, counters, histograms, modules)
        ok = _compare(definition.direction, value, definition.target)
        unit_suffix = f" {definition.unit}" if definition.unit else ""
        message = f"{value:.4f}{unit_suffix} (target {definition.direction} {definition.target})"
        statuses.append(SLOStatus(definition=definition, value=value, ok=ok, message=message))
    return statuses


def _compute_value(
    definition: SLODefinition,
    counters: Mapping[str, float],
    histograms: Mapping[str, Sequence[float]],
    modules: Mapping[str, Mapping[str, object]],
) -> float:
    if definition.measure == "admin_availability":
        requests = counters.get("sos_admin_requests_total", 0.0)
        failures = counters.get("sos_admin_failures_total", 0.0)
        if requests <= 0:
            return 1.0
        return max(0.0, 1.0 - failures / requests)
    if definition.measure == "rehearsal_success_ratio":
        total = counters.get("sos_rehearsal_cycles_total", 0.0)
        failures = counters.get("sos_rehearsal_failures_total", 0.0)
        if total <= 0:
            return 1.0
        return max(0.0, min(1.0, 1.0 - failures / total))
    if definition.measure == "council_latency_p95":
        samples = _hist_samples(histograms, "sos_council_vote_latency_ms")
        return _p95(samples) / 1000.0
    if definition.measure == "critic_disagreement_rate":
        disagreements = counters.get("sos_critic_disagreements_total", 0.0)
        votes = _counter_total(counters, "sos_council_votes_total")
        if votes <= 0:
            return 0.0
        return max(0.0, disagreements / votes)
    if definition.measure == "hungry_eyes_freshness":
        module = modules.get("hungry_eyes", {}) if isinstance(modules, Mapping) else {}
        last = module.get("last_retrain") if isinstance(module, Mapping) else None
        if not last:
            return float("inf")
        try:
            timestamp = datetime.fromisoformat(str(last))
        except ValueError:
            return float("inf")
        delta = datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)
        return max(0.0, delta.total_seconds() / 86400.0)
    return counters.get(definition.measure, 0.0)


def _compare(direction: str, value: float, target: float) -> bool:
    if direction == ">=":
        return value >= target
    if direction == "<=":
        return value <= target
    return False


def to_prometheus(statuses: Iterable[SLOStatus]) -> str:
    lines: list[str] = []
    for status in statuses:
        definition = status.definition
        labels = f"name=\"{definition.name}\",target=\"{definition.target}\""
        lines.append("# TYPE sentientos_slo gauge")
        lines.append(f"sentientos_slo{{{labels}}} {1.0 if status.ok else 0.0}")
        lines.append("# TYPE sentientos_slo_value gauge")
        lines.append(f"sentientos_slo_value{{name=\"{definition.name}\"}} {status.value}")
    return "\n".join(lines)


def to_dict(statuses: Sequence[SLOStatus]) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for status in statuses:
        payload.append(
            {
                "name": status.definition.name,
                "description": status.definition.description,
                "target": status.definition.target,
                "direction": status.definition.direction,
                "unit": status.definition.unit,
                "value": status.value,
                "ok": status.ok,
                "message": status.message,
            }
        )
    return payload


__all__ = [
    "SLODefinition",
    "SLOStatus",
    "evaluate",
    "load_definitions",
    "to_dict",
    "to_prometheus",
]

