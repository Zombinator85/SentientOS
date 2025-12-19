from __future__ import annotations

import json
from hashlib import sha256
from dataclasses import asdict, dataclass, field
from typing import Iterable, Literal, Mapping, TypedDict, cast

Classification = Literal["mandatory", "advisory", "optional", "artifact-dependent"]
Status = Literal["passed", "failed", "skipped", "error", "missing"]
OverallStatus = Literal["PASS", "WARN", "FAIL"]


class ToolClassificationPayload(TypedDict):
    tool: str
    classification: Classification
    non_blocking: bool
    description: str
    dependency: str | None


class ToolResultPayload(TypedDict):
    tool: str
    classification: Classification
    status: Status
    non_blocking: bool
    reason: str | None
    dependency: str | None


class ToolingStatusAggregatePayload(TypedDict, total=False):
    schema_version: str
    overall_status: OverallStatus
    tools: dict[str, ToolResultPayload]
    missing_tools: list[str]
    lineage_parent_fingerprint: str
    lineage_relation: str

_SCHEMA_VERSION = "1.1"
_LINEAGE_SCHEMA_VERSION = "1.1"
_VALID_STATUSES: set[Status] = {"passed", "failed", "skipped", "error", "missing"}
_VALID_LINEAGE_RELATIONS: set[str] = {"supersedes", "amends", "recheck"}


@dataclass(frozen=True)
class SchemaDefinition:
    version: str
    aggregate_fields: tuple[str, ...]
    optional_aggregate_fields: tuple[str, ...]
    tool_fields: tuple[str, ...]
    classification_fields: tuple[str, ...]


@dataclass(frozen=True)
class ToolClassification:
    tool: str
    classification: Classification
    non_blocking: bool
    description: str
    dependency: str | None = None

    def to_dict(self) -> ToolClassificationPayload:
        data = asdict(self)
        return cast(ToolClassificationPayload, data)


@dataclass(frozen=True)
class ToolResult:
    tool: str
    classification: Classification
    status: Status
    non_blocking: bool
    reason: str | None = None
    dependency: str | None = None

    def to_dict(self) -> ToolResultPayload:
        data = asdict(self)
        return cast(ToolResultPayload, data)


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

TOOLING_STATUS_SCHEMA = SchemaDefinition(
    version=_SCHEMA_VERSION,
    aggregate_fields=("schema_version", "overall_status", "tools", "missing_tools"),
    optional_aggregate_fields=("lineage_parent_fingerprint", "lineage_relation"),
    tool_fields=(
        "tool",
        "classification",
        "status",
        "non_blocking",
        "reason",
        "dependency",
    ),
    classification_fields=(
        "tool",
        "classification",
        "non_blocking",
        "description",
        "dependency",
    ),
)


def get_classification(tool: str) -> ToolClassification:
    if tool not in _CLASSIFICATIONS:
        raise KeyError(f"Unknown tool classification for {tool}")
    return _CLASSIFICATIONS[tool]


def _validate_status(status: str) -> Status:
    if status not in _VALID_STATUSES:
        raise ValueError(f"Unknown tool status '{status}'")
    return cast(Status, status)


