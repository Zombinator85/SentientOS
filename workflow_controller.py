"""Inert compatibility boundary for the retired executable workflow engine.

Workflow declarations are data, not authority to load source, import an action,
or invoke a Python callable.  This module remains importable because legacy
inspection modules still refer to its name; it deliberately performs no work at
import time and exposes no executable compatibility API.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import MappingProxyType
from typing import Any, NoReturn

from sentientos.optional_deps import optional_import


class WorkflowExecutionRetiredError(RuntimeError):
    """Raised when legacy workflow execution is requested."""


WORKFLOW_FILES: MappingProxyType[str, Path] = MappingProxyType({})
EVENT_PATH = Path(os.getenv("WORKFLOW_EVENT_PATH", "logs/memory/events.jsonl"))


def _load_yaml(text: str) -> dict[str, Any]:
    """Parse inert YAML for legacy read-only inspection consumers."""

    yaml = optional_import("pyyaml", feature="workflow_metadata_inspection")
    if yaml is None:
        raise RuntimeError("YAML metadata inspection requires PyYAML")
    value = yaml.safe_load(text)
    return value if isinstance(value, dict) else {}


def _retired(*_args: object, **_kwargs: object) -> NoReturn:
    raise WorkflowExecutionRetiredError(
        "generic executable workflows are retired; use an explicit typed effect contract"
    )


# Compatibility entry points fail before inspecting paths, declarations, or callables.
load_workflow_file = _retired
load_workflows = _retired
run_workflow = _retired
register_workflow = _retired
register_action = _retired
undo_last = _retired


def main() -> int:
    """Reject the retired CLI without parsing legacy execution options."""

    _retired()


if __name__ == "__main__":
    main()
