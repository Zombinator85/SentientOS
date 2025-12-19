from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from hashlib import sha256
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


class ProvenanceAttestationPayload(TypedDict, total=False):
    attestation_version: str
    producer_id: str
    producer_type: str
    constraints: dict[str, str]


class ToolingStatusAggregatePayload(TypedDict, total=False):
    schema_version: str
    overall_status: OverallStatus
    tools: dict[str, ToolResultPayload]
    missing_tools: list[str]
    lineage_parent_fingerprint: str
    lineage_relation: str
    provenance_attestation: ProvenanceAttestationPayload | None


class ToolingStatusPolicyPayload(TypedDict, total=False):
    schema_version: str
    allowed_overall_statuses: list[OverallStatus]
    allowed_producer_types: list[str]
    required_redaction_profile: str
    maximum_advisory_issues: int


class PolicyLayerPayload(TypedDict):
    name: str
    priority: int
    policy: ToolingStatusPolicyPayload


class PolicyCompositionPayload(TypedDict):
    schema_version: str
    layers: list[PolicyLayerPayload]
    overall_status_rule: str
    producer_type_rule: str
    advisory_issue_rule: str
    redaction_profile_rule: str


class PolicyDecisionPayload(TypedDict):
    outcome: "PolicyDecisionOutcome"
    reasons: list[str]


class PolicyDecisionRuleTracePayload(TypedDict, total=False):
    name: "TraceRuleName"
    outcome: "TraceRuleOutcome"
    observed: str
    expected: object
    rationale: str | None


class PolicyOverrideTracePayload(TypedDict):
    dimension: str
    mode: str
    selected: tuple[str, ...] | int | None
    considered: tuple[tuple[str, tuple[str, ...] | int | None], ...]
    discarded: tuple[tuple[str, ...] | int | None, ...]


class PolicyDecisionTracePayload(TypedDict):
    schema_version: str
    profile: str
    aggregate: ToolingStatusAggregatePayload
    evaluated_rules: list[PolicyDecisionRuleTracePayload]
    matched_conditions: list[str]
    applied_overrides: list[PolicyOverrideTracePayload]
    rejected_alternatives: list[str]


class PolicyEvaluationOptionsPayload(TypedDict):
    emit_trace: bool
    use_cache: bool


class PolicyEvaluationSnapshotPayloadRequired(TypedDict):
    schema_version: str
    profile: str
    aggregate: ToolingStatusAggregatePayload
    aggregate_fingerprint: str
    policy: ToolingStatusPolicyPayload
    policy_forward_metadata: dict[str, object]
    policy_fingerprint: str
    decision: PolicyDecisionPayload
    trace: PolicyDecisionTracePayload | None
    options: PolicyEvaluationOptionsPayload


class PolicyEvaluationSnapshotPayload(PolicyEvaluationSnapshotPayloadRequired, total=False):
    parent_snapshot_fingerprint: str
    lineage_relation: str
    review_notes: str
    snapshot_fingerprint: str
    evaluation_fingerprint: str

_SCHEMA_VERSION = "1.2"
_ATTESTATION_SCHEMA_VERSION = "1.2"
_LINEAGE_SCHEMA_VERSION = "1.1"
_SNAPSHOT_SCHEMA_VERSION = "1.1"
_SNAPSHOT_LINEAGE_SCHEMA_VERSION = "1.1"
_VALID_STATUSES: set[Status] = {"passed", "failed", "skipped", "error", "missing"}
_VALID_LINEAGE_RELATIONS: set[str] = {"supersedes", "amends", "annotates", "recheck"}
_AUTHORITATIVE_SNAPSHOT_RELATIONS: set[str] = {"supersedes", "amends"}
_VALID_PRODUCER_TYPES: set[str] = {"local", "ci", "sandbox", "pipeline", "adhoc"}
_REDACTED_MARKER = "<redacted>"
_REDACTED_FINGERPRINT = "0" * 64
_POLICY_SCHEMA_VERSION = "1.0"
_POLICY_COMPOSITION_SCHEMA_VERSION = "1.0"
_TRACE_SCHEMA_VERSION = "1.0"
_MAX_REVIEW_NOTES_LENGTH = 2048


class _PolicyEvaluationCache:
    def __init__(self, *, max_entries: int = 64) -> None:
        self._max_entries = max_entries
        self._store: OrderedDict[
            tuple[str, str, str, bool],
            tuple["PolicyDecision", "PolicyDecisionTrace | None"],
        ] = OrderedDict()
        self.hits = 0

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._store)

    def get(
        self, key: tuple[str, str, str, bool]
    ) -> tuple["PolicyDecision", "PolicyDecisionTrace | None"] | None:
        cached = self._store.get(key)
        if cached is None:
            return None
        self.hits += 1
        self._store.move_to_end(key)
        return cached

    def set(
        self,
        key: tuple[str, str, str, bool],
        value: tuple["PolicyDecision", "PolicyDecisionTrace | None"],
    ) -> None:
        self._store[key] = value
        self._store.move_to_end(key)
        if len(self._store) > self._max_entries:
            self._store.popitem(last=False)


_POLICY_EVALUATION_CACHE = _PolicyEvaluationCache()


@dataclass(frozen=True)
class RedactionProfileConfig:
    include_reason: bool
    include_dependency: bool
    include_lineage_parent: bool
    include_attestation_details: bool
    include_review_notes: bool


class RedactionProfile(Enum):
    FULL = ("full", "1", RedactionProfileConfig(True, True, True, True, True))
    SAFE = ("safe", "1", RedactionProfileConfig(False, False, True, False, False))
    MINIMAL = ("minimal", "1", RedactionProfileConfig(False, False, False, False, False))

    def __init__(self, profile_name: str, version: str, config: RedactionProfileConfig):
        self.profile_name = profile_name
        self.version = version
        self.config = config

    @property
    def fingerprint_scope(self) -> str:
        return f"{self.profile_name}.v{self.version}"


@dataclass(frozen=True)
class SchemaDefinition:
    version: str
    aggregate_fields: tuple[str, ...]
    optional_aggregate_fields: tuple[str, ...]
    tool_fields: tuple[str, ...]
    classification_fields: tuple[str, ...]


@dataclass(frozen=True)
class ToolingStatusPolicy:
    schema_version: str
    allowed_overall_statuses: tuple[OverallStatus, ...]
    allowed_producer_types: tuple[str, ...] | None
    required_redaction_profile: RedactionProfile | None
    maximum_advisory_issues: int | None
    forward_metadata: dict[str, object] = field(default_factory=dict)


class PolicyOverrideMode(Enum):
    RESTRICTIVE_WINS = "restrictive_wins"
    EXPLICIT_WIDEN = "explicit_widen"
    MOST_SEVERE_WINS = "most_severe_wins"


@dataclass(frozen=True)
class PolicyLayer:
    name: str
    priority: int
    policy: ToolingStatusPolicy


@dataclass(frozen=True)
class ToolingStatusPolicyComposition:
    schema_version: str
    layers: tuple[PolicyLayer, ...]
    overall_status_rule: PolicyOverrideMode
    producer_type_rule: PolicyOverrideMode
    advisory_issue_rule: PolicyOverrideMode
    redaction_profile_rule: PolicyOverrideMode


PolicyDecisionOutcome = Literal["ACCEPT", "WARN", "REJECT"]


@dataclass(frozen=True)
class PolicyDecision:
    outcome: PolicyDecisionOutcome
    reasons: tuple[str, ...] = ()


TraceRuleName = Literal[
    "overall_status",
    "producer_type",
    "redaction_profile",
    "advisory_issues",
]

TraceRuleOutcome = Literal["match", "warn", "reject"]
_TRACE_RULE_NAMES: tuple[TraceRuleName, ...] = (
    "overall_status",
    "producer_type",
    "redaction_profile",
    "advisory_issues",
)
_TRACE_RULE_OUTCOMES: tuple[TraceRuleOutcome, ...] = ("match", "warn", "reject")


@dataclass(frozen=True)
class PolicyDecisionRuleTrace:
    name: TraceRuleName
    outcome: TraceRuleOutcome
    observed: str
    expected: tuple[str, ...] | int | None = None
    rationale: str | None = None


@dataclass(frozen=True)
class PolicyOverrideTrace:
    dimension: Literal[
        "overall_status",
        "producer_type",
        "advisory_issues",
        "redaction_profile",
    ]
    mode: PolicyOverrideMode
    selected: tuple[str, ...] | int | None
    considered: tuple[tuple[str, tuple[str, ...] | int | None], ...]
    discarded: tuple[tuple[str, ...] | int | None, ...]


@dataclass(frozen=True)
class PolicyDecisionTrace:
    schema_version: str
    profile: RedactionProfile
    aggregate: ToolingStatusAggregatePayload
    evaluated_rules: tuple[PolicyDecisionRuleTrace, ...]
    matched_conditions: tuple[str, ...]
    applied_overrides: tuple[PolicyOverrideTrace, ...]
    rejected_alternatives: tuple[str, ...]


@dataclass(frozen=True)
class PolicyEvaluationOptions:
    profile: RedactionProfile
    emit_trace: bool
    use_cache: bool


