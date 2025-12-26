"""Evaluate alert rules for SentientOS operations."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .admin_server import RUNTIME
from .optional_deps import optional_import

from .metrics import MetricsRegistry
from .slo import evaluate as evaluate_slos
from .storage import get_data_root


@dataclass(frozen=True)
class AlertRule:
    name: str
    severity: str
    type: str
    params: Mapping[str, object]
    description: str = ""


@dataclass(frozen=True)
class Alert:
    name: str
    value: float
    message: str
    severity: str = "warning"

    def to_prometheus(self) -> str:
        labels = f"name=\"{self.name}\",severity=\"{self.severity}\""
        return "\n".join(
            [
                "# TYPE sentientos_alert gauge",
                f"sentientos_alert{{{labels}}} {self.value}",
            ]
        )


def _load_yaml_rule(path: Path) -> AlertRule | None:
    yaml = optional_import("pyyaml", feature="alert_rules")
    if yaml is None:
        return None
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, Mapping):
        return None
    try:
        return AlertRule(
            name=str(payload["name"]),
            severity=str(payload.get("severity", "warning")),
            type=str(payload.get("type", "metric_threshold")),
            params=dict(payload.get("params", {})),
            description=str(payload.get("description", "")),
        )
    except Exception:
        return None


def _default_rules() -> list[AlertRule]:
    return [
        AlertRule(
            name="HighReflexionTimeouts",
            severity="warning",
            type="metric_threshold",
            params={"metric": "sos_reflexion_latency_ms_max", "comparison": ">", "threshold": 2000.0},
        ),
        AlertRule(
            name="NoQuorum",
            severity="critical",
            type="metric_threshold",
            params={"metric": "sos_council_quorum_misses_total", "comparison": ">", "threshold": 0.0},
        ),
        AlertRule(
            name="OracleDegradedSustained",
            severity="critical",
            type="oracle_degraded",
            params={"minutes": 15},
        ),
        AlertRule(
            name="CuratorBacklogHigh",
            severity="warning",
            type="module_field_threshold",
            params={"module": "memory_curator", "field": "backlog", "comparison": ">", "threshold": 25},
        ),
        AlertRule(
            name="HungryEyesStaleModel",
            severity="warning",
            type="module_stale",
            params={"module": "hungry_eyes", "field": "last_retrain", "max_age_hours": 24 * 7},
        ),
        AlertRule(
            name="EventSignatureMismatches",
            severity="critical",
            type="metric_threshold",
            params={"metric": "sos_event_signature_mismatches_total", "comparison": ">", "threshold": 0.0},
        ),
    ]


def load_rules(directory: Path | None = None) -> list[AlertRule]:
    directory = directory or (Path.cwd() / "ops" / "alerts")
    if directory.exists():
        rules: list[AlertRule] = []
        for path in sorted(directory.glob("*.yml")) + sorted(directory.glob("*.yaml")):
            rule = _load_yaml_rule(path)
            if rule:
                rules.append(rule)
        if rules:
            return rules
    return _default_rules()


def _parse_metrics(metrics_text: str) -> Mapping[str, float]:
    metrics: dict[str, float] = {}
    for line in metrics_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if " " not in line:
            continue
        metric, value = line.rsplit(" ", 1)
        name = metric.split("{", 1)[0]
        try:
            metrics[name] = float(value)
        except ValueError:
            continue
    return metrics


def _compare(comparison: str, value: float, threshold: float) -> bool:
    if comparison == ">":
        return value > threshold
    if comparison == ">=":
        return value >= threshold
    if comparison == "<":
        return value < threshold
    if comparison == "<=":
        return value <= threshold
    return False


def evaluate_alerts(
    status: Mapping[str, object],
    metrics_text: str,
    *,
    rules: Sequence[AlertRule] | None = None,
    metrics_registry: MetricsRegistry | None = None,
) -> list[Alert]:
    rules = list(rules or load_rules())
    metrics = _parse_metrics(metrics_text)
    modules = status.get("modules", {}) if isinstance(status, Mapping) else {}
    registry = metrics_registry or RUNTIME.metrics
    slo_statuses = evaluate_slos(registry, modules if isinstance(modules, Mapping) else None)
    slo_lookup = {entry.definition.name: entry for entry in slo_statuses}
    alerts: list[Alert] = []
    for rule in rules:
        alert = _evaluate_rule(rule, status, modules, metrics, slo_lookup)
        alerts.append(alert)
    return alerts


def _evaluate_rule(
    rule: AlertRule,
    status: Mapping[str, object],
    modules: Mapping[str, object],
    metrics: Mapping[str, float],
    slo_lookup: Mapping[str, object],
) -> Alert:
    severity = rule.severity
    if rule.type == "metric_threshold":
        metric = str(rule.params.get("metric", ""))
        comparison = str(rule.params.get("comparison", ">"))
        threshold = float(rule.params.get("threshold", 0.0))
        value = metrics.get(metric, 0.0)
        firing = _compare(comparison, value, threshold)
        message = f"{metric}={value:.2f} {comparison} {threshold}"
        return Alert(rule.name, 1.0 if firing else 0.0, message, severity)
    if rule.type == "oracle_degraded":
        module = modules.get("oracle", {}) if isinstance(modules, Mapping) else {}
        status_value = module.get("status") if isinstance(module, Mapping) else None
        minutes = float(rule.params.get("minutes", 10))
        fired = False
        if status_value == "degraded":
            last = module.get("last_degraded_at")
            if last:
                try:
                    ts = datetime.fromisoformat(str(last))
                    age = datetime.now(timezone.utc) - ts.astimezone(timezone.utc)
                    fired = age >= timedelta(minutes=minutes)
                except ValueError:
                    fired = True
            else:
                fired = True
        message = "oracle degraded" if fired else "oracle healthy"
        return Alert(rule.name, 1.0 if fired else 0.0, message, severity)
    if rule.type == "module_field_threshold":
        module_name = str(rule.params.get("module", ""))
        field = str(rule.params.get("field", ""))
        comparison = str(rule.params.get("comparison", ">"))
        threshold = float(rule.params.get("threshold", 0.0))
        module = modules.get(module_name, {}) if isinstance(modules, Mapping) else {}
        value = 0.0
        if isinstance(module, Mapping) and field in module:
            try:
                value = float(module[field])
            except (TypeError, ValueError):
                value = 0.0
        fired = _compare(comparison, value, threshold)
        message = f"{module_name}.{field}={value:.2f} {comparison} {threshold}"
        return Alert(rule.name, 1.0 if fired else 0.0, message, severity)
    if rule.type == "module_stale":
        module_name = str(rule.params.get("module", ""))
        field = str(rule.params.get("field", "last_retrain"))
        max_age_hours = float(rule.params.get("max_age_hours", 24.0))
        module = modules.get(module_name, {}) if isinstance(modules, Mapping) else {}
        timestamp = module.get(field) if isinstance(module, Mapping) else None
        fired = False
        if timestamp:
            try:
                ts = datetime.fromisoformat(str(timestamp))
                age = datetime.now(timezone.utc) - ts.astimezone(timezone.utc)
                fired = age.total_seconds() > max_age_hours * 3600
            except ValueError:
                fired = True
        else:
            fired = True
        message = f"{module_name} stale" if fired else f"{module_name} fresh"
        return Alert(rule.name, 1.0 if fired else 0.0, message, severity)
    if rule.type == "slo_breach":
        name = str(rule.params.get("name", ""))
        entry = slo_lookup.get(name)
        breached = bool(entry and not entry.ok)
        message = entry.message if entry else "slo missing"
        return Alert(rule.name, 1.0 if breached else 0.0, message, severity)
    return Alert(rule.name, 0.0, "unsupported rule", severity)


def write_alerts(alerts: Iterable[Alert]) -> Mapping[str, str]:
    directory = get_data_root() / "glow" / "alerts"
    directory.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    for alert in alerts:
        path = directory / f"{alert.name}.prom"
        path.write_text(alert.to_prometheus() + "\n", encoding="utf-8")
        paths[alert.name] = str(path)
    return paths


def snapshot() -> Mapping[str, object]:
    status = RUNTIME.status()
    metrics_text = RUNTIME.export_metrics()
    alerts = evaluate_alerts({"modules": status.modules}, metrics_text, metrics_registry=RUNTIME.metrics)
    paths = write_alerts(alerts)
    return {
        "status": status.modules,
        "alerts": [alert.__dict__ for alert in alerts],
        "paths": paths,
    }


def _cmd_snapshot() -> int:
    payload = snapshot()
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_gauges() -> int:
    status = RUNTIME.status()
    metrics_text = RUNTIME.export_metrics()
    alerts = evaluate_alerts({"modules": status.modules}, metrics_text)
    output = "\n".join(alert.to_prometheus() for alert in alerts if alert.value >= 1.0)
    print(output)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate SentientOS alert rules")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("snapshot", help="Emit JSON snapshot of alert state")
    sub.add_parser("gauges", help="Print Prometheus gauges for firing alerts")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "gauges":
        return _cmd_gauges()
    return _cmd_snapshot()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())


__all__ = [
    "Alert",
    "AlertRule",
    "evaluate_alerts",
    "load_rules",
    "snapshot",
    "write_alerts",
]