def _validate_fingerprint_value(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("fingerprint must be a string when provided")
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError("fingerprint must be a lowercase hexadecimal sha256 digest")
    return value


def _validate_lineage_relation(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("lineage_relation must be a string when provided")
    if value not in _VALID_LINEAGE_RELATIONS:
        raise ValueError(
            f"lineage_relation must be one of {sorted(_VALID_LINEAGE_RELATIONS)}"
        )
    return value


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
    lineage_parent_fingerprint: str | None = None
    lineage_relation: str | None = None
    forward_version_detected: bool = False
    forward_metadata: dict[str, object] = field(default_factory=dict)

    def canonical_dict(self) -> ToolingStatusAggregatePayload:
        payload: ToolingStatusAggregatePayload = {
            "schema_version": self.schema_version,
            "overall_status": self.overall_status,
            "tools": {
                name: result.to_dict() for name, result in sorted(self.tools.items())
            },
            "missing_tools": sorted(self.missing_tools),
        }
        if self.lineage_parent_fingerprint is not None:
            payload["lineage_parent_fingerprint"] = self.lineage_parent_fingerprint
        if self.lineage_relation is not None:
            payload["lineage_relation"] = self.lineage_relation
        return payload

    @property
    def fingerprint(self) -> str:
        canonical = self.canonical_dict()
        serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return sha256(serialized.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = dict(self.canonical_dict())
        payload["fingerprint"] = self.fingerprint
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


def _version_tuple(version: str) -> tuple[int, ...]:
    parts = version.split(".")
    if not all(part.isdigit() for part in parts):
        raise ValueError(f"Invalid schema version format: {version}")
    return tuple(int(part) for part in parts)


def _compare_versions(candidate: str, reference: str) -> int:
    candidate_tuple = _version_tuple(candidate)
    reference_tuple = _version_tuple(reference)
    max_len = max(len(candidate_tuple), len(reference_tuple))
    candidate_tuple = candidate_tuple + (0,) * (max_len - len(candidate_tuple))
    reference_tuple = reference_tuple + (0,) * (max_len - len(reference_tuple))
    if candidate_tuple == reference_tuple:
        return 0
    return 1 if candidate_tuple > reference_tuple else -1


def _validate_missing_tools(payload: object) -> tuple[str, ...]:
    if not isinstance(payload, list):
        raise ValueError("missing_tools must be a list of tool names")
    missing_tools: list[str] = []
    for entry in payload:
        if not isinstance(entry, str):
            raise ValueError("missing_tools entries must be strings")
        missing_tools.append(entry)
    return tuple(missing_tools)


def _parse_tool_payload(
    tool: str,
    payload: Mapping[str, object] | None,
    *,
    allow_unknown_fields: bool,
    tool_forward_metadata: dict[str, dict[str, object]],
) -> ToolResult:
    cls = get_classification(tool)
    if payload is None:
        if allow_unknown_fields:
            return _coerce_tool_result(tool, None)
        raise ValueError(f"Tool '{tool}' payload missing")
    if not isinstance(payload, Mapping):
        raise ValueError(f"Tool '{tool}' payload must be a mapping")

    required_fields = set(TOOLING_STATUS_SCHEMA.tool_fields)
    missing = required_fields - set(payload.keys())
    if missing:
        raise ValueError(f"Tool '{tool}' payload missing required fields: {sorted(missing)}")

    extra_fields = set(payload.keys()) - required_fields
    if extra_fields and allow_unknown_fields:
        tool_forward_metadata[tool] = {name: payload[name] for name in extra_fields}
    elif extra_fields:
        raise ValueError(
            f"Tool '{tool}' payload has unexpected fields: {sorted(extra_fields)}"
        )

    tool_name = payload.get("tool")
    if tool_name != tool:
        raise ValueError(f"Tool key '{tool}' payload has mismatched tool name '{tool_name}'")

    classification_value = payload.get("classification")
    if classification_value != cls.classification:
        raise ValueError(
            f"Tool '{tool}' classification '{classification_value}' does not match registered"
            f" value '{cls.classification}'"
        )

    non_blocking_value = payload.get("non_blocking")
    if not isinstance(non_blocking_value, bool):
        raise ValueError(f"Tool '{tool}' non_blocking must be a boolean")
    if non_blocking_value != cls.non_blocking:
        raise ValueError(
            f"Tool '{tool}' non_blocking value {non_blocking_value} does not match"
            f" registered value {cls.non_blocking}"
        )

    dependency_value = payload.get("dependency")
    if dependency_value != cls.dependency:
        raise ValueError(
            f"Tool '{tool}' dependency '{dependency_value}' does not match registered value"
            f" '{cls.dependency}'"
        )

    status_value = payload.get("status")
    if not isinstance(status_value, str):
        raise ValueError(f"Tool '{tool}' payload missing status")
    status = _validate_status(status_value)

    reason_value = payload.get("reason")
    if reason_value is not None and not isinstance(reason_value, str):
        raise ValueError(f"Tool '{tool}' reason must be a string when provided")

    return ToolResult(
        tool=tool,
        classification=cls.classification,
        status=status,
        non_blocking=cls.non_blocking,
        reason=reason_value,
        dependency=cls.dependency,
    )


def parse_tooling_status_payload(payload: Mapping[str, object]) -> ToolingStatusAggregate:
    if not isinstance(payload, Mapping):
        raise TypeError("Tooling status payload must be a mapping")

    schema_version_value = payload.get("schema_version")
    if not isinstance(schema_version_value, str):
        raise ValueError("Tooling status payload missing schema_version")

    version_comparison = _compare_versions(schema_version_value, TOOLING_STATUS_SCHEMA.version)
    forward_version_detected = version_comparison > 0
    backward_version_detected = version_comparison < 0
    lineage_supported = _compare_versions(schema_version_value, _LINEAGE_SCHEMA_VERSION) >= 0

    fingerprint_value = payload.get("fingerprint")
    if fingerprint_value is not None:
        fingerprint_value = _validate_fingerprint_value(fingerprint_value)

    required_fields = set(TOOLING_STATUS_SCHEMA.aggregate_fields)
    missing_fields = required_fields - set(payload.keys())
    if missing_fields:
        raise ValueError(
            f"Tooling status payload missing required fields: {sorted(missing_fields)}"
        )

    forward_metadata: dict[str, object] = {}
    allowed_optional_fields: set[str] = set()
    if lineage_supported:
        allowed_optional_fields.update(TOOLING_STATUS_SCHEMA.optional_aggregate_fields)

    extra_fields = (
        set(payload.keys()) - required_fields - allowed_optional_fields - {"fingerprint"}
    )
    if extra_fields and (forward_version_detected or backward_version_detected):
        forward_metadata["aggregate"] = {name: payload[name] for name in extra_fields}
    elif extra_fields:
        raise ValueError(f"Tooling status payload has unexpected fields: {sorted(extra_fields)}")

    overall_status_value = payload.get("overall_status")
    if not isinstance(overall_status_value, str):
        raise ValueError("overall_status must be a string")
    if not forward_version_detected and overall_status_value not in {"PASS", "WARN", "FAIL"}:
        raise ValueError(f"Unknown overall_status '{overall_status_value}'")
    overall_status = cast(OverallStatus, overall_status_value)

    tools_payload = payload.get("tools")
    if not isinstance(tools_payload, Mapping):
        raise ValueError("tools must be a mapping")

    missing_tools_value = payload.get("missing_tools")
    missing_tools = _validate_missing_tools(missing_tools_value)
    if not forward_version_detected:
        unexpected_missing = [name for name in missing_tools if name not in _CLASSIFICATIONS]
        if unexpected_missing:
            raise ValueError(
                f"missing_tools contains unknown entries: {sorted(unexpected_missing)}"
            )

    tools: dict[str, ToolResult] = {}
    tool_forward_metadata: dict[str, dict[str, object]] = {}
    for tool in sorted(_CLASSIFICATIONS.keys()):
        raw_tool_payload = tools_payload.get(tool)
        tools[tool] = _parse_tool_payload(
            tool,
            cast(Mapping[str, object] | None, raw_tool_payload),
            allow_unknown_fields=forward_version_detected,
            tool_forward_metadata=tool_forward_metadata,
        )

    unknown_tools = {name: data for name, data in tools_payload.items() if name not in tools}
    if unknown_tools and forward_version_detected:
        forward_metadata["tools"] = unknown_tools
    elif unknown_tools:
        raise ValueError(f"tools payload contained unknown entries: {sorted(unknown_tools)}")

    if tool_forward_metadata:
        forward_metadata["tool_fields"] = tool_forward_metadata

    lineage_parent: str | None = None
    lineage_relation: str | None = None
    lineage_parent_payload = payload.get("lineage_parent_fingerprint")
    lineage_relation_payload = payload.get("lineage_relation")
    if lineage_supported:
        if lineage_parent_payload is not None:
            lineage_parent = _validate_fingerprint_value(lineage_parent_payload)
        if lineage_relation_payload is not None:
            lineage_relation = _validate_lineage_relation(lineage_relation_payload)
            if lineage_parent is None:
                raise ValueError("lineage_relation provided without lineage_parent_fingerprint")
    elif lineage_parent_payload is not None or lineage_relation_payload is not None:
        forward_metadata["aggregate"] = {
            **forward_metadata.get("aggregate", {}),
            **{
                key: value
                for key, value in (
                    ("lineage_parent_fingerprint", lineage_parent_payload),
                    ("lineage_relation", lineage_relation_payload),
                )
                if value is not None
            },
        }

    aggregate = ToolingStatusAggregate(
        schema_version=schema_version_value,
        overall_status=overall_status,
        tools=tools,
        missing_tools=tuple(sorted(missing_tools)),
        lineage_parent_fingerprint=lineage_parent,
        lineage_relation=lineage_relation,
        forward_version_detected=forward_version_detected,
        forward_metadata=forward_metadata,
    )

    if fingerprint_value is not None and fingerprint_value != aggregate.fingerprint:
        raise ValueError("Tooling status fingerprint does not match canonical payload")

    if aggregate.lineage_parent_fingerprint is not None and (
        aggregate.lineage_parent_fingerprint == aggregate.fingerprint
    ):
        raise ValueError("Tooling status payload cannot reference itself as lineage parent")

    return aggregate


def aggregate_tooling_status(
    tool_payloads: Mapping[str, Mapping[str, object]],
    *,
    lineage_parent_fingerprint: str | None = None,
    lineage_relation: str | None = None,
) -> ToolingStatusAggregate:
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
    parent_value = _validate_fingerprint_value(lineage_parent_fingerprint) if lineage_parent_fingerprint else None
    relation_value = _validate_lineage_relation(lineage_relation) if lineage_relation else None
    if relation_value is not None and parent_value is None:
        raise ValueError("lineage_relation provided without lineage_parent_fingerprint")

    aggregate = ToolingStatusAggregate(
        schema_version=_SCHEMA_VERSION,
        overall_status=overall,
        tools=tools,
        missing_tools=tuple(sorted(missing)),
        lineage_parent_fingerprint=parent_value,
        lineage_relation=relation_value,
    )

    if aggregate.lineage_parent_fingerprint is not None and (
        aggregate.lineage_parent_fingerprint == aggregate.fingerprint
    ):
        raise ValueError("Tooling status payload cannot reference itself as lineage parent")

    return aggregate


def _to_aggregate(subject: ToolingStatusAggregate | Mapping[str, object]) -> ToolingStatusAggregate:
    if isinstance(subject, ToolingStatusAggregate):
        return subject
    return parse_tooling_status_payload(subject)


def fingerprint_tooling_status(subject: ToolingStatusAggregate | Mapping[str, object]) -> str:
    aggregate = _to_aggregate(subject)
    return aggregate.fingerprint


def tooling_status_equal(
    first: ToolingStatusAggregate | Mapping[str, object],
    second: ToolingStatusAggregate | Mapping[str, object],
) -> bool:
    return fingerprint_tooling_status(first) == fingerprint_tooling_status(second)


def tooling_status_supersedes(
    candidate: ToolingStatusAggregate | Mapping[str, object],
    reference: ToolingStatusAggregate | Mapping[str, object],
) -> bool:
    candidate_aggregate = _to_aggregate(candidate)
    reference_aggregate = _to_aggregate(reference)
    parent_fingerprint = candidate_aggregate.lineage_parent_fingerprint

    if parent_fingerprint is None:
        return False
    if parent_fingerprint == candidate_aggregate.fingerprint:
        raise ValueError("Lineage parent fingerprint matches candidate fingerprint")
    return parent_fingerprint == reference_aggregate.fingerprint


def validate_lineage_chain(
    aggregates: Iterable[ToolingStatusAggregate | Mapping[str, object]]
) -> None:
    parsed: list[ToolingStatusAggregate] = [_to_aggregate(entry) for entry in aggregates]
    seen: dict[str, ToolingStatusAggregate] = {}
    for aggregate in parsed:
        if aggregate.fingerprint in seen:
            raise ValueError("Duplicate fingerprints detected in lineage chain")
        seen[aggregate.fingerprint] = aggregate

    for aggregate in parsed:
        parent_fingerprint = aggregate.lineage_parent_fingerprint
        if parent_fingerprint is None:
            continue
        if parent_fingerprint == aggregate.fingerprint:
            raise ValueError("Self-referential lineage detected")

        visited: set[str] = set()
        current = parent_fingerprint
        while current is not None and current in seen:
            if current in visited:
                raise ValueError("Lineage cycle detected")
            visited.add(current)
            current = seen[current].lineage_parent_fingerprint

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