@dataclass(frozen=True)
class PolicyEvaluationSnapshot:
    schema_version: str
    aggregate: "ToolingStatusAggregate"
    policy: ToolingStatusPolicy
    aggregate_fingerprint: str
    policy_fingerprint: str
    decision: PolicyDecision
    trace: PolicyDecisionTrace | None
    options: PolicyEvaluationOptions
    parent_snapshot_fingerprint: str | None = None
    lineage_relation: str | None = None
    review_notes: str | None = None

    @property
    def evaluation_fingerprint(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "profile": self.options.profile.fingerprint_scope,
            "aggregate_fingerprint": self.aggregate_fingerprint,
            "policy_fingerprint": self.policy_fingerprint,
            "decision": _decision_to_payload(self.decision),
            "trace": _trace_to_payload(self.trace),
            "options": {
                "emit_trace": self.options.emit_trace,
                "use_cache": self.options.use_cache,
            },
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return sha256(serialized.encode("utf-8")).hexdigest()

    def _redacted_parent_fingerprint(self) -> str | None:
        if self.parent_snapshot_fingerprint is None:
            return None
        if self.options.profile.config.include_lineage_parent:
            return self.parent_snapshot_fingerprint
        return _REDACTED_FINGERPRINT

    def _redacted_review_notes(self) -> str | None:
        if self.review_notes is None:
            return None
        if self.options.profile.config.include_review_notes:
            return self.review_notes
        return _REDACTED_MARKER

    @property
    def fingerprint(self) -> str:
        payload = {
            "evaluation_fingerprint": self.evaluation_fingerprint,
            "parent_snapshot_fingerprint": self._redacted_parent_fingerprint(),
            "lineage_relation": self.lineage_relation,
            "review_notes": self._redacted_review_notes(),
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return sha256(serialized.encode("utf-8")).hexdigest()

    def to_payload(self) -> PolicyEvaluationSnapshotPayload:
        payload: PolicyEvaluationSnapshotPayload = {
            "schema_version": self.schema_version,
            "profile": self.options.profile.profile_name,
            "aggregate": _serialize_payload(
                self.aggregate.profiled_payload(self.options.profile)
            ),
            "aggregate_fingerprint": self.aggregate_fingerprint,
            "policy": _serialize_payload(_policy_to_payload(self.policy)),
            "policy_forward_metadata": _serialize_payload(self.policy.forward_metadata),
            "policy_fingerprint": self.policy_fingerprint,
            "decision": cast(PolicyDecisionPayload, _decision_to_payload(self.decision)),
            "trace": _trace_to_payload(self.trace),
            "options": cast(
                PolicyEvaluationOptionsPayload,
                {
                    "emit_trace": self.options.emit_trace,
                    "use_cache": self.options.use_cache,
                },
            ),
            "evaluation_fingerprint": self.evaluation_fingerprint,
            "snapshot_fingerprint": self.fingerprint,
        }
        if self.parent_snapshot_fingerprint is not None:
            payload["parent_snapshot_fingerprint"] = self._redacted_parent_fingerprint()
        if self.lineage_relation is not None:
            payload["lineage_relation"] = self.lineage_relation
        if self.review_notes is not None:
            payload["review_notes"] = self._redacted_review_notes()
        return payload


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
    aggregate_fields=(
        "schema_version",
        "overall_status",
        "tools",
        "missing_tools",
        "provenance_attestation",
    ),
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


def _validate_producer_id(value: object, *, allow_redacted: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError("producer_id must be a string when provided")
    if allow_redacted and value == _REDACTED_MARKER:
        return value
    if not value or any(ch.isspace() for ch in value):
        raise ValueError("producer_id must be a non-empty string without whitespace")
    return value


def _validate_producer_type(value: object, *, allow_redacted: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError("producer_type must be a string when provided")
    if allow_redacted and value == _REDACTED_MARKER:
        return value
    if value not in _VALID_PRODUCER_TYPES:
        raise ValueError(
            f"producer_type must be one of {sorted(_VALID_PRODUCER_TYPES)}"
        )
    return value


def _validate_constraints(value: object, *, allow_redacted: bool = False) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("constraints must be a mapping of string keys to string values")
    constraints: dict[str, str] = {}
    for key, entry in value.items():
        if not isinstance(key, str) or not isinstance(entry, str):
            raise ValueError("constraints keys and values must be strings")
        if allow_redacted and entry == _REDACTED_MARKER:
            constraints[key] = entry
            continue
        constraints[key] = entry
    return dict(sorted(constraints.items()))


def _redaction_profile_from_name(name: str) -> RedactionProfile:
    for profile in RedactionProfile:
        if profile.profile_name == name:
            return profile
    raise ValueError(
        f"required_redaction_profile must be one of {[profile.profile_name for profile in RedactionProfile]}"
    )


def parse_tooling_status_policy(payload: Mapping[str, object]) -> ToolingStatusPolicy:
    if not isinstance(payload, Mapping):
        raise TypeError("Policy payload must be a mapping")

    schema_version_value = payload.get("schema_version")
    if not isinstance(schema_version_value, str):
        raise ValueError("Policy payload missing schema_version")

    version_comparison = _compare_versions(schema_version_value, _POLICY_SCHEMA_VERSION)
    forward_version_detected = version_comparison > 0
    backward_version_detected = version_comparison < 0

    allowed_overall_statuses_value = payload.get("allowed_overall_statuses")
    if not isinstance(allowed_overall_statuses_value, list) or not allowed_overall_statuses_value:
        raise ValueError("allowed_overall_statuses must be a non-empty list")
    allowed_overall_statuses: list[OverallStatus] = []
    for entry in allowed_overall_statuses_value:
        if not isinstance(entry, str):
            raise ValueError("allowed_overall_statuses entries must be strings")
        if not forward_version_detected and entry not in {"PASS", "WARN", "FAIL"}:
            raise ValueError(
                "allowed_overall_statuses entries must be one of ['PASS', 'WARN', 'FAIL']"
            )
        allowed_overall_statuses.append(cast(OverallStatus, entry))

    allowed_producer_types_value = payload.get("allowed_producer_types")
    allowed_producer_types: tuple[str, ...] | None = None
    if allowed_producer_types_value is not None:
        if not isinstance(allowed_producer_types_value, list) or not allowed_producer_types_value:
            raise ValueError("allowed_producer_types must be a non-empty list when provided")
        producer_types: list[str] = []
        for entry in allowed_producer_types_value:
            if not isinstance(entry, str):
                raise ValueError("allowed_producer_types entries must be strings")
            if not forward_version_detected and entry not in _VALID_PRODUCER_TYPES:
                raise ValueError(
                    f"allowed_producer_types entries must be one of {sorted(_VALID_PRODUCER_TYPES)}"
                )
            producer_types.append(entry)
        allowed_producer_types = tuple(sorted(set(producer_types)))

    required_redaction_profile_value = payload.get("required_redaction_profile")
    required_redaction_profile: RedactionProfile | None = None
    if required_redaction_profile_value is not None:
        if not isinstance(required_redaction_profile_value, str):
            raise ValueError("required_redaction_profile must be a string when provided")
        required_redaction_profile = _redaction_profile_from_name(required_redaction_profile_value)

    maximum_advisory_issues_value = payload.get("maximum_advisory_issues")
    maximum_advisory_issues: int | None = None
    if maximum_advisory_issues_value is not None:
        if not isinstance(maximum_advisory_issues_value, int) or maximum_advisory_issues_value < 0:
            raise ValueError("maximum_advisory_issues must be a non-negative integer when provided")
        maximum_advisory_issues = maximum_advisory_issues_value

    known_fields = {
        "schema_version",
        "allowed_overall_statuses",
        "allowed_producer_types",
        "required_redaction_profile",
        "maximum_advisory_issues",
    }
    extra_fields = set(payload.keys()) - known_fields
    forward_metadata: dict[str, object] = {}
    if extra_fields and (forward_version_detected or backward_version_detected):
        forward_metadata = {name: payload[name] for name in sorted(extra_fields)}
    elif extra_fields:
        raise ValueError(f"Policy payload has unexpected fields: {sorted(extra_fields)}")

    return ToolingStatusPolicy(
        schema_version=schema_version_value,
        allowed_overall_statuses=tuple(sorted(set(allowed_overall_statuses))),
        allowed_producer_types=allowed_producer_types,
        required_redaction_profile=required_redaction_profile,
        maximum_advisory_issues=maximum_advisory_issues,
        forward_metadata=forward_metadata,
    )


def _parse_override_mode(
    value: object,
    *,
    field: str,
    allowed: tuple[PolicyOverrideMode, ...],
) -> PolicyOverrideMode:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    try:
        mode = PolicyOverrideMode(value)
    except ValueError:
        raise ValueError(
            f"{field} must be one of {[entry.value for entry in allowed]}"
        ) from None
    if mode not in allowed:
        raise ValueError(f"{field} must be one of {[entry.value for entry in allowed]}")
    return mode


def _parse_policy_layer(payload: Mapping[str, object]) -> PolicyLayer:
    if not isinstance(payload, Mapping):
        raise TypeError("Policy layer must be a mapping")
    name = payload.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("Policy layer missing name")
    priority = payload.get("priority")
    if not isinstance(priority, int):
        raise ValueError("Policy layer priority must be an integer")
    policy_payload = payload.get("policy")
    if not isinstance(policy_payload, Mapping):
        raise ValueError("Policy layer missing policy payload")
    return PolicyLayer(
        name=name,
        priority=priority,
        policy=parse_tooling_status_policy(policy_payload),
    )


def parse_tooling_status_policy_composition(
    payload: Mapping[str, object]
) -> ToolingStatusPolicyComposition:
    if not isinstance(payload, Mapping):
        raise TypeError("Policy composition payload must be a mapping")
    schema_version_value = payload.get("schema_version")
    if not isinstance(schema_version_value, str):
        raise ValueError("Policy composition payload missing schema_version")
    if _compare_versions(schema_version_value, _POLICY_COMPOSITION_SCHEMA_VERSION) != 0:
        raise ValueError(
            f"Unsupported policy composition schema version {schema_version_value}"
        )

    layers_value = payload.get("layers")
    if not isinstance(layers_value, list) or not layers_value:
        raise ValueError("Policy composition requires at least one layer")
    parsed_layers = tuple(_parse_policy_layer(entry) for entry in layers_value)
    priorities = {}
    for layer in parsed_layers:
        if layer.name in priorities:
            raise ValueError(f"Duplicate policy layer name '{layer.name}'")
        if layer.priority in priorities.values():
            raise ValueError("Policy layer priorities must be unique")
        priorities[layer.name] = layer.priority

    overall_status_rule = _parse_override_mode(
        payload.get("overall_status_rule"),
        field="overall_status_rule",
        allowed=(
            PolicyOverrideMode.RESTRICTIVE_WINS,
            PolicyOverrideMode.EXPLICIT_WIDEN,
            PolicyOverrideMode.MOST_SEVERE_WINS,
        ),
    )
    producer_type_rule = _parse_override_mode(
        payload.get("producer_type_rule"),
        field="producer_type_rule",
        allowed=(
            PolicyOverrideMode.RESTRICTIVE_WINS,
            PolicyOverrideMode.EXPLICIT_WIDEN,
        ),
    )
    advisory_issue_rule = _parse_override_mode(
        payload.get("advisory_issue_rule"),
        field="advisory_issue_rule",
        allowed=(
            PolicyOverrideMode.RESTRICTIVE_WINS,
            PolicyOverrideMode.EXPLICIT_WIDEN,
        ),
    )
    redaction_profile_rule = _parse_override_mode(
        payload.get("redaction_profile_rule"),
        field="redaction_profile_rule",
        allowed=(
            PolicyOverrideMode.RESTRICTIVE_WINS,
            PolicyOverrideMode.EXPLICIT_WIDEN,
        ),
    )

    return ToolingStatusPolicyComposition(
        schema_version=schema_version_value,
        layers=tuple(sorted(parsed_layers, key=lambda layer: (layer.priority, layer.name))),
        overall_status_rule=overall_status_rule,
        producer_type_rule=producer_type_rule,
        advisory_issue_rule=advisory_issue_rule,
        redaction_profile_rule=redaction_profile_rule,
    )


@dataclass(frozen=True)
class ProvenanceAttestation:
    attestation_version: str
    producer_id: str
    producer_type: str
    constraints: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> ProvenanceAttestationPayload:
        return {
            "attestation_version": self.attestation_version,
            "producer_id": self.producer_id,
            "producer_type": self.producer_type,
            "constraints": dict(sorted(self.constraints.items())),
        }


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
    provenance_attestation: ProvenanceAttestation | None = None
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
        payload["provenance_attestation"] = (
            self.provenance_attestation.to_dict()
            if self.provenance_attestation is not None
            else None
        )
        if self.lineage_parent_fingerprint is not None:
            payload["lineage_parent_fingerprint"] = self.lineage_parent_fingerprint
        if self.lineage_relation is not None:
            payload["lineage_relation"] = self.lineage_relation
        return payload

    def profiled_payload(
        self, profile: RedactionProfile = RedactionProfile.FULL
    ) -> ToolingStatusAggregatePayload:
        payload = self.canonical_dict()
        if profile is RedactionProfile.FULL:
            return payload

        if "provenance_attestation" in payload:
            attestation_payload = payload["provenance_attestation"]
            if attestation_payload is not None and not profile.config.include_attestation_details:
                payload["provenance_attestation"] = cast(
                    ProvenanceAttestationPayload,
                    {
                        "attestation_version": attestation_payload["attestation_version"],
                        "producer_id": _REDACTED_MARKER,
                        "producer_type": _REDACTED_MARKER,
                        "constraints": {
                            key: _REDACTED_MARKER for key in attestation_payload["constraints"].keys()
                        },
                    },
                )

        redacted_tools: dict[str, ToolResultPayload] = {}
        for name, tool_payload in payload["tools"].items():
            updated_payload = dict(tool_payload)
            if not profile.config.include_reason and updated_payload.get("reason") is not None:
                updated_payload["reason"] = _REDACTED_MARKER
            if (
                not profile.config.include_dependency
                and updated_payload.get("dependency") is not None
            ):
                updated_payload["dependency"] = _REDACTED_MARKER
            redacted_tools[name] = cast(ToolResultPayload, updated_payload)

        redacted_payload: ToolingStatusAggregatePayload = {
            **payload,
            "tools": redacted_tools,
        }

        if (
            not profile.config.include_lineage_parent
            and "lineage_parent_fingerprint" in redacted_payload
        ):
            redacted_payload["lineage_parent_fingerprint"] = _REDACTED_FINGERPRINT

        return redacted_payload

    def fingerprint_for_profile(self, profile: RedactionProfile = RedactionProfile.FULL) -> str:
        payload = self.profiled_payload(profile)
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if profile is RedactionProfile.FULL:
            return sha256(serialized.encode("utf-8")).hexdigest()
        scoped_payload = f"{profile.fingerprint_scope}:{serialized}"
        return sha256(scoped_payload.encode("utf-8")).hexdigest()

    @property
    def fingerprint(self) -> str:
        return self.fingerprint_for_profile(RedactionProfile.FULL)

    def to_dict(self, profile: RedactionProfile = RedactionProfile.FULL) -> dict[str, object]:
        payload: dict[str, object] = dict(self.profiled_payload(profile))
        payload["fingerprint"] = self.fingerprint_for_profile(profile)
        return payload

    def to_json(self, profile: RedactionProfile = RedactionProfile.FULL) -> str:
        return json.dumps(self.to_dict(profile), sort_keys=True)


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
    profile: RedactionProfile,
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
        if profile.config.include_dependency or dependency_value != _REDACTED_MARKER:
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


def parse_tooling_status_payload(
    payload: Mapping[str, object], *, profile: RedactionProfile = RedactionProfile.FULL
) -> ToolingStatusAggregate:
    if not isinstance(payload, Mapping):
        raise TypeError("Tooling status payload must be a mapping")

    schema_version_value = payload.get("schema_version")
    if not isinstance(schema_version_value, str):
        raise ValueError("Tooling status payload missing schema_version")

    version_comparison = _compare_versions(schema_version_value, TOOLING_STATUS_SCHEMA.version)
    forward_version_detected = version_comparison > 0
    backward_version_detected = version_comparison < 0
    lineage_supported = _compare_versions(schema_version_value, _LINEAGE_SCHEMA_VERSION) >= 0
    attestation_supported = (
        _compare_versions(schema_version_value, _ATTESTATION_SCHEMA_VERSION) >= 0
    )

    fingerprint_value = payload.get("fingerprint")
    if fingerprint_value is not None:
        fingerprint_value = _validate_fingerprint_value(fingerprint_value)

    required_fields = set(TOOLING_STATUS_SCHEMA.aggregate_fields)
    if not attestation_supported:
        required_fields.remove("provenance_attestation")
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
            profile=profile,
        )

    unknown_tools = {name: data for name, data in tools_payload.items() if name not in tools}
    if unknown_tools and forward_version_detected:
        forward_metadata["tools"] = unknown_tools
    elif unknown_tools:
        raise ValueError(f"tools payload contained unknown entries: {sorted(unknown_tools)}")

    if tool_forward_metadata:
        forward_metadata["tool_fields"] = tool_forward_metadata

    provenance_attestation_payload = payload.get("provenance_attestation")
    provenance_attestation: ProvenanceAttestation | None = None
    if attestation_supported:
        if provenance_attestation_payload is None:
            provenance_attestation = None
        else:
            if not isinstance(provenance_attestation_payload, Mapping):
                raise ValueError("provenance_attestation must be a mapping when provided")
            attestation_version_value = provenance_attestation_payload.get("attestation_version")
            if not isinstance(attestation_version_value, str):
                raise ValueError("provenance_attestation.attestation_version must be provided")
            producer_id_value = _validate_producer_id(
                provenance_attestation_payload.get("producer_id"),
                allow_redacted=not profile.config.include_attestation_details,
            )
            producer_type_value = _validate_producer_type(
                provenance_attestation_payload.get("producer_type"),
                allow_redacted=not profile.config.include_attestation_details,
            )
            constraints_value = _validate_constraints(
                provenance_attestation_payload.get("constraints", {}),
                allow_redacted=not profile.config.include_attestation_details,
            )
            known_fields = {
                "attestation_version",
                "producer_id",
                "producer_type",
                "constraints",
            }
            extra_attestation_fields = (
                set(provenance_attestation_payload.keys()) - known_fields
            )
            if extra_attestation_fields and (forward_version_detected or backward_version_detected):
                forward_metadata["provenance_attestation"] = {
                    name: provenance_attestation_payload[name]
                    for name in sorted(extra_attestation_fields)
                }
            elif extra_attestation_fields:
                raise ValueError(
                    "provenance_attestation has unexpected fields: "
                    f"{sorted(extra_attestation_fields)}"
                )
            provenance_attestation = ProvenanceAttestation(
                attestation_version=attestation_version_value,
                producer_id=producer_id_value,
                producer_type=producer_type_value,
                constraints=constraints_value,
            )
    elif provenance_attestation_payload is not None:
        forward_metadata["aggregate"] = {
            **forward_metadata.get("aggregate", {}),
            "provenance_attestation": provenance_attestation_payload,
        }

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
        provenance_attestation=provenance_attestation,
        lineage_parent_fingerprint=lineage_parent,
        lineage_relation=lineage_relation,
        forward_version_detected=forward_version_detected,
        forward_metadata=forward_metadata,
    )

    aggregate_fingerprint = aggregate.fingerprint_for_profile(profile)

    if fingerprint_value is not None and fingerprint_value != aggregate_fingerprint:
        raise ValueError("Tooling status fingerprint does not match canonical payload")

    if aggregate.lineage_parent_fingerprint is not None and (
        aggregate.lineage_parent_fingerprint == aggregate_fingerprint
    ):
        raise ValueError("Tooling status payload cannot reference itself as lineage parent")

    return aggregate


def aggregate_tooling_status(
    tool_payloads: Mapping[str, Mapping[str, object]],
    *,
    lineage_parent_fingerprint: str | None = None,
    lineage_relation: str | None = None,
    provenance_attestation: ProvenanceAttestation | Mapping[str, object] | None = None,
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
    attestation_value: ProvenanceAttestation | None = None
    if provenance_attestation is not None:
        if isinstance(provenance_attestation, ProvenanceAttestation):
            attestation_value = provenance_attestation
        else:
            attestation_version_payload = provenance_attestation.get(
                "attestation_version"
            )
            if not isinstance(attestation_version_payload, str):
                raise ValueError("provenance_attestation.attestation_version must be provided")
            attestation_value = ProvenanceAttestation(
                attestation_version=attestation_version_payload,
                producer_id=_validate_producer_id(provenance_attestation.get("producer_id")),
                producer_type=_validate_producer_type(provenance_attestation.get("producer_type")),
                constraints=_validate_constraints(provenance_attestation.get("constraints", {})),
            )
    parent_value = _validate_fingerprint_value(lineage_parent_fingerprint) if lineage_parent_fingerprint else None
    relation_value = _validate_lineage_relation(lineage_relation) if lineage_relation else None
    if relation_value is not None and parent_value is None:
        raise ValueError("lineage_relation provided without lineage_parent_fingerprint")

    aggregate = ToolingStatusAggregate(
        schema_version=_SCHEMA_VERSION,
        overall_status=overall,
        tools=tools,
        missing_tools=tuple(sorted(missing)),
        provenance_attestation=attestation_value,
        lineage_parent_fingerprint=parent_value,
        lineage_relation=relation_value,
    )

    if aggregate.lineage_parent_fingerprint is not None and (
        aggregate.lineage_parent_fingerprint == aggregate.fingerprint
    ):
        raise ValueError("Tooling status payload cannot reference itself as lineage parent")

    return aggregate


def _to_aggregate(
    subject: ToolingStatusAggregate | Mapping[str, object],
    *,
    profile: RedactionProfile = RedactionProfile.FULL,
) -> ToolingStatusAggregate:
    if isinstance(subject, ToolingStatusAggregate):
        return subject
    return parse_tooling_status_payload(subject, profile=profile)


def _to_policy(policy: ToolingStatusPolicy | Mapping[str, object]) -> ToolingStatusPolicy:
    if isinstance(policy, ToolingStatusPolicy):
        return policy
    if isinstance(policy, Mapping):
        return parse_tooling_status_policy(policy)
    raise TypeError("Policy must be a ToolingStatusPolicy or mapping")


def _redaction_matches_profile(
    aggregate: ToolingStatusAggregate, profile: RedactionProfile
) -> bool:
    return aggregate.canonical_dict() == aggregate.profiled_payload(profile)


def _count_advisory_issues(aggregate: ToolingStatusAggregate) -> int:
    return sum(
        1
        for result in aggregate.tools.values()
        if result.classification == "advisory" and result.status != "passed"
    )


def _compose_allowed_statuses(
    layers: Iterable[PolicyLayer], mode: PolicyOverrideMode
) -> tuple[OverallStatus, ...]:
    status_sets = [set(layer.policy.allowed_overall_statuses) for layer in layers]
    if not status_sets:
        raise ValueError("At least one policy layer is required")

    if mode is PolicyOverrideMode.RESTRICTIVE_WINS:
        result = set.intersection(*status_sets)
        if not result:
            raise ValueError(
                "No allowed_overall_statuses remain after restrictive composition"
            )
        return tuple(sorted(result))

    if mode is PolicyOverrideMode.EXPLICIT_WIDEN:
        return tuple(sorted(set().union(*status_sets)))

    if mode is PolicyOverrideMode.MOST_SEVERE_WINS:
        severity = {"PASS": 0, "WARN": 1, "FAIL": 2}
        worst_allowed = max(max(severity[status] for status in entries) for entries in status_sets)
        return tuple(
            sorted(
                {status for status, level in severity.items() if level <= worst_allowed}
            )
        )

    raise ValueError(f"Unsupported override mode {mode.value}")


def _compose_producer_types(
    layers: Iterable[PolicyLayer], mode: PolicyOverrideMode
) -> tuple[str, ...] | None:
    producer_sets: list[set[str]] = []
    unrestricted = False
    for layer in layers:
        if layer.policy.allowed_producer_types is None:
            unrestricted = True
            continue
        producer_sets.append(set(layer.policy.allowed_producer_types))

    if not producer_sets:
        return None

    if mode is PolicyOverrideMode.RESTRICTIVE_WINS:
        baseline = set(_VALID_PRODUCER_TYPES)
        result = baseline.intersection(*producer_sets)
        if not result:
            raise ValueError("Producer type composition removed all allowed types")
        return tuple(sorted(result))

    if mode is PolicyOverrideMode.EXPLICIT_WIDEN:
        result = set().union(*producer_sets)
        if unrestricted and not result:
            return None
        if unrestricted and result == set(_VALID_PRODUCER_TYPES):
            return None
        return tuple(sorted(result)) if result else None

    raise ValueError("Unsupported producer type override mode")


def _compose_advisory_limits(
    layers: Iterable[PolicyLayer], mode: PolicyOverrideMode
) -> int | None:
    limits = [layer.policy.maximum_advisory_issues for layer in layers]
    finite_limits = [limit for limit in limits if limit is not None]
    if mode is PolicyOverrideMode.RESTRICTIVE_WINS:
        return min(finite_limits) if finite_limits else None
    if mode is PolicyOverrideMode.EXPLICIT_WIDEN:
        if any(limit is None for limit in limits):
            return None
        return max(finite_limits) if finite_limits else None
    raise ValueError("Unsupported advisory issue override mode")


def _redaction_restriction_rank(profile: RedactionProfile) -> int:
    if profile is RedactionProfile.MINIMAL:
        return 2
    if profile is RedactionProfile.SAFE:
        return 1
    return 0


def _compose_redaction_profile(
    layers: Iterable[PolicyLayer], mode: PolicyOverrideMode
) -> RedactionProfile | None:
    profiles = [layer.policy.required_redaction_profile for layer in layers if layer.policy.required_redaction_profile]
    if not profiles:
        return None
    if mode is PolicyOverrideMode.RESTRICTIVE_WINS:
        return max(profiles, key=_redaction_restriction_rank)
    if mode is PolicyOverrideMode.EXPLICIT_WIDEN:
        return min(profiles, key=_redaction_restriction_rank)
    raise ValueError("Unsupported redaction profile override mode")


def _serialize_payload(value: Mapping[str, object]) -> ToolingStatusAggregatePayload:
    return cast(
        ToolingStatusAggregatePayload,
        json.loads(json.dumps(value, sort_keys=True)),
    )


def _decision_to_payload(decision: PolicyDecision) -> PolicyDecisionPayload:
    return {
        "outcome": decision.outcome,
        "reasons": list(decision.reasons),
    }


def _parse_decision_payload(payload: Mapping[str, object]) -> PolicyDecision:
    if not isinstance(payload, Mapping):
        raise TypeError("Policy decision payload must be a mapping")

    outcome_value = payload.get("outcome")
    if outcome_value not in ("ACCEPT", "WARN", "REJECT"):
        raise ValueError("Policy decision outcome must be one of ['ACCEPT', 'WARN', 'REJECT']")

    reasons_value = payload.get("reasons")
    if not isinstance(reasons_value, list):
        raise ValueError("Policy decision reasons must be a list")
    if any(not isinstance(reason, str) for reason in reasons_value):
        raise ValueError("Policy decision reasons must be strings")

    return PolicyDecision(cast(PolicyDecisionOutcome, outcome_value), tuple(reasons_value))


def _policy_to_payload(policy: "ToolingStatusPolicy") -> ToolingStatusPolicyPayload:
    return cast(
        ToolingStatusPolicyPayload,
        {
            "schema_version": policy.schema_version,
            "allowed_overall_statuses": list(policy.allowed_overall_statuses),
            "allowed_producer_types": (
                list(policy.allowed_producer_types)
                if policy.allowed_producer_types is not None
                else None
            ),
            "required_redaction_profile": (
                policy.required_redaction_profile.profile_name
                if policy.required_redaction_profile is not None
                else None
            ),
            "maximum_advisory_issues": policy.maximum_advisory_issues,
        },
    )


def _policy_fingerprint(policy: "ToolingStatusPolicy") -> str:
    payload = {
        "schema_version": policy.schema_version,
        "allowed_overall_statuses": tuple(policy.allowed_overall_statuses),
        "allowed_producer_types": (
            tuple(policy.allowed_producer_types)
            if policy.allowed_producer_types is not None
            else None
        ),
        "required_redaction_profile": (
            policy.required_redaction_profile.fingerprint_scope
            if policy.required_redaction_profile is not None
            else None
        ),
        "maximum_advisory_issues": policy.maximum_advisory_issues,
        "forward_metadata": policy.forward_metadata,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_expected_value(value: object) -> tuple[str, ...] | int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        normalized: list[str] = []
        for entry in value:
            if not isinstance(entry, str):
                raise TypeError("Trace expected values must be strings")
            normalized.append(entry)
        return tuple(normalized)
    raise TypeError("Unexpected expected value type in trace")


def _trace_to_payload(trace: PolicyDecisionTrace | None) -> PolicyDecisionTracePayload | None:
    if trace is None:
        return None
    return cast(
        PolicyDecisionTracePayload,
        {
            "schema_version": trace.schema_version,
            "profile": trace.profile.profile_name,
            "aggregate": _serialize_payload(trace.aggregate),
            "evaluated_rules": [
                {
                    "name": rule.name,
                    "outcome": rule.outcome,
                    "observed": rule.observed,
                    "expected": rule.expected,
                    "rationale": rule.rationale,
                }
                for rule in trace.evaluated_rules
            ],
            "matched_conditions": list(trace.matched_conditions),
            "applied_overrides": [
                {
                    "dimension": override.dimension,
                    "mode": override.mode.value,
                    "selected": override.selected,
                    "considered": override.considered,
                    "discarded": override.discarded,
                }
                for override in trace.applied_overrides
            ],
            "rejected_alternatives": list(trace.rejected_alternatives),
        },
    )


def _parse_policy_decision_rule_trace(
    payload: Mapping[str, object]
) -> PolicyDecisionRuleTrace:
    if not isinstance(payload, Mapping):
        raise TypeError("Trace rule payload must be a mapping")

    name = payload.get("name")
    if name not in _TRACE_RULE_NAMES:
        raise ValueError("Trace rule name is invalid")

    outcome = payload.get("outcome")
    if outcome not in _TRACE_RULE_OUTCOMES:
        raise ValueError("Trace rule outcome is invalid")

    observed = payload.get("observed")
    if not isinstance(observed, str):
        raise ValueError("Trace rule observed value must be a string")

    expected = _normalize_expected_value(payload.get("expected"))
    rationale = payload.get("rationale")
    if rationale is not None and not isinstance(rationale, str):
        raise ValueError("Trace rule rationale must be a string when provided")

    return PolicyDecisionRuleTrace(
        name=cast(TraceRuleName, name),
        outcome=cast(TraceRuleOutcome, outcome),
        observed=observed,
        expected=expected,
        rationale=rationale,
    )


def _parse_policy_override_trace(
    payload: Mapping[str, object]
) -> PolicyOverrideTrace:
    if not isinstance(payload, Mapping):
        raise TypeError("Override trace payload must be a mapping")

    dimension_value = payload.get("dimension")
    if dimension_value not in {
        "overall_status",
        "producer_type",
        "advisory_issues",
        "redaction_profile",
    }:
        raise ValueError("Override trace dimension is invalid")

    mode_value = payload.get("mode")
    if not isinstance(mode_value, str):
        raise ValueError("Override trace mode must be a string")
    mode = PolicyOverrideMode(mode_value)

    selected = _normalize_layer_value(payload.get("selected"))

    considered_value = payload.get("considered")
    if not isinstance(considered_value, (list, tuple)):
        raise ValueError("Override trace considered must be a list or tuple")
    considered: list[tuple[str, tuple[str, ...] | int | None]] = []
    for entry in considered_value:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise ValueError("Override trace considered entries must be two-element pairs")
        name, value = entry
        if not isinstance(name, str):
            raise ValueError("Override trace considered entry names must be strings")
        considered.append((name, _normalize_layer_value(value)))

    discarded_value = payload.get("discarded")
    if not isinstance(discarded_value, (list, tuple)):
        raise ValueError("Override trace discarded must be a list or tuple")
    discarded: list[tuple[str, ...] | int | None] = []
    for entry in discarded_value:
        discarded.append(_normalize_layer_value(entry))

    return PolicyOverrideTrace(
        dimension=cast(PolicyOverrideTrace.__annotations__["dimension"], dimension_value),
        mode=mode,
        selected=selected,
        considered=tuple(sorted(considered, key=lambda entry: entry[0])),
        discarded=tuple(discarded),
    )


def _parse_trace_payload(
    payload: Mapping[str, object] | None, *, profile: RedactionProfile
) -> PolicyDecisionTrace | None:
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise TypeError("Policy decision trace payload must be a mapping when provided")

    schema_version_value = payload.get("schema_version")
    if not isinstance(schema_version_value, str):
        raise ValueError("Trace payload missing schema_version")
    if _compare_versions(schema_version_value, _TRACE_SCHEMA_VERSION) > 0:
        raise ValueError(
            f"Unsupported policy decision trace schema version '{schema_version_value}'"
        )

    profile_value = payload.get("profile")
    if not isinstance(profile_value, str):
        raise ValueError("Trace payload missing profile")
    trace_profile = _redaction_profile_from_name(profile_value)
    if trace_profile is not profile:
        raise ValueError("Trace payload profile does not match snapshot profile")

    aggregate_payload = payload.get("aggregate")
    if not isinstance(aggregate_payload, Mapping):
        raise ValueError("Trace aggregate must be a mapping")

    rules_payload = payload.get("evaluated_rules")
    if not isinstance(rules_payload, list):
        raise ValueError("Trace evaluated_rules must be a list")
    rules = tuple(_parse_policy_decision_rule_trace(rule) for rule in rules_payload)

    matched_value = payload.get("matched_conditions")
    if not isinstance(matched_value, list) or any(not isinstance(entry, str) for entry in matched_value):
        raise ValueError("Trace matched_conditions must be a list of strings")

    overrides_payload = payload.get("applied_overrides")
    if not isinstance(overrides_payload, list):
        raise ValueError("Trace applied_overrides must be a list")
    overrides = tuple(_parse_policy_override_trace(entry) for entry in overrides_payload)

    rejected_value = payload.get("rejected_alternatives")
    if not isinstance(rejected_value, list) or any(not isinstance(entry, str) for entry in rejected_value):
        raise ValueError("Trace rejected_alternatives must be a list of strings")

    trace = PolicyDecisionTrace(
        schema_version=schema_version_value,
        profile=trace_profile,
        aggregate=_serialize_payload(cast(Mapping[str, object], aggregate_payload)),
        evaluated_rules=rules,
        matched_conditions=tuple(matched_value),
        applied_overrides=overrides,
        rejected_alternatives=tuple(rejected_value),
    )
    _validate_trace(trace)
    return trace


def _parse_snapshot_options(
    payload: Mapping[str, object], *, profile: RedactionProfile
) -> PolicyEvaluationOptions:
    if not isinstance(payload, Mapping):
        raise TypeError("Snapshot options must be a mapping")

    emit_trace_value = payload.get("emit_trace")
    use_cache_value = payload.get("use_cache")
    if not isinstance(emit_trace_value, bool) or not isinstance(use_cache_value, bool):
        raise ValueError("Snapshot options must include boolean emit_trace and use_cache")

    return PolicyEvaluationOptions(
        profile=profile, emit_trace=emit_trace_value, use_cache=use_cache_value
    )


def parse_policy_evaluation_snapshot(
    payload: Mapping[str, object]
) -> PolicyEvaluationSnapshot:
    if not isinstance(payload, Mapping):
        raise TypeError("Policy evaluation snapshot must be a mapping")

    schema_version_value = payload.get("schema_version")
    if not isinstance(schema_version_value, str):
        raise ValueError("Snapshot missing schema_version")
    version_comparison = _compare_versions(schema_version_value, _SNAPSHOT_SCHEMA_VERSION)
    if version_comparison > 0:
        raise ValueError(
            f"Unsupported policy evaluation snapshot schema version '{schema_version_value}'"
        )
    lineage_supported = (
        _compare_versions(schema_version_value, _SNAPSHOT_LINEAGE_SCHEMA_VERSION) >= 0
    )
    backward_version_detected = version_comparison < 0

    allowed_fields = {
        "schema_version",
        "profile",
        "aggregate",
        "aggregate_fingerprint",
        "policy",
        "policy_forward_metadata",
        "policy_fingerprint",
        "decision",
        "trace",
        "options",
    }
    if lineage_supported:
        allowed_fields.update(
            {
                "parent_snapshot_fingerprint",
                "lineage_relation",
                "review_notes",
                "snapshot_fingerprint",
                "evaluation_fingerprint",
            }
        )

    extra_fields = set(payload.keys()) - allowed_fields
    if extra_fields and not backward_version_detected:
        raise ValueError(
            f"Snapshot payload has unexpected fields: {sorted(extra_fields)}"
        )

    profile_value = payload.get("profile")
    if not isinstance(profile_value, str):
        raise ValueError("Snapshot missing profile")
    profile = _redaction_profile_from_name(profile_value)

    aggregate_payload = payload.get("aggregate")
    if not isinstance(aggregate_payload, Mapping):
        raise ValueError("Snapshot missing aggregate payload")
    aggregate = parse_tooling_status_payload(aggregate_payload, profile=profile)

    aggregate_fingerprint_value = payload.get("aggregate_fingerprint")
    if not isinstance(aggregate_fingerprint_value, str):
        raise ValueError("Snapshot missing aggregate_fingerprint")
    if aggregate.fingerprint_for_profile(profile) != aggregate_fingerprint_value:
        raise ValueError("Snapshot aggregate_fingerprint does not match payload")

    policy_payload = payload.get("policy")
    if not isinstance(policy_payload, Mapping):
        raise ValueError("Snapshot missing policy payload")
    policy = parse_tooling_status_policy(policy_payload)

    policy_forward_metadata_value = payload.get("policy_forward_metadata")
    if not isinstance(policy_forward_metadata_value, Mapping):
        raise ValueError("Snapshot missing policy_forward_metadata")
    policy_forward_metadata = cast(
        dict[str, object], json.loads(json.dumps(policy_forward_metadata_value, sort_keys=True))
    )
    policy = replace(policy, forward_metadata=policy_forward_metadata)

    policy_fingerprint_value = payload.get("policy_fingerprint")
    if not isinstance(policy_fingerprint_value, str):
        raise ValueError("Snapshot missing policy_fingerprint")
    if _policy_fingerprint(policy) != policy_fingerprint_value:
        raise ValueError("Snapshot policy_fingerprint does not match payload")

    decision_payload = payload.get("decision")
    if not isinstance(decision_payload, Mapping):
        raise ValueError("Snapshot missing decision payload")
    decision = _parse_decision_payload(decision_payload)

    trace = _parse_trace_payload(payload.get("trace"), profile=profile)

    options_payload = payload.get("options")
    if not isinstance(options_payload, Mapping):
        raise ValueError("Snapshot missing options payload")
    options = _parse_snapshot_options(options_payload, profile=profile)

    if options.emit_trace and trace is None:
        raise ValueError("Snapshot options expect trace but none was provided")

    parent_snapshot_fingerprint: str | None = None
    lineage_relation: str | None = None
    review_notes: str | None = None
    evaluation_fingerprint_value: str | None = None
    snapshot_fingerprint_value: str | None = None

    if lineage_supported:
        parent_snapshot_payload = payload.get("parent_snapshot_fingerprint")
        relation_payload = payload.get("lineage_relation")
        review_notes_payload = payload.get("review_notes")
        snapshot_fingerprint_payload = payload.get("snapshot_fingerprint")
        evaluation_fingerprint_payload = payload.get("evaluation_fingerprint")

        if parent_snapshot_payload is not None:
            parent_snapshot_fingerprint = _validate_fingerprint_value(
                parent_snapshot_payload
            )
        if relation_payload is not None:
            lineage_relation = _validate_lineage_relation(relation_payload)
        if lineage_relation is not None and parent_snapshot_fingerprint is None:
            raise ValueError(
                "lineage_relation provided without parent_snapshot_fingerprint"
            )
        if parent_snapshot_fingerprint is not None and lineage_relation is None:
            raise ValueError(
                "lineage_relation must accompany parent_snapshot_fingerprint"
            )
        if review_notes_payload is not None:
            if not isinstance(review_notes_payload, str):
                raise ValueError("review_notes must be a string when provided")
            if len(review_notes_payload) > _MAX_REVIEW_NOTES_LENGTH:
                raise ValueError("review_notes exceeds maximum length")
            review_notes = review_notes_payload

        if evaluation_fingerprint_payload is not None:
            if not isinstance(evaluation_fingerprint_payload, str):
                raise ValueError("evaluation_fingerprint must be a string when provided")
            evaluation_fingerprint_value = evaluation_fingerprint_payload

        if snapshot_fingerprint_payload is not None:
            if not isinstance(snapshot_fingerprint_payload, str):
                raise ValueError("snapshot_fingerprint must be a string when provided")
            snapshot_fingerprint_value = snapshot_fingerprint_payload

    elif any(
        key in payload
        for key in (
            "parent_snapshot_fingerprint",
            "lineage_relation",
            "review_notes",
            "snapshot_fingerprint",
            "evaluation_fingerprint",
        )
    ):
        raise ValueError("Lineage metadata is not supported for this snapshot schema version")

    snapshot = PolicyEvaluationSnapshot(
        schema_version=schema_version_value,
        aggregate=aggregate,
        policy=policy,
        aggregate_fingerprint=aggregate_fingerprint_value,
        policy_fingerprint=policy_fingerprint_value,
        decision=decision,
        trace=trace,
        options=options,
        parent_snapshot_fingerprint=parent_snapshot_fingerprint,
        lineage_relation=lineage_relation,
        review_notes=review_notes,
    )

    if snapshot.parent_snapshot_fingerprint is not None and (
        snapshot.parent_snapshot_fingerprint == snapshot.fingerprint
    ):
        raise ValueError("Snapshot cannot reference itself as lineage parent")

    if evaluation_fingerprint_value is not None and (
        evaluation_fingerprint_value != snapshot.evaluation_fingerprint
    ):
        raise ValueError("Snapshot evaluation_fingerprint does not match payload")

    if snapshot_fingerprint_value is not None and (
        snapshot_fingerprint_value != snapshot.fingerprint
    ):
        raise ValueError("Snapshot fingerprint does not match payload")

    return snapshot


def _assert_snapshot_equivalence(
    snapshot: PolicyEvaluationSnapshot,
    decision: PolicyDecision,
    trace: PolicyDecisionTrace | None,
) -> None:
    if snapshot.aggregate.fingerprint_for_profile(snapshot.options.profile) != snapshot.aggregate_fingerprint:
        raise ValueError("Snapshot aggregate fingerprint mismatch on re-evaluation")

    if _policy_fingerprint(snapshot.policy) != snapshot.policy_fingerprint:
        raise ValueError("Snapshot policy fingerprint mismatch on re-evaluation")

    if decision != snapshot.decision:
        raise ValueError("Snapshot decision does not match re-evaluation result")

    if snapshot.options.emit_trace:
        if snapshot.trace is None:
            raise ValueError("Snapshot is missing trace data")
        if trace is None:
            raise ValueError("Re-evaluation did not produce a trace")
        if trace != snapshot.trace:
            raise ValueError("Snapshot trace does not match re-evaluation result")


def snapshot_tooling_status_policy_evaluation(
    subject: ToolingStatusAggregate | Mapping[str, object],
    policy: ToolingStatusPolicy | Mapping[str, object],
    *,
    profile: RedactionProfile = RedactionProfile.FULL,
    emit_trace: bool = True,
    use_cache: bool = True,
    cache: _PolicyEvaluationCache | None = None,
    parent_snapshot_fingerprint: str | None = None,
    lineage_relation: str | None = None,
    review_notes: str | None = None,
) -> PolicyEvaluationSnapshotPayload:
    aggregate = _to_aggregate(subject, profile=profile)
    parsed_policy = _to_policy(policy)

    parent_fingerprint_value = (
        _validate_fingerprint_value(parent_snapshot_fingerprint)
        if parent_snapshot_fingerprint
        else None
    )
    lineage_relation_value = (
        _validate_lineage_relation(lineage_relation) if lineage_relation else None
    )
    if lineage_relation_value is not None and parent_fingerprint_value is None:
        raise ValueError("lineage_relation provided without parent_snapshot_fingerprint")
    if parent_fingerprint_value is not None and lineage_relation_value is None:
        raise ValueError("lineage_relation must accompany parent_snapshot_fingerprint")
    if review_notes is not None:
        if not isinstance(review_notes, str):
            raise TypeError("review_notes must be a string when provided")
        if len(review_notes) > _MAX_REVIEW_NOTES_LENGTH:
            raise ValueError("review_notes exceeds maximum length")

    evaluation = evaluate_tooling_status_policy(
        aggregate,
        parsed_policy,
        profile=profile,
        emit_trace=emit_trace,
        use_cache=use_cache,
        cache=cache,
    )

    decision: PolicyDecision
    trace: PolicyDecisionTrace | None
    if emit_trace:
        decision, trace = cast(tuple[PolicyDecision, PolicyDecisionTrace], evaluation)
    else:
        decision = cast(PolicyDecision, evaluation)
        trace = None

    snapshot = PolicyEvaluationSnapshot(
        schema_version=_SNAPSHOT_SCHEMA_VERSION,
        aggregate=aggregate,
        policy=parsed_policy,
        aggregate_fingerprint=aggregate.fingerprint_for_profile(profile),
        policy_fingerprint=_policy_fingerprint(parsed_policy),
        decision=decision,
        trace=trace,
        options=PolicyEvaluationOptions(
            profile=profile, emit_trace=emit_trace, use_cache=use_cache
        ),
        parent_snapshot_fingerprint=parent_fingerprint_value,
        lineage_relation=lineage_relation_value,
        review_notes=review_notes,
    )
    if snapshot.parent_snapshot_fingerprint is not None and (
        snapshot.parent_snapshot_fingerprint == snapshot.fingerprint
    ):
        raise ValueError("Snapshot cannot reference itself as lineage parent")
    return snapshot.to_payload()


def verify_tooling_status_policy_snapshot(
    snapshot_payload: Mapping[str, object],
    *,
    cache: _PolicyEvaluationCache | None = None,
) -> PolicyDecision | tuple[PolicyDecision, PolicyDecisionTrace]:
    snapshot = parse_policy_evaluation_snapshot(snapshot_payload)

    evaluation = evaluate_tooling_status_policy(
        snapshot.aggregate,
        snapshot.policy,
        profile=snapshot.options.profile,
        emit_trace=snapshot.options.emit_trace,
        use_cache=snapshot.options.use_cache,
        cache=cache if cache is not None else _PolicyEvaluationCache(),
    )

    decision: PolicyDecision
    trace: PolicyDecisionTrace | None
    if snapshot.options.emit_trace:
        decision, trace = cast(tuple[PolicyDecision, PolicyDecisionTrace], evaluation)
    else:
        decision = cast(PolicyDecision, evaluation)
        trace = None

    _assert_snapshot_equivalence(snapshot, decision, trace)

    if snapshot.options.emit_trace:
        return decision, cast(PolicyDecisionTrace, trace)
    return decision


def _evaluation_cache_key(
    aggregate: "ToolingStatusAggregate",
    policy: "ToolingStatusPolicy",
    *,
    profile: RedactionProfile,
    emit_trace: bool,
) -> tuple[str, str, str, bool]:
    return (
        aggregate.fingerprint_for_profile(profile),
        _policy_fingerprint(policy),
        profile.fingerprint_scope,
        emit_trace,
    )


def _validate_trace(trace: PolicyDecisionTrace) -> None:
    if trace.schema_version != _TRACE_SCHEMA_VERSION:
        raise ValueError("Unsupported policy decision trace schema version")

    if len(trace.evaluated_rules) > 16:
        raise ValueError("Trace contains too many rule evaluations")
    if len(trace.applied_overrides) > 8:
        raise ValueError("Trace contains too many override entries")
    if len(trace.rejected_alternatives) > 64:
        raise ValueError("Trace rejected alternatives exceed bounds")

    for rule in trace.evaluated_rules:
        if rule.name not in _TRACE_RULE_NAMES:
            raise ValueError(f"Unknown rule name in trace: {rule.name}")
        if rule.outcome not in _TRACE_RULE_OUTCOMES:
            raise ValueError(f"Unknown rule outcome in trace: {rule.outcome}")


def _normalize_layer_value(value: object) -> tuple[str, ...] | int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(cast(tuple[str, ...], value))
    raise TypeError("Unexpected layer value type in policy metadata")


class _PolicyDecisionTraceBuilder:
    def __init__(
        self,
        aggregate: ToolingStatusAggregate,
        policy: ToolingStatusPolicy,
        profile: RedactionProfile,
    ) -> None:
        self._profile = profile
        self.aggregate = _serialize_payload(aggregate.profiled_payload(profile))
        self.rules: list[PolicyDecisionRuleTrace] = []
        self.matched: list[str] = []
        self.rejected: list[str] = []
        self.applied_overrides: tuple[PolicyOverrideTrace, ...] = self._build_overrides(policy)

    def _build_overrides(self, policy: ToolingStatusPolicy) -> tuple[PolicyOverrideTrace, ...]:
        metadata = policy.forward_metadata
        layers = metadata.get("composition_layer_policies")
        if not isinstance(layers, tuple):
            return ()

        rules = metadata.get("composition_rules")
        if not isinstance(rules, Mapping):
            return ()

        layer_summaries: list[dict[str, object]] = []
        for entry in layers:
            if isinstance(entry, Mapping):
                layer_summaries.append(dict(entry))

        overrides: list[PolicyOverrideTrace] = []

        def _considered_values(field: str) -> tuple[tuple[str, tuple[str, ...] | int | None], ...]:
            considered: list[tuple[str, tuple[str, ...] | int | None]] = []
            for summary in layer_summaries:
                name = cast(str, summary.get("name"))
                if not name:
                    continue
                raw_value = summary.get(field)
                value = _normalize_layer_value(raw_value)
                considered.append((name, value))
            return tuple(sorted(considered, key=lambda entry: entry[0]))

        def _discarded_from_union(
            candidates: Iterable[tuple[str, tuple[str, ...] | int | None]],
            selected: tuple[str, ...] | int | None,
        ) -> tuple[tuple[str, ...] | int | None, ...]:
            if isinstance(selected, int):
                discarded_numbers = {
                    value
                    for _, value in candidates
                    if isinstance(value, int) and value != selected
                }
                if any(value is None for _, value in candidates):
                    if selected is not None:
                        discarded_numbers.add(None)
                return tuple(sorted(discarded_numbers, key=lambda entry: (-1 if entry is None else entry)))
            if selected is None:
                discarded_sets = [
                    set(value)
                    for _, value in candidates
                    if isinstance(value, tuple)
                ]
                combined = set().union(*discarded_sets) if discarded_sets else set()
                return tuple(sorted(combined)) if combined else ()
            combined_candidates: set[str] = set()
            for _, value in candidates:
                if isinstance(value, tuple):
                    combined_candidates.update(value)
            discarded = combined_candidates - set(selected)
            return tuple(sorted(discarded)) if discarded else ()

        mappings: tuple[tuple[str, str, tuple[str, ...] | int | None], ...] = (
            (
                "overall_status",
                "allowed_overall_statuses",
                tuple(policy.allowed_overall_statuses),
            ),
            (
                "producer_type",
                "allowed_producer_types",
                tuple(policy.allowed_producer_types)
                if policy.allowed_producer_types is not None
                else None,
            ),
            (
                "advisory_issues",
                "maximum_advisory_issues",
                policy.maximum_advisory_issues,
            ),
            (
                "redaction_profile",
                "required_redaction_profile",
                (policy.required_redaction_profile.profile_name,)
                if policy.required_redaction_profile is not None
                else None,
            ),
        )

        for dimension, field, selected in mappings:
            mode_field = f"{dimension}_rule"
            mode_value = rules.get(mode_field)
            if mode_value is None:
                continue
            considered = _considered_values(field)
            discarded = _discarded_from_union(considered, selected)
            if discarded:
                self.rejected.append(
                    f"{dimension} discarded {discarded} via {mode_value}"
                )
            overrides.append(
                PolicyOverrideTrace(
                    dimension=cast(PolicyOverrideTrace.__annotations__["dimension"], dimension),
                    mode=PolicyOverrideMode(mode_value),
                    selected=selected,
                    considered=considered,
                    discarded=discarded,
                )
            )

        return tuple(overrides)

    def record_rule(
        self,
        *,
        name: TraceRuleName,
        outcome: TraceRuleOutcome,
        observed: str,
        expected: tuple[str, ...] | int | None,
        rationale: str | None = None,
        rejected_alternative: str | None = None,
    ) -> None:
        self.rules.append(
            PolicyDecisionRuleTrace(
                name=name,
                outcome=outcome,
                observed=observed,
                expected=expected,
                rationale=rationale,
            )
        )
        if outcome == "match":
            self.matched.append(rationale or name)
        if rejected_alternative:
            self.rejected.append(rejected_alternative)

    def finalize(self) -> PolicyDecisionTrace:
        trace = PolicyDecisionTrace(
            schema_version=_TRACE_SCHEMA_VERSION,
            profile=self._profile,
            aggregate=self.aggregate,
            evaluated_rules=tuple(self.rules),
            matched_conditions=tuple(self.matched),
            applied_overrides=self.applied_overrides,
            rejected_alternatives=tuple(self.rejected),
        )
        _validate_trace(trace)
        return trace


def compose_tooling_status_policies(
    composition: ToolingStatusPolicyComposition | Mapping[str, object]
) -> ToolingStatusPolicy:
    parsed = (
        parse_tooling_status_policy_composition(composition)
        if isinstance(composition, Mapping)
        else composition
    )
    if not parsed.layers:
        raise ValueError("Policy composition requires at least one layer")

    schema_versions = {layer.policy.schema_version for layer in parsed.layers}
    if len(schema_versions) != 1:
        raise ValueError("Policy layers must share the same policy schema version")
    schema_version = schema_versions.pop()
    if schema_version != _POLICY_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported policy schema version '{schema_version}' in composition"
        )

    allowed_overall_statuses = _compose_allowed_statuses(
        parsed.layers, parsed.overall_status_rule
    )
    allowed_producer_types = _compose_producer_types(
        parsed.layers, parsed.producer_type_rule
    )
    maximum_advisory_issues = _compose_advisory_limits(
        parsed.layers, parsed.advisory_issue_rule
    )
    required_redaction_profile = _compose_redaction_profile(
        parsed.layers, parsed.redaction_profile_rule
    )

    metadata = {
        "composition_layers": tuple(
            (layer.name, layer.priority) for layer in parsed.layers
        ),
        "composition_layer_policies": tuple(
            {
                "name": layer.name,
                "priority": layer.priority,
                "allowed_overall_statuses": tuple(layer.policy.allowed_overall_statuses),
                "allowed_producer_types": (
                    tuple(layer.policy.allowed_producer_types)
                    if layer.policy.allowed_producer_types is not None
                    else None
                ),
                "required_redaction_profile": (
                    layer.policy.required_redaction_profile.profile_name
                    if layer.policy.required_redaction_profile is not None
                    else None
                ),
                "maximum_advisory_issues": layer.policy.maximum_advisory_issues,
            }
            for layer in parsed.layers
        ),
        "composition_rules": {
            "overall_status_rule": parsed.overall_status_rule.value,
            "producer_type_rule": parsed.producer_type_rule.value,
            "advisory_issue_rule": parsed.advisory_issue_rule.value,
            "redaction_profile_rule": parsed.redaction_profile_rule.value,
        },
    }

    return ToolingStatusPolicy(
        schema_version=_POLICY_SCHEMA_VERSION,
        allowed_overall_statuses=allowed_overall_statuses,
        allowed_producer_types=allowed_producer_types,
        required_redaction_profile=required_redaction_profile,
        maximum_advisory_issues=maximum_advisory_issues,
        forward_metadata=metadata,
    )


def evaluate_tooling_status_policy(
    subject: ToolingStatusAggregate | Mapping[str, object],
    policy: ToolingStatusPolicy | Mapping[str, object],
    *,
    profile: RedactionProfile = RedactionProfile.FULL,
    emit_trace: bool = False,
    use_cache: bool = True,
    cache: _PolicyEvaluationCache | None = None,
) -> PolicyDecision | tuple[PolicyDecision, PolicyDecisionTrace]:
    """Evaluate a tooling status aggregate against a policy.

    Idempotency contract:
    * Identical inputs (subject + policy + profile + options) yield identical
      decisions and traces.
    * Results do not depend on evaluation order or call count; the cache is
      performance-only and never a decision authority.
    * Validation failures bypass the cache to prevent poisoning.
    """
    aggregate = _to_aggregate(subject, profile=profile)
    parsed_policy = _to_policy(policy)
    active_cache = cache if cache is not None else _POLICY_EVALUATION_CACHE
    cache_key: tuple[str, str, str, bool] | None = None

    if use_cache:
        cache_key = _evaluation_cache_key(
            aggregate, parsed_policy, profile=profile, emit_trace=emit_trace
        )
        cached = active_cache.get(cache_key)
        if cached is not None:
            decision, trace = cached
            if emit_trace:
                return decision, cast(PolicyDecisionTrace, trace)
            return decision

    trace_builder = (
        _PolicyDecisionTraceBuilder(aggregate, parsed_policy, profile)
        if emit_trace
        else None
    )

    reject_reasons: list[str] = []
    warn_reasons: list[str] = []

    if aggregate.overall_status not in parsed_policy.allowed_overall_statuses:
        reject_reasons.append(
            "overall_status"
            f" '{aggregate.overall_status}' not permitted by policy"
        )
        if trace_builder:
            trace_builder.record_rule(
                name="overall_status",
                outcome="reject",
                observed=aggregate.overall_status,
                expected=parsed_policy.allowed_overall_statuses,
                rationale="overall_status rejected",
                rejected_alternative=f"overall_status {aggregate.overall_status} not in {parsed_policy.allowed_overall_statuses}",
            )
    elif aggregate.overall_status != "PASS":
        warn_reasons.append(f"overall_status is {aggregate.overall_status}")
        if trace_builder:
            trace_builder.record_rule(
                name="overall_status",
                outcome="warn",
                observed=aggregate.overall_status,
                expected=parsed_policy.allowed_overall_statuses,
                rationale=f"overall_status is {aggregate.overall_status}",
            )
    elif trace_builder:
        trace_builder.record_rule(
            name="overall_status",
            outcome="match",
            observed=aggregate.overall_status,
            expected=parsed_policy.allowed_overall_statuses,
            rationale="overall_status permitted",
        )

    if parsed_policy.allowed_producer_types is not None:
        attestation = aggregate.provenance_attestation
        if attestation is None:
            reject_reasons.append("provenance attestation required")
            if trace_builder:
                trace_builder.record_rule(
                    name="producer_type",
                    outcome="reject",
                    observed="<missing attestation>",
                    expected=parsed_policy.allowed_producer_types,
                    rationale="producer attestation missing",
                    rejected_alternative="producer_type unavailable",
                )
        elif attestation.producer_type not in parsed_policy.allowed_producer_types:
            reject_reasons.append(
                "producer_type '"
                f"{attestation.producer_type}' not permitted (allowed:"
                f" {sorted(parsed_policy.allowed_producer_types)})"
            )
            if trace_builder:
                trace_builder.record_rule(
                    name="producer_type",
                    outcome="reject",
                    observed=attestation.producer_type,
                    expected=parsed_policy.allowed_producer_types,
                    rationale="producer_type rejected",
                    rejected_alternative=(
                        f"producer_type {attestation.producer_type} not in"
                        f" {parsed_policy.allowed_producer_types}"
                    ),
                )
        elif trace_builder:
            trace_builder.record_rule(
                name="producer_type",
                outcome="match",
                observed=attestation.producer_type,
                expected=parsed_policy.allowed_producer_types,
                rationale="producer_type permitted",
            )
    elif trace_builder:
        trace_builder.record_rule(
            name="producer_type",
            outcome="match",
            observed=(
                aggregate.provenance_attestation.producer_type
                if aggregate.provenance_attestation is not None
                else "<not required>"
            ),
            expected=None,
            rationale="producer_type unrestricted",
        )

    if (
        parsed_policy.required_redaction_profile is not None
        and not _redaction_matches_profile(aggregate, parsed_policy.required_redaction_profile)
    ):
        reject_reasons.append(
            "aggregate payload not constrained to required redaction profile '"
            f"{parsed_policy.required_redaction_profile.profile_name}'"
        )
        if trace_builder:
            trace_builder.record_rule(
                name="redaction_profile",
                outcome="reject",
                observed=profile.profile_name,
                expected=(parsed_policy.required_redaction_profile.profile_name,),
                rationale="redaction profile mismatch",
                rejected_alternative=(
                    f"redaction profile {profile.profile_name} !="
                    f" {parsed_policy.required_redaction_profile.profile_name}"
                ),
            )
    elif trace_builder:
        trace_builder.record_rule(
            name="redaction_profile",
            outcome="match",
            observed=profile.profile_name,
            expected=(
                (parsed_policy.required_redaction_profile.profile_name,)
                if parsed_policy.required_redaction_profile is not None
                else None
            ),
            rationale=(
                "redaction profile permitted"
                if parsed_policy.required_redaction_profile is not None
                else "no required redaction profile"
            ),
        )

    advisory_issues = _count_advisory_issues(aggregate)
    if (
        parsed_policy.maximum_advisory_issues is not None
        and advisory_issues > parsed_policy.maximum_advisory_issues
    ):
        reject_reasons.append(
            f"advisory issues {advisory_issues} exceed maximum"
            f" {parsed_policy.maximum_advisory_issues}"
        )
        if trace_builder:
            trace_builder.record_rule(
                name="advisory_issues",
                outcome="reject",
                observed=str(advisory_issues),
                expected=parsed_policy.maximum_advisory_issues,
                rationale="advisory issue limit exceeded",
                rejected_alternative=(
                    f"advisory issues {advisory_issues} exceed"
                    f" {parsed_policy.maximum_advisory_issues}"
                ),
            )
    if advisory_issues:
        warn_reasons.append(f"{advisory_issues} advisory issue(s) present")
        if trace_builder and advisory_issues <= (
            parsed_policy.maximum_advisory_issues
            if parsed_policy.maximum_advisory_issues is not None
            else advisory_issues
        ):
            trace_builder.record_rule(
                name="advisory_issues",
                outcome="warn",
                observed=str(advisory_issues),
                expected=parsed_policy.maximum_advisory_issues,
                rationale="advisory issues present",
            )
    elif trace_builder:
        trace_builder.record_rule(
            name="advisory_issues",
            outcome="match",
            observed="0",
            expected=parsed_policy.maximum_advisory_issues,
            rationale="no advisory issues",
        )

    decision = PolicyDecision("ACCEPT", ())
    if reject_reasons:
        decision = PolicyDecision("REJECT", tuple(reject_reasons + warn_reasons))
    elif warn_reasons:
        decision = PolicyDecision("WARN", tuple(warn_reasons))

    if trace_builder:
        trace = trace_builder.finalize()
        if use_cache and cache_key is not None:
            active_cache.set(cache_key, (decision, trace))
        return decision, trace

    if use_cache and cache_key is not None:
        active_cache.set(cache_key, (decision, None))

    return decision


def policy_ci_strict() -> ToolingStatusPolicy:
    return ToolingStatusPolicy(
        schema_version=_POLICY_SCHEMA_VERSION,
        allowed_overall_statuses=("PASS",),
        allowed_producer_types=("ci",),
        required_redaction_profile=None,
        maximum_advisory_issues=0,
    )


def policy_local_dev_permissive() -> ToolingStatusPolicy:
    return ToolingStatusPolicy(
        schema_version=_POLICY_SCHEMA_VERSION,
        allowed_overall_statuses=("PASS", "WARN"),
        allowed_producer_types=None,
        required_redaction_profile=None,
        maximum_advisory_issues=None,
    )


def policy_release_gate() -> ToolingStatusPolicy:
    return ToolingStatusPolicy(
        schema_version=_POLICY_SCHEMA_VERSION,
        allowed_overall_statuses=("PASS",),
        allowed_producer_types=None,
        required_redaction_profile=RedactionProfile.SAFE,
        maximum_advisory_issues=0,
    )


def fingerprint_tooling_status(
    subject: ToolingStatusAggregate | Mapping[str, object],
    *,
    profile: RedactionProfile = RedactionProfile.FULL,
) -> str:
    aggregate = _to_aggregate(subject, profile=profile)
    return aggregate.fingerprint_for_profile(profile)


def tooling_status_equal(
    first: ToolingStatusAggregate | Mapping[str, object],
    second: ToolingStatusAggregate | Mapping[str, object],
    *,
    profile: RedactionProfile = RedactionProfile.FULL,
) -> bool:
    return fingerprint_tooling_status(first, profile=profile) == fingerprint_tooling_status(
        second, profile=profile
    )


def tooling_status_equal_ignoring_attestation(
    first: ToolingStatusAggregate | Mapping[str, object],
    second: ToolingStatusAggregate | Mapping[str, object],
    *,
    profile: RedactionProfile = RedactionProfile.FULL,
) -> bool:
    first_aggregate = _to_aggregate(first, profile=profile)
    second_aggregate = _to_aggregate(second, profile=profile)
    return fingerprint_tooling_status(
        replace(first_aggregate, provenance_attestation=None), profile=profile
    ) == fingerprint_tooling_status(
        replace(second_aggregate, provenance_attestation=None), profile=profile
    )


def tooling_status_same_results_different_producers(
    candidate: ToolingStatusAggregate | Mapping[str, object],
    reference: ToolingStatusAggregate | Mapping[str, object],
    *,
    profile: RedactionProfile = RedactionProfile.FULL,
) -> bool:
    candidate_aggregate = _to_aggregate(candidate, profile=profile)
    reference_aggregate = _to_aggregate(reference, profile=profile)
    if candidate_aggregate.provenance_attestation is None or reference_aggregate.provenance_attestation is None:
        return False
    if candidate_aggregate.provenance_attestation == reference_aggregate.provenance_attestation:
        return False
    return tooling_status_equal_ignoring_attestation(
        candidate_aggregate, reference_aggregate, profile=profile
    )


def tooling_status_supersedes(
    candidate: ToolingStatusAggregate | Mapping[str, object],
    reference: ToolingStatusAggregate | Mapping[str, object],
    *,
    profile: RedactionProfile = RedactionProfile.FULL,
) -> bool:
    candidate_aggregate = _to_aggregate(candidate, profile=profile)
    reference_aggregate = _to_aggregate(reference, profile=profile)
    parent_fingerprint = candidate_aggregate.lineage_parent_fingerprint

    if parent_fingerprint is None:
        return False
    if candidate_aggregate.lineage_relation not in {"supersedes", "amends"}:
        return False
    if parent_fingerprint == candidate_aggregate.fingerprint_for_profile(profile):
        raise ValueError("Lineage parent fingerprint matches candidate fingerprint")
    return parent_fingerprint == reference_aggregate.fingerprint_for_profile(profile)


def _to_snapshot(
    candidate: PolicyEvaluationSnapshot | Mapping[str, object]
) -> PolicyEvaluationSnapshot:
    if isinstance(candidate, PolicyEvaluationSnapshot):
        return candidate
    return parse_policy_evaluation_snapshot(candidate)


def snapshot_supersedes(
    candidate: PolicyEvaluationSnapshot | Mapping[str, object],
    reference: PolicyEvaluationSnapshot | Mapping[str, object],
) -> bool:
    candidate_snapshot = _to_snapshot(candidate)
    reference_snapshot = _to_snapshot(reference)

    parent_fingerprint = candidate_snapshot.parent_snapshot_fingerprint
    if parent_fingerprint is None:
        return False
    if candidate_snapshot.lineage_relation not in _AUTHORITATIVE_SNAPSHOT_RELATIONS:
        return False
    if parent_fingerprint == candidate_snapshot.fingerprint:
        raise ValueError("Snapshot cannot reference itself as lineage parent")
    return parent_fingerprint == reference_snapshot.fingerprint


def detect_supersession_chains(
    snapshots: Iterable[PolicyEvaluationSnapshot | Mapping[str, object]],
) -> list[tuple[PolicyEvaluationSnapshot, ...]]:
    parsed_snapshots = [_to_snapshot(entry) for entry in snapshots]
    fingerprint_index: dict[str, PolicyEvaluationSnapshot] = {}
    for snapshot in parsed_snapshots:
        fingerprint = snapshot.fingerprint
        if fingerprint in fingerprint_index:
            raise ValueError("Duplicate snapshot fingerprints detected in lineage chain")
        fingerprint_index[fingerprint] = snapshot
        if snapshot.parent_snapshot_fingerprint is not None and (
            snapshot.parent_snapshot_fingerprint == fingerprint
        ):
            raise ValueError("Snapshot cannot reference itself as lineage parent")

    for snapshot in parsed_snapshots:
        visited: set[str] = set()
        current = snapshot
        while (
            current.lineage_relation in _AUTHORITATIVE_SNAPSHOT_RELATIONS
            and current.parent_snapshot_fingerprint is not None
        ):
            parent_fingerprint = current.parent_snapshot_fingerprint
            if parent_fingerprint in visited:
                raise ValueError("Snapshot lineage cycle detected")
            visited.add(parent_fingerprint)
            parent = fingerprint_index.get(parent_fingerprint)
            if parent is None:
                break
            current = parent

    authoritative_children: set[str] = set()
    authoritative_parents: set[str] = set()
    for snapshot in parsed_snapshots:
        if snapshot.lineage_relation in _AUTHORITATIVE_SNAPSHOT_RELATIONS and snapshot.parent_snapshot_fingerprint is not None:
            authoritative_children.add(snapshot.fingerprint)
            authoritative_parents.add(snapshot.parent_snapshot_fingerprint)

    tips = [
        snapshot
        for snapshot in parsed_snapshots
        if snapshot.fingerprint in authoritative_children
        and snapshot.fingerprint not in authoritative_parents
    ]

    chains: list[tuple[PolicyEvaluationSnapshot, ...]] = []
    for tip in tips:
        chain: list[PolicyEvaluationSnapshot] = []
        current = tip
        visited: set[str] = set()
        while True:
            chain.append(current)
            parent_fingerprint = current.parent_snapshot_fingerprint
            if parent_fingerprint is None:
                break
            if current.lineage_relation not in _AUTHORITATIVE_SNAPSHOT_RELATIONS:
                break
            if parent_fingerprint in visited:
                raise ValueError("Snapshot lineage cycle detected")
            visited.add(parent_fingerprint)
            parent = fingerprint_index.get(parent_fingerprint)
            if parent is None:
                break
            current = parent
        chains.append(tuple(reversed(chain)))
    return chains


def latest_authoritative_snapshot(
    snapshots: Iterable[PolicyEvaluationSnapshot | Mapping[str, object]]
) -> PolicyEvaluationSnapshot | None:
    chains = detect_supersession_chains(snapshots)
    if not chains:
        return None
    if len(chains) > 1:
        raise ValueError("Multiple supersession chains detected")
    return chains[0][-1]


def collect_snapshot_annotations(
    snapshots: Iterable[PolicyEvaluationSnapshot | Mapping[str, object]]
) -> dict[str, tuple[PolicyEvaluationSnapshot, ...]]:
    parsed_snapshots = [_to_snapshot(entry) for entry in snapshots]
    annotations: dict[str, list[PolicyEvaluationSnapshot]] = {}
    for snapshot in parsed_snapshots:
        parent_fingerprint = snapshot.parent_snapshot_fingerprint
        if parent_fingerprint is None:
            continue
        if snapshot.lineage_relation in _AUTHORITATIVE_SNAPSHOT_RELATIONS:
            continue
        annotations.setdefault(parent_fingerprint, []).append(snapshot)

    return {
        fingerprint: tuple(entries) for fingerprint, entries in annotations.items()
    }


def validate_lineage_chain(
    aggregates: Iterable[ToolingStatusAggregate | Mapping[str, object]],
    *,
    profile: RedactionProfile = RedactionProfile.FULL,
) -> None:
    parsed: list[ToolingStatusAggregate] = [
        _to_aggregate(entry, profile=profile) for entry in aggregates
    ]
    seen: dict[str, ToolingStatusAggregate] = {}
    for aggregate in parsed:
        fingerprint = aggregate.fingerprint_for_profile(profile)
        if fingerprint in seen:
            raise ValueError("Duplicate fingerprints detected in lineage chain")
        seen[fingerprint] = aggregate

    for aggregate in parsed:
        parent_fingerprint = aggregate.lineage_parent_fingerprint
        if parent_fingerprint is None:
            continue
        if parent_fingerprint == aggregate.fingerprint_for_profile(profile):
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
