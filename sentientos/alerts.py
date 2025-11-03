"""Operator alert synthesis built from admin status and metrics."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple

from .admin_server import admin_metrics, admin_status
from .storage import get_data_root


def _load_status() -> Mapping[str, object]:
    response = admin_status()
    return json.loads(response.body.decode("utf-8"))


def _load_metrics() -> str:
    response = admin_metrics()
    return response.body.decode("utf-8")


def _parse_prometheus(text: str) -> Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float]:
    metrics: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if " " not in line:
            continue
        metric, value = line.rsplit(" ", 1)
        if "{" in metric and metric.endswith("}"):
            name, label_str = metric[:-1].split("{", 1)
            labels = tuple(
                tuple(part.split("=", 1))
                for part in label_str.split(",")
                if "=" in part
            )
            labels = tuple((k, v.strip('"')) for k, v in labels)
        else:
            name = metric
            labels = tuple()
        try:
            numeric = float(value)
        except ValueError:
            continue
        metrics[(name, labels)] = numeric
    return metrics


def _ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _parse_iso8601(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@dataclass
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


def evaluate_alerts(status: Mapping[str, object], metrics_text: str) -> Iterable[Alert]:
    metrics = _parse_prometheus(metrics_text)
    modules = status.get("modules", {}) if isinstance(status, Mapping) else {}

    # Critic disagreements surge
    disagreements = metrics.get(("sos_critic_disagreements_total", tuple()), 0.0)
    yield Alert(
        name="critic_disagreements_surge",
        value=1.0 if disagreements > 0 else 0.0,
        message=f"critic disagreements observed: {int(disagreements)}",
    )

    # Oracle degraded duration
    oracle = modules.get("oracle", {}) if isinstance(modules, Mapping) else {}
    oracle_status = oracle.get("status")
    last_degraded_at = _parse_iso8601(str(oracle.get("last_degraded_at"))) if oracle.get("last_degraded_at") else None
    degraded_minutes = 0.0
    if last_degraded_at is not None:
        degraded_minutes = max(
            0.0,
            (datetime.now(timezone.utc) - last_degraded_at).total_seconds() / 60.0,
        )
    oracle_value = 1.0 if oracle_status == "degraded" and degraded_minutes >= 1.0 else 0.0
    yield Alert(
        name="oracle_degraded",
        value=oracle_value,
        message=f"oracle {oracle.get('mode', 'offline')} for {degraded_minutes:.1f}m",
    )

    # Council quorum misses ratio
    total_votes = sum(
        value
        for (name, _labels), value in metrics.items()
        if name == "sos_council_votes_total"
    )
    quorum_misses = metrics.get(("sos_council_quorum_misses_total", tuple()), 0.0)
    quorum_ratio = _ratio(quorum_misses, total_votes)
    yield Alert(
        name="council_quorum_miss_ratio",
        value=1.0 if quorum_ratio > 0.2 else 0.0,
        message=f"quorum miss ratio {quorum_ratio:.2f}",
    )

    # HungryEyes retrain overdue
    hungry = modules.get("hungry_eyes", {}) if isinstance(modules, Mapping) else {}
    last_retrain = _parse_iso8601(str(hungry.get("last_retrain"))) if hungry.get("last_retrain") else None
    overdue = True
    if last_retrain is not None:
        overdue = (datetime.now(timezone.utc) - last_retrain).total_seconds() > 3600.0
    yield Alert(
        name="hungryeyes_retrain_overdue",
        value=1.0 if overdue else 0.0,
        message="HungryEyes retrain overdue" if overdue else "HungryEyes retrain fresh",
    )


def write_alerts(alerts: Iterable[Alert]) -> Dict[str, Path]:
    directory = get_data_root() / "glow" / "alerts"
    directory.mkdir(parents=True, exist_ok=True)
    paths: Dict[str, Path] = {}
    for alert in alerts:
        path = directory / f"{alert.name}.prom"
        path.write_text(alert.to_prometheus() + "\n", encoding="utf-8")
        paths[alert.name] = path
    return paths


def snapshot() -> Dict[str, object]:
    status = _load_status()
    metrics = _load_metrics()
    alerts = list(evaluate_alerts(status, metrics))
    paths = write_alerts(alerts)
    return {
        "status": status,
        "alerts": [alert.__dict__ for alert in alerts],
        "paths": {name: str(path) for name, path in paths.items()},
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sentientos-alerts",
        description="Materialise alert state for operators",
    )
    parser.parse_args(argv)
    payload = snapshot()
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
