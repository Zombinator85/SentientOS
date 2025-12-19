from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Literal

Classification = Literal["advisory", "optional", "artifact-dependent"]
Status = Literal["passed", "failed", "skipped", "error"]


@dataclass(frozen=True)
class ToolClassification:
    tool: str
    classification: Classification
    non_blocking: bool
    description: str
    dependency: str | None = None

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        if self.dependency is None:
            data.pop("dependency")
        return data


@dataclass(frozen=True)
class ToolResult:
    tool: str
    classification: Classification
    status: Status
    non_blocking: bool
    reason: str | None = None
    dependency: str | None = None

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        if self.reason is None:
            data.pop("reason")
        if self.dependency is None:
            data.pop("dependency")
        return data


_CLASSIFICATIONS: dict[str, ToolClassification] = {
    "mypy": ToolClassification(
        tool="mypy",
        classification="advisory",
        non_blocking=True,
        description="Typing debt remains in legacy modules; treat failures as advisory until addressed.",
    ),
    "verify_audits": ToolClassification(
        tool="verify_audits",
        classification="optional",
        non_blocking=True,
        description="Audit verification relies on environment log availability; may be skipped when tooling is unavailable.",
    ),
    "audit_immutability_verifier": ToolClassification(
        tool="audit_immutability_verifier",
        classification="artifact-dependent",
        non_blocking=True,
        description="Requires immutable manifest artifacts; skip when the manifest is not provisioned.",
        dependency="/vow/immutable_manifest.json",
    ),
}


def get_classification(tool: str) -> ToolClassification:
    if tool not in _CLASSIFICATIONS:
        raise KeyError(f"Unknown tool classification for {tool}")
    return _CLASSIFICATIONS[tool]


def emit(tool: str | None = None) -> dict[str, dict[str, object]]:
    if tool is not None:
        classification = get_classification(tool)
        return {tool: classification.to_dict()}
    return {name: cls.to_dict() for name, cls in _CLASSIFICATIONS.items()}


def render_result(tool: str, status: Status, *, reason: str | None = None) -> dict[str, object]:
    cls = get_classification(tool)
    return ToolResult(
        tool=tool,
        classification=cls.classification,
        status=status,
        non_blocking=cls.non_blocking,
        reason=reason,
        dependency=cls.dependency,
    ).to_dict()


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Emit machine-readable tool classifications.",
    )
    parser.add_argument(
        "tool",
        nargs="?",
        help="Tool name to emit (default: all)",
        choices=sorted(_CLASSIFICATIONS.keys()),
    )
    args = parser.parse_args(argv)
    data = emit(args.tool)
    print(json.dumps(data, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
