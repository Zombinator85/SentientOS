"""Utility helpers for running fully deterministic demo experiments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional

import copy
import json

import experiment_tracker

from sentientos.experiments.chain import ChainStep, ExperimentChain
from sentientos.experiments.consensus import compute_experiment_digest
from sentientos.experiments.runner import (
    ChainRunResult,
    ChainStepResult,
    run_chain,
)


ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEMO_DIR = ROOT_DIR / "demos"


@dataclass(frozen=True)
class DemoSummary:
    """Minimal information about a demo specification."""

    demo_id: str
    description: str
    path: Path


@dataclass
class DemoRun:
    """Return object describing a completed demo execution."""

    spec: Dict[str, object]
    chain: ExperimentChain
    result: ChainRunResult


def list_demos() -> List[DemoSummary]:
    """Return all available demo specifications sorted by identifier."""

    if not DEMO_DIR.exists():
        return []

    summaries: List[DemoSummary] = []
    for path in sorted(DEMO_DIR.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, Mapping):
            continue
        chain_id = str(raw.get("chain_id") or path.stem)
        description = str(raw.get("description") or "").strip()
        summaries.append(DemoSummary(chain_id, description, path))
    return sorted(summaries, key=lambda item: item.demo_id)


def _load_demo_spec(name: str) -> Dict[str, object]:
    path = DEMO_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Demo specification '{name}' not found")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Invalid JSON in demo '{name}': {exc}") from exc
    if not isinstance(data, Mapping):
        raise ValueError(f"Demo '{name}' must be a JSON object")
    spec = dict(data)
    spec.setdefault("chain_id", name)
    return spec


def _load_records() -> List[Dict[str, object]]:
    path = experiment_tracker.DATA_FILE
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    return []


def _save_records(records: Iterable[Dict[str, object]]) -> None:
    path = experiment_tracker.DATA_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    serialisable = [dict(item) for item in records]
    path.write_text(json.dumps(serialisable, indent=2), encoding="utf-8")


def _ensure_mock_adapter(record: Dict[str, object]) -> None:
    adapter = record.get("adapter")
    if isinstance(adapter, Mapping):
        adapter_name = adapter.get("name") or adapter.get("adapter")
    else:
        adapter_name = adapter
    if adapter_name is None:
        record["adapter"] = "mock"
        adapter_name = "mock"
    if adapter_name != "mock":
        raise ValueError("Demo experiments must use the mock adapter")


def _deepcopy_if_needed(value):
    if isinstance(value, (dict, list)):
        return copy.deepcopy(value)
    return value


def _prepare_record(step_id: str, spec: Mapping[str, object], existing: Optional[Dict[str, object]]) -> Dict[str, object]:
    now = datetime.utcnow().isoformat()
    description = str(spec.get("description") or (existing or {}).get("description") or step_id)
    conditions = str(spec.get("conditions") or (existing or {}).get("conditions") or "demo conditions")
    expected = str(spec.get("expected") or (existing or {}).get("expected") or "demo outcome")

    requires_consensus = bool(spec.get("requires_consensus") or (existing or {}).get("requires_consensus", False))
    quorum_k = int(spec.get("quorum_k") or (existing or {}).get("quorum_k", 1) or 1)
    quorum_k = max(1, quorum_k)
    quorum_n_default = max(quorum_k, (existing or {}).get("quorum_n", quorum_k))
    quorum_n = int(spec.get("quorum_n") or quorum_n_default or quorum_k)
    quorum_n = max(quorum_k, quorum_n)

    record: Dict[str, object] = {
        "id": step_id,
        "description": description,
        "conditions": conditions,
        "expected": expected,
        "status": str(spec.get("status") or (existing or {}).get("status") or "active"),
        "votes": copy.deepcopy((existing or {}).get("votes", {})),
        "comments": copy.deepcopy((existing or {}).get("comments", [])),
        "triggers": int((existing or {}).get("triggers", 0)),
        "success": int((existing or {}).get("success", 0)),
        "proposer": (existing or {}).get("proposer", "demo"),
        "proposed_at": (existing or {}).get("proposed_at", now),
        "requires_consensus": requires_consensus,
        "quorum_k": quorum_k,
        "quorum_n": quorum_n,
    }

    criteria = spec.get("criteria")
    if criteria is not None:
        record["criteria"] = str(criteria)
    elif existing and "criteria" in existing:
        record["criteria"] = existing["criteria"]

    for field in ("adapter", "adapters", "action", "actions", "measure", "measures", "metadata", "mock_context"):
        if field in spec:
            record[field] = _deepcopy_if_needed(spec[field])
        elif existing and field in existing:
            record[field] = _deepcopy_if_needed(existing[field])

    _ensure_mock_adapter(record)
    record["digest"] = compute_experiment_digest(record)
    return record


def _upsert_experiment(step_id: str, exp_spec: Mapping[str, object]) -> Dict[str, object]:
    records = _load_records()
    existing: Optional[Dict[str, object]] = None
    for item in records:
        if item.get("id") == step_id:
            existing = item
            break

    record = _prepare_record(step_id, exp_spec, existing)

    if existing is None or existing != record:
        updated_records: List[Dict[str, object]] = []
        replaced = False
        for item in records:
            if item.get("id") == step_id:
                updated_records.append(record)
                replaced = True
            else:
                updated_records.append(item)
        if not replaced:
            updated_records.append(record)
        _save_records(updated_records)
        audit = getattr(experiment_tracker, "_audit", None)
        if callable(audit):
            action = "demo_update" if existing else "demo_create"
            audit(action, step_id, source="demo_gallery")
    return record


def _build_chain(spec: Mapping[str, object]) -> ExperimentChain:
    try:
        chain_id = str(spec["chain_id"])
        start = str(spec["start"])
        steps_spec = spec["steps"]  # type: ignore[index]
    except KeyError as exc:
        raise ValueError(f"Demo spec missing required field: {exc}") from exc

    if not isinstance(steps_spec, Mapping):
        raise ValueError("Demo steps must be a mapping")

    steps: Dict[str, ChainStep] = {}
    for step_id, raw_step in steps_spec.items():
        if not isinstance(step_id, str):
            raise ValueError("Demo step identifiers must be strings")
        if not isinstance(raw_step, Mapping):
            raise ValueError(f"Step '{step_id}' must be a mapping")
        steps[step_id] = ChainStep(
            id=step_id,
            on_success=raw_step.get("on_success"),
            on_failure=raw_step.get("on_failure"),
        )

    description = str(spec.get("description", f"Demo chain {chain_id}"))
    max_steps = int(spec.get("max_steps", max(32, len(steps) * 2)))
    return ExperimentChain(
        chain_id=chain_id,
        description=description,
        start=start,
        steps=steps,
        max_steps=max_steps,
    )


def _prepare_experiments(spec: Mapping[str, object]) -> Dict[str, Dict[str, object]]:
    steps_spec = spec.get("steps")
    if not isinstance(steps_spec, Mapping):
        raise ValueError("Demo steps must be defined")

    records: Dict[str, Dict[str, object]] = {}
    for step_id, raw_step in steps_spec.items():
        if not isinstance(raw_step, Mapping):
            raise ValueError(f"Step '{step_id}' must be a mapping")
        exp_spec = raw_step.get("experiment")
        if not isinstance(exp_spec, Mapping):
            raise ValueError(f"Step '{step_id}' missing 'experiment' specification")
        record = _upsert_experiment(step_id, exp_spec)
        records[step_id] = record
    return records


def run_demo(
    name: str,
    *,
    stream: Optional[Callable[[str], None]] = None,
) -> DemoRun:
    """Execute a demo by chain identifier and return the run result."""

    spec = _load_demo_spec(name)
    _prepare_experiments(spec)
    chain = _build_chain(spec)

    if stream is None:
        stream = lambda message: None  # type: ignore[assignment]

    def _progress(step_result: ChainStepResult) -> None:
        step = chain.steps.get(step_result.experiment_id)
        if step_result.success is True:
            status = "SUCCESS"
            next_step = step.on_success if step else None
        elif step_result.success is False:
            status = "FAILURE"
            next_step = step.on_failure if step else None
        else:
            status = step_result.error or "SKIPPED"
            next_step = None

        prefix = f"[demo {chain.chain_id}]"
        if next_step:
            stream(
                f"{prefix} step {step_result.step_index}: {step_result.experiment_id} → {status} → next {next_step}"
            )
        else:
            stream(
                f"{prefix} step {step_result.step_index}: {step_result.experiment_id} → {status} → chain complete"
            )

    result = run_chain(chain, progress_callback=_progress)

    return DemoRun(spec=spec, chain=chain, result=result)

