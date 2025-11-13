"""Experiment chain definitions and persistence helpers."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Optional

from logging_config import get_log_path


@dataclass(frozen=True)
class ChainStep:
    """Single step in an experiment chain."""

    id: str
    on_success: Optional[str] = None
    on_failure: Optional[str] = None


@dataclass(frozen=True)
class ExperimentChain:
    """Representation of a deterministic experiment chain."""

    chain_id: str
    description: str
    start: str
    steps: Dict[str, ChainStep]
    max_steps: int = 32

    def __post_init__(self) -> None:
        if not self.chain_id:
            raise ValueError("chain_id must be provided")
        if not self.steps:
            raise ValueError("Experiment chain must define at least one step")
        if self.start not in self.steps:
            raise ValueError("start must reference a valid step id")
        if self.max_steps <= 0:
            raise ValueError("max_steps must be positive")
        for step_id, step in self.steps.items():
            if step.id != step_id:
                raise ValueError("Step mapping keys must match ChainStep ids")
            for target in (step.on_success, step.on_failure):
                if target is not None and target not in self.steps:
                    raise ValueError(
                        f"Step '{step_id}' references unknown target '{target}'"
                    )


CHAIN_SPEC_PATH = get_log_path("experiment_chains.json", "EXPERIMENT_CHAIN_FILE")
CHAIN_SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)


def _normalize_step_spec(step_id: str, spec: Mapping[str, object]) -> ChainStep:
    on_success = spec.get("on_success")
    on_failure = spec.get("on_failure")
    if on_success is not None and not isinstance(on_success, str):
        raise ValueError("on_success must be a string or null")
    if on_failure is not None and not isinstance(on_failure, str):
        raise ValueError("on_failure must be a string or null")
    return ChainStep(id=step_id, on_success=on_success, on_failure=on_failure)


def chain_from_spec(spec: Mapping[str, object]) -> ExperimentChain:
    """Construct an :class:`ExperimentChain` from a raw mapping."""

    try:
        chain_id = str(spec["chain_id"])  # type: ignore[index]
        description = str(spec.get("description", ""))
        start = str(spec["start"])  # type: ignore[index]
        steps_spec = spec["steps"]  # type: ignore[index]
    except KeyError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Missing required chain field: {exc}") from exc

    if not isinstance(steps_spec, Mapping):
        raise ValueError("steps must be a mapping of step ids to specifications")

    steps: Dict[str, ChainStep] = {}
    for step_id, step_info in steps_spec.items():
        if not isinstance(step_id, str):
            raise ValueError("Step ids must be strings")
        if not isinstance(step_info, Mapping):
            raise ValueError("Each step specification must be a mapping")
        steps[step_id] = _normalize_step_spec(step_id, step_info)

    max_steps_value = spec.get("max_steps", 32)
    if not isinstance(max_steps_value, int):
        raise ValueError("max_steps must be an integer")

    return ExperimentChain(
        chain_id=chain_id,
        description=description,
        start=start,
        steps=steps,
        max_steps=max_steps_value,
    )


def chain_to_spec(chain: ExperimentChain) -> Dict[str, object]:
    """Convert a chain to a JSON-serialisable specification."""

    return {
        "chain_id": chain.chain_id,
        "description": chain.description,
        "start": chain.start,
        "max_steps": chain.max_steps,
        "steps": {
            step_id: {
                "on_success": step.on_success,
                "on_failure": step.on_failure,
            }
            for step_id, step in chain.steps.items()
        },
    }


def _load_specs() -> Dict[str, Dict[str, object]]:
    if not CHAIN_SPEC_PATH.exists():
        return {}
    try:
        raw = json.loads(CHAIN_SPEC_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, Mapping):  # pragma: no cover - defensive
        return {}
    processed: Dict[str, Dict[str, object]] = {}
    for chain_id, spec in raw.items():
        if isinstance(chain_id, str) and isinstance(spec, Mapping):
            processed[chain_id] = dict(spec)
    return processed


def _save_specs(specs: Mapping[str, Mapping[str, object]]) -> None:
    serialisable = {key: dict(value) for key, value in specs.items()}
    CHAIN_SPEC_PATH.write_text(
        json.dumps(serialisable, indent=2, sort_keys=True), encoding="utf-8"
    )


def save_chain(chain: ExperimentChain) -> None:
    specs = _load_specs()
    specs[chain.chain_id] = chain_to_spec(chain)
    _save_specs(specs)


def delete_chain(chain_id: str) -> bool:
    specs = _load_specs()
    if chain_id not in specs:
        return False
    del specs[chain_id]
    _save_specs(specs)
    return True


def load_chain(chain_id: str) -> Optional[ExperimentChain]:
    specs = _load_specs()
    spec = specs.get(chain_id)
    if not spec:
        return None
    return chain_from_spec(spec)


def list_chains() -> Iterable[ExperimentChain]:
    specs = _load_specs()
    for spec in specs.values():
        yield chain_from_spec(spec)
