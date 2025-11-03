"""Minimal metrics registry producing Prometheus exposition text."""

from __future__ import annotations

import json
import threading
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, MutableMapping, Tuple

from .storage import get_data_root

_LabelTuple = Tuple[Tuple[str, str], ...]


def _label_tuple(labels: Mapping[str, str] | None) -> _LabelTuple:
    if not labels:
        return tuple()
    return tuple(sorted((str(key), str(value)) for key, value in labels.items()))


@dataclass
class Histogram:
    name: str
    samples: list[float]

    def observe(self, value: float) -> None:
        self.samples.append(float(value))

    def export(self, labels: _LabelTuple) -> str:
        if not self.samples:
            return ""
        count = len(self.samples)
        total = sum(self.samples)
        maximum = max(self.samples)
        label_str = "" if not labels else "{" + ",".join(f"{k}=\"{v}\"" for k, v in labels) + "}"
        return "\n".join(
            [
                f"# TYPE {self.name} histogram",
                f"{self.name}_count{label_str} {count}",
                f"{self.name}_sum{label_str} {total}",
                f"{self.name}_max{label_str} {maximum}",
            ]
        )


class MetricsRegistry:
    """Thread-safe metrics registry used by rehearsal automation."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: MutableMapping[Tuple[str, _LabelTuple], float] = defaultdict(float)
        self._gauges: MutableMapping[Tuple[str, _LabelTuple], float] = {}
        self._histograms: Dict[Tuple[str, _LabelTuple], Histogram] = {}

    def increment(self, name: str, value: float = 1.0, *, labels: Mapping[str, str] | None = None) -> None:
        key = (name, _label_tuple(labels))
        with self._lock:
            self._counters[key] += float(value)

    def set_gauge(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        key = (name, _label_tuple(labels))
        with self._lock:
            self._gauges[key] = float(value)

    def observe(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        key = (name, _label_tuple(labels))
        with self._lock:
            hist = self._histograms.get(key)
            if hist is None:
                hist = Histogram(name, [])
                self._histograms[key] = hist
            hist.observe(value)

    def export_prometheus(self) -> str:
        with self._lock:
            lines: list[str] = []
            for (name, labels), value in sorted(self._counters.items()):
                label_str = "" if not labels else "{" + ",".join(f"{k}=\"{v}\"" for k, v in labels) + "}"
                lines.append(f"# TYPE {name} counter")
                lines.append(f"{name}{label_str} {value}")
            for (name, labels), value in sorted(self._gauges.items()):
                label_str = "" if not labels else "{" + ",".join(f"{k}=\"{v}\"" for k, v in labels) + "}"
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name}{label_str} {value}")
            for (name, labels), hist in sorted(self._histograms.items()):
                output = hist.export(labels)
                if output:
                    lines.append(output)
            return "\n".join(lines)

    def snapshot(self) -> dict:
        with self._lock:
            counters = {
                name + _format_labels(labels): value
                for (name, labels), value in self._counters.items()
            }
            gauges = {
                name + _format_labels(labels): value
                for (name, labels), value in self._gauges.items()
            }
            histograms = {
                name + _format_labels(labels): hist.samples[:]
                for (name, labels), hist in self._histograms.items()
            }
            return {"counters": counters, "gauges": gauges, "histograms": histograms}

    def persist_prometheus(self, name: str = "autonomy.prom") -> Path:
        metrics_dir = get_data_root() / "glow" / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        path = metrics_dir / name
        path.write_text(self.export_prometheus(), encoding="utf-8")
        return path

    def persist_snapshot(self, name: str = "metrics.snap") -> Path:
        metrics_dir = get_data_root() / "glow" / "rehearsal" / "latest"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        path = metrics_dir / name
        path.write_text(json.dumps(self.snapshot(), indent=2), encoding="utf-8")
        return path


def _format_labels(labels: _LabelTuple) -> str:
    if not labels:
        return ""
    return "{" + ",".join(f"{k}={v}" for k, v in labels) + "}"


__all__ = ["MetricsRegistry"]
