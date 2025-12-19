from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Iterable, Literal, Mapping, cast

Classification = Literal["mandatory", "advisory", "optional", "artifact-dependent"]
Status = Literal["passed", "failed", "skipped", "error", "missing"]
OverallStatus = Literal["PASS", "WARN", "FAIL"]

_SCHEMA_VERSION = "1.0"
_VALID_STATUSES: set[Status] = {"passed", "failed", "skipped", "error", "missing"}


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
    "pytest": ToolClassification(
        tool="pytest",
        classification="mandatory",
        non_blocking=False,
        description="Primary mandatory test suite.",
    ),
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


def _validate_status(status: str) -> Status:
    if status not in _VALID_STATUSES:
        raise ValueError(f"Unknown tool status '{status}'")
    return cast(Status, status)


def _coerce_tool_result(tool: str, payload: Mapping[str, object] | None) -> ToolResult:
    cls = get_classification(tool)
    if payload is None:
        return ToolResult(
            tool=tool,
            classification=cls.classification,
            status="missing",
            non_blocking=cls.non_blocking,
            reason="missing_result",
            dependency=cls.dependency,
        )
    status_value = payload.get("status")
    if not isinstance(status_value, str):
        raise ValueError(f"Tool '{tool}' payload missing status")
    status = _validate_status(status_value)
    reason = payload.get("reason")
    reason_str = reason if isinstance(reason, str) else None
    return ToolResult(
        tool=tool,
        classification=cls.classification,
        status=status,
        non_blocking=cls.non_blocking,
        reason=reason_str,
        dependency=cls.dependency,
    )


def _derive_overall(results: Iterable[ToolResult]) -> OverallStatus:
    has_advisory_issue = False
    for result in results:
        if result.classification == "mandatory" and result.status != "passed":
            return "FAIL"
        if result.classification == "advisory" and result.status != "passed":
            has_advisory_issue = True
    if has_advisory_issue:
        return "WARN"
    return "PASS"


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


@dataclass(frozen=True)
class ToolingStatusAggregate:
    schema_version: str
    overall_status: OverallStatus
    tools: dict[str, ToolResult]
    missing_tools: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "overall_status": self.overall_status,
            "tools": {name: result.to_dict() for name, result in self.tools.items()},
            "missing_tools": list(self.missing_tools),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


def aggregate_tooling_status(tool_payloads: Mapping[str, Mapping[str, object]]) -> ToolingStatusAggregate:
    unknown = set(tool_payloads) - set(_CLASSIFICATIONS)
    if unknown:
        raise KeyError(f"Unknown tooling results provided: {sorted(unknown)}")

    tools: dict[str, ToolResult] = {}
    missing: list[str] = []
    for name in sorted(_CLASSIFICATIONS.keys()):
        payload = tool_payloads.get(name)
        if payload is None:
            missing.append(name)
        tools[name] = _coerce_tool_result(name, payload)

    overall = _derive_overall(tools.values())
    return ToolingStatusAggregate(
        schema_version=_SCHEMA_VERSION,
        overall_status=overall,
        tools=tools,
        missing_tools=tuple(missing),
    )


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
