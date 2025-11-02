"""Adaptive anomaly detector used by :mod:`sentientos.daemons.integrity_daemon`.

The HungryEyes sentinel observes amendment events and learns from the
``proof_report``/``probe_report`` artefacts emitted by the integrity pipeline.
The implementation intentionally avoids heavyweight ML dependencies; instead it
derives a simple logistic model from historical ledger/quarantine entries.  The
resulting risk score is deterministic, reproducible, and explainable because it
is based on a small set of covenant-aligned features (violation counts,
invariant flags, probe results, etc.).

The module provides three main building blocks:

``HungryEyesDatasetBuilder``
    Parses ledger JSONL entries or quarantine payloads into normalised training
    examples.

``HungryEyesSentinel``
    Learns a risk model from the dataset and exposes :meth:`assess` for use by
    :class:`sentientos.daemons.integrity_daemon.IntegrityDaemon`.

``extract_features``
    Stateless helper that turns an amendment event into the feature vector used
    during both training and inference.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Mapping

import json
import math


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value is None:
        return []
    return [value]


def _as_mapping(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def extract_features(event: Mapping[str, object]) -> dict[str, float]:
    """Derive numerical features from an integrity event.

    The feature set intentionally mirrors the covenant invariants so that the
    resulting weights remain interpretable.  All values are scaled into the
    ``[0, 1]`` range so that the logistic model can be trained without needing
    external normalisation steps.
    """

    payload = _as_mapping(event)
    proof = _as_mapping(payload.get("proof_report"))
    probe = _as_mapping(payload.get("probe_report") or payload.get("probe"))

    violations = [
        _as_mapping(item)
        for item in _as_list(proof.get("violations"))
        if isinstance(item, Mapping)
    ]
    trace = [item for item in _as_list(proof.get("trace")) if isinstance(item, Mapping)]

    total_checks = len(trace)
    violation_count = len(violations)
    critical_count = sum(
        1 for item in violations if str(item.get("severity", "")).lower() == "critical"
    )

    invariants = {str(item.get("invariant", "")).lower() for item in violations}

    def _flag(name: str) -> float:
        return 1.0 if name in invariants else 0.0

    removed_keys = _as_list(probe.get("removed_keys"))
    truncated_lists = _as_list(probe.get("truncated_lists"))

    def _bool_flag(mapping: Mapping[str, object], key: str) -> float:
        return 1.0 if bool(mapping.get(key)) else 0.0

    features: dict[str, float] = {
        "violation_density": float(violation_count) / float(total_checks or 1),
        "violation_count": float(violation_count),
        "critical_count": float(critical_count),
        "structural_integrity_flag": _flag("structural_integrity"),
        "audit_continuity_flag": _flag("audit_continuity"),
        "forbidden_status_flag": _flag("forbidden_status"),
        "recursion_guard_flag": _flag("recursion_guard"),
        "probe_removed_keys": float(len(removed_keys)),
        "probe_truncated_lists": float(len(truncated_lists)),
        "probe_lineage_missing": _bool_flag(probe, "lineage_missing"),
        "probe_ledger_removed": _bool_flag(probe, "ledger_removed"),
        "probe_forbidden_status": 1.0 if probe.get("forbidden_status") else 0.0,
        "probe_summary_blank": _bool_flag(probe, "summary_blank"),
        "probe_recursion_break": _bool_flag(probe, "recursion_break"),
        "proof_valid": 1.0 if bool(proof.get("valid")) else 0.0,
    }

    summary = payload.get("summary")
    if isinstance(summary, str):
        features["summary_length"] = float(len(summary))
    elif isinstance(summary, Mapping):
        synopsis = summary.get("text")
        if isinstance(synopsis, str):
            features["summary_length"] = float(len(synopsis))

    return features


@dataclass(frozen=True)
class HungryEyesTrainingExample:
    """Container representing a single labelled observation."""

    features: dict[str, float]
    label: int


class HungryEyesDatasetBuilder:
    """Utility that assembles :class:`HungryEyesTrainingExample` instances."""

    def __init__(self) -> None:
        self._examples: list[HungryEyesTrainingExample] = []

    def add_event(self, event: Mapping[str, object]) -> None:
        features = extract_features(event)
        label = 1 if self._is_violation(event) else 0
        self._examples.append(HungryEyesTrainingExample(features, label))

    def add_many(self, events: Iterable[Mapping[str, object]]) -> None:
        for event in events:
            self.add_event(event)

    def load_jsonl(self, path: Path | str) -> None:
        path = Path(path)
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, Mapping):
                    self.add_event(event)

    def load_directory(self, path: Path | str) -> None:
        path = Path(path)
        if not path.exists() or not path.is_dir():
            return
        for entry in sorted(path.iterdir()):
            if entry.is_file() and entry.suffix in {".json", ".jsonl"}:
                try:
                    data = json.loads(entry.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
                if isinstance(data, Mapping):
                    self.add_event(data)

    def build(self) -> list[HungryEyesTrainingExample]:
        return list(self._examples)

    @staticmethod
    def _is_violation(event: Mapping[str, object]) -> bool:
        status = str(event.get("status", "")).upper()
        if status in {"QUARANTINED", "VIOLATION", "REJECTED"}:
            return True
        proof = _as_mapping(event.get("proof_report"))
        if not proof.get("valid", True):
            return True
        violations = _as_list(proof.get("violations"))
        return bool(violations)


class HungryEyesSentinel:
    """Lightweight logistic model that scores amendment risk."""

    _EPSILON = 1e-6
    _VALID_MODES = {"observe", "repair", "full", "expand"}

    def __init__(self, mode: str = "observe", *, threshold: float = 0.5, retrain_window: int = 10) -> None:
        self.mode = mode
        self.threshold = float(threshold)
        self._weights: dict[str, float] = {}
        self._bias: float = 0.0
        self._fitted = False
        self._dataset: list[HungryEyesTrainingExample] = []
        self._pending: list[HungryEyesTrainingExample] = []
        self._retrain_window = max(1, int(retrain_window))

    def fit(self, examples: Iterable[HungryEyesTrainingExample]) -> None:
        examples = list(examples)
        self._dataset = list(examples)
        if not examples:
            self._weights = {}
            self._bias = 0.0
            self._fitted = False
            return

        positives: dict[str, float] = {}
        negatives: dict[str, float] = {}
        pos_total = self._EPSILON
        neg_total = self._EPSILON

        for example in examples:
            if example.label:
                pos_total += 1.0
                target = positives
            else:
                neg_total += 1.0
                target = negatives
            for name, value in example.features.items():
                if value == 0:
                    continue
                target[name] = target.get(name, self._EPSILON) + float(value)

        feature_names = set(positives) | set(negatives)
        if not feature_names:
            # With no informative features, fall back to the base rate.
            self._weights = {}
            self._bias = math.log(max(pos_total, self._EPSILON) / max(neg_total, self._EPSILON))
            self._fitted = True
            return

        weights: dict[str, float] = {}
        for name in feature_names:
            pos_mean = positives.get(name, self._EPSILON) / pos_total
            neg_mean = negatives.get(name, self._EPSILON) / neg_total
            weights[name] = math.log(max(pos_mean, self._EPSILON) / max(neg_mean, self._EPSILON))

        self._weights = weights
        self._bias = math.log(max(pos_total, self._EPSILON) / max(neg_total, self._EPSILON))
        self._fitted = True

    def observe(self, event: Mapping[str, object]) -> dict[str, object]:
        """Update the dataset with a new event and retrain if needed."""

        builder = HungryEyesDatasetBuilder()
        builder.add_event(event)
        example = builder.build()[0]
        self._dataset.append(example)
        self._pending.append(example)
        if len(self._pending) >= self._retrain_window:
            self.fit(self._dataset)
            self._pending.clear()
        if not self._fitted:
            return {
                "mode": self.mode,
                "risk": 0.0,
                "threshold": self.threshold,
                "features": example.features,
                "contributions": {},
            }
        return self.assess(event)

    def assess(self, event: Mapping[str, object]) -> dict[str, object]:
        if not self._fitted:
            raise RuntimeError("HungryEyesSentinel must be fitted before assessment")
        features = extract_features(event)
        score = self._bias
        contributions: dict[str, float] = {}
        for name, value in features.items():
            weight = self._weights.get(name)
            if weight is None or value == 0:
                continue
            contribution = weight * value
            contributions[name] = contribution
            score += contribution
        risk = 1.0 / (1.0 + math.exp(-score))
        return {
            "mode": self.mode,
            "risk": float(min(max(risk, 0.0), 1.0)),
            "threshold": self.threshold,
            "features": features,
            "contributions": contributions,
        }

    @property
    def fitted(self) -> bool:
        return self._fitted

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        normalised = str(value or "observe").lower()
        if normalised not in self._VALID_MODES:
            raise ValueError(
                "HungryEyesSentinel mode must be one of: "
                + ", ".join(sorted(self._VALID_MODES))
            )
        self._mode = normalised

    def snapshot(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "threshold": self.threshold,
            "weights": dict(self._weights),
            "bias": self._bias,
            "fitted": self._fitted,
            "dataset_size": len(self._dataset),
        }

    @property
    def dataset_size(self) -> int:
        return len(self._dataset)


def iter_quarantine_payloads(path: Path | str) -> Iterator[dict[str, object]]:
    """Yield JSON payloads stored inside a quarantine directory."""

    path = Path(path)
    if not path.exists() or not path.is_dir():
        return iter(())

    def _iterator() -> Iterator[dict[str, object]]:
        for entry in sorted(path.glob("*.json")):
            try:
                payload = json.loads(entry.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload

    return _iterator()
