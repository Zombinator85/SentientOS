"""Bounded, non-authoritative causal owner introspection.

The compositor in this module joins independently produced reports; it does not
interpret them.  In particular, a projection is neither truth, authority, nor
an effect receipt.  Providers are explicit and are expected to whitelist only
metadata that their owner can support.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence, cast

SCHEMA_VERSION = "sentientos.causal_introspection:v1"
SNAPSHOT_DELTA_SCHEMA = "sentientos.causal_introspection_snapshot_delta:v1"
CONFIG_ENV = "SENTIENTOS_CAUSAL_INTROSPECTION_CONFIG"
MAX_PROJECTIONS = 64
MAX_REFERENCES = 128
MAX_OBSERVATIONS = 128
MAX_FINDINGS = 32
MAX_PROJECTION_BYTES = 131_072
MAX_SNAPSHOT_BYTES = 2_097_152
MAX_SNAPSHOT_GENERATIONS = 4096
MAX_SNAPSHOT_CUSTODY_BYTES = 268_435_456
MAX_CONFIG_BYTES = 16_384

DOMAINS = frozenset({
    "installation", "model_supply", "model_serving", "model_succession",
    "software_succession", "maintenance", "authority_admission", "effects",
    "world_state", "longitudinal_self_model", "developmental_history",
    "persistent_epistemics", "canonical_memory", "causal_resources",
    "embodiment", "federation", "runtime_supervision",
})
REFERENCE_KINDS = frozenset({
    "principal", "purpose", "configuration", "lineage", "model",
    "software_generation", "authority_evidence", "admission", "execution",
    "effect", "consequence", "resource_attribution", "memory_custody",
    "epistemic_state", "developmental_record", "world_state", "body",
    "federation", "supervision", "artifact", "receipt",
})
OBSERVATION_CLASSES = frozenset({
    "identity", "configuration", "lifecycle", "currentness", "health",
    "readiness", "lineage", "authority_evidence", "execution_evidence",
    "effect_evidence", "resource_attribution", "consequence", "count", "boundary",
})
PRODUCTION_POSTURES = frozenset({"production", "rehearsal", "synthetic_test", "historical", "unknown"})
TRACE_DIMENSIONS = ("WHO", "WHY", "MAY", "WHAT_EXECUTED", "WHAT_IT_COST", "WHAT_HAPPENED")
TRACE_POSTURES = frozenset({"observed", "evidence_reference_only", "not_observed", "not_composed", "unknown"})
SECRET_TOKENS = ("password", "secret", "api_key", "private_key", "credential", "bearer_token", "access_token", "refresh_token")
FORBIDDEN_KEYS = frozenset({
    "overall_system_truth", "overall_identity", "overall_goal", "overall_policy",
    "overall_health_conclusion", "overall_safety_conclusion", "overall_sentience",
    "persistent_identity", "inference_performed", "local_adoption", "resource_allocation",
})


class IntrospectionError(ValueError):
    """A fail-closed introspection boundary or custody failure."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise IntrospectionError("bounded_json_required") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _plain(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {key: _plain(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return cast(dict[str, Any], value)


@dataclass(frozen=True)
class CausalReference:
    reference_kind: str
    reference_id: str
    reference_digest: str
    relation: str
    source_owner_id: str
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class OwnerObservation:
    observation_key: str
    bounded_value: Any
    observation_class: str
    source_refs: tuple[str, ...] = ()
    freshness: str = "unknown"
    evidence_posture: str = "owner_report"
    production_posture: str = "unknown"


@dataclass(frozen=True)
class SemanticTraceDimension:
    observed_refs: tuple[str, ...] = ()
    posture: str = "not_observed"


def empty_semantic_trace() -> Mapping[str, SemanticTraceDimension]:
    return {dimension: SemanticTraceDimension() for dimension in TRACE_DIMENSIONS}


@dataclass(frozen=True)
class ProjectionPosture:
    read_only: bool = True
    current_truth: bool = False
    authority: bool = False
    policy: bool = False
    goal: bool = False
    permission: bool = False
    execution_authority: bool = False
    admission_authority: bool = False
    adoption_authority: bool = False
    source_mutation_authority: bool = False


@dataclass(frozen=True)
class OwnerIntrospectionProjection:
    projection_id: str
    projection_digest: str
    owner_id: str
    owner_kind: str
    domain: str
    capture_tick: str
    observation_posture: str
    source_references: tuple[CausalReference, ...]
    causal_references: tuple[CausalReference, ...]
    observations: tuple[OwnerObservation, ...]
    findings: tuple[str, ...] = ()
    semantic_trace: Mapping[str, SemanticTraceDimension] = field(default_factory=empty_semantic_trace)
    posture: ProjectionPosture = field(default_factory=ProjectionPosture)
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class CaptureContext:
    tick_id: str
    repository_revision: str | None = None
    repository_tree: str | None = None
    runtime_generation: str | None = None
    capture_posture: str = "unknown"


class OwnerIntrospectionProvider(Protocol):
    provider_id: str

    def project(self, context: CaptureContext) -> OwnerIntrospectionProjection: ...


@dataclass(frozen=True)
class ProviderRegistration:
    owner_id: str
    domain: str
    provider: OwnerIntrospectionProvider


@dataclass(frozen=True)
class CaptureFinding:
    owner_id: str
    domain: str
    error_code: str
    error_class: str


@dataclass(frozen=True)
class ProjectionConflict:
    observation_key: str
    projection_ids: tuple[str, ...]


@dataclass(frozen=True)
class CausalIntrospectionSnapshot:
    snapshot_id: str
    snapshot_digest: str
    generation: int
    predecessor_snapshot_digest: str | None
    capture_tick: str
    repository_revision: str | None
    repository_tree: str | None
    projection_ids: tuple[str, ...]
    projection_digests: tuple[str, ...]
    projections: tuple[OwnerIntrospectionProjection, ...]
    capture_findings: tuple[CaptureFinding, ...]
    conflicts: tuple[ProjectionConflict, ...]
    completion_posture: str
    authority: bool = False
    current_truth: bool = False
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class IntrospectionConfig:
    enabled: bool
    custody_root: Path
    world_state_consumption_enabled: bool
    max_projections: int
    enabled_domains: tuple[str, ...]
    required_domains: tuple[str, ...]
    schema: str = SCHEMA_VERSION


def load_config(path: str | Path | None = None) -> IntrospectionConfig | None:
    selected = str(path) if path is not None else os.environ.get(CONFIG_ENV)
    if not selected:
        return None
    config_path = Path(os.path.abspath(selected))
    directory_fd: int | None = None
    try:
        supports_relative = bool(
            os.name == "posix" and hasattr(os, "O_NOFOLLOW")
            and hasattr(os, "O_DIRECTORY") and os.open in os.supports_dir_fd
            and os.stat in os.supports_dir_fd
        )
        if supports_relative:
            directory_fd = os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            for component in config_path.parent.parts[1:]:
                next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=directory_fd)
                os.close(directory_fd)
                directory_fd = next_fd
            metadata = os.stat(config_path.name, dir_fd=directory_fd, follow_symlinks=False)
        else:
            current = Path(config_path.anchor)
            for component in config_path.parent.parts[1:]:
                current = current / component
                if not stat.S_ISDIR(current.lstat().st_mode):
                    raise OSError("configuration parent is not a directory")
            metadata = config_path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_CONFIG_BYTES:
            raise IntrospectionError("configuration_file_unbounded_or_not_regular")
        descriptor = (os.open(config_path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
            if directory_fd is not None else
            os.open(config_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)))
        try:
            opened = os.fstat(descriptor)
            if (not stat.S_ISREG(opened.st_mode) or opened.st_ino != metadata.st_ino
                    or opened.st_dev != metadata.st_dev or opened.st_size > MAX_CONFIG_BYTES):
                raise IntrospectionError("configuration_file_changed_during_open")
            chunks: list[bytes] = []
            remaining = MAX_CONFIG_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(4096, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            config_data = b"".join(chunks)
            if len(config_data) > MAX_CONFIG_BYTES:
                raise IntrospectionError("configuration_file_unbounded_or_not_regular")
        finally:
            os.close(descriptor)
        payload = json.loads(config_data.decode("utf-8"))
    except IntrospectionError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntrospectionError("configuration_unavailable_or_invalid") from exc
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
    if not isinstance(payload, dict):
        raise IntrospectionError("configuration_object_required")
    if payload.get("schema") != SCHEMA_VERSION:
        raise IntrospectionError("unsupported_config_schema")
    allowed = {"schema", "enabled", "custody_root", "world_state_consumption_enabled",
        "max_projections", "enabled_domains", "required_domains"}
    if set(payload) - allowed or not {"schema", "enabled", "custody_root",
            "world_state_consumption_enabled", "enabled_domains", "required_domains"} <= set(payload):
        raise IntrospectionError("configuration_shape_invalid")
    if (not isinstance(payload["enabled"], bool)
            or not isinstance(payload["world_state_consumption_enabled"], bool)):
        raise IntrospectionError("configuration_boolean_invalid")
    root_value = payload.get("custody_root")
    if not isinstance(root_value, str) or not root_value:
        raise IntrospectionError("absolute_custody_root_required")
    root = Path(root_value)
    if not root.is_absolute():
        raise IntrospectionError("absolute_custody_root_required")
    raw_enabled = payload["enabled_domains"]
    raw_required = payload["required_domains"]
    if (not isinstance(raw_enabled, list) or not isinstance(raw_required, list)
            or any(not isinstance(item, str) for item in (*raw_enabled, *raw_required))):
        raise IntrospectionError("configuration_domains_invalid")
    enabled = tuple(raw_enabled)
    required = tuple(raw_required)
    if len(set(enabled)) != len(enabled) or len(set(required)) != len(required):
        raise IntrospectionError("duplicate_config_domain")
    if not set(enabled) <= DOMAINS or not set(required) <= set(enabled):
        raise IntrospectionError("invalid_config_domains")
    maximum = payload.get("max_projections", MAX_PROJECTIONS)
    if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 1 or maximum > MAX_PROJECTIONS:
        raise IntrospectionError("invalid_max_projections")
    return IntrospectionConfig(payload["enabled"], root,
        payload["world_state_consumption_enabled"], maximum,
        enabled, required)


def _projection_payload(projection: OwnerIntrospectionProjection) -> dict[str, Any]:
    value = _plain(projection)
    value.pop("projection_id", None)
    value.pop("projection_digest", None)
    return cast(dict[str, Any], value)


def build_projection(*, owner_id: str, owner_kind: str, domain: str,
        context: CaptureContext, source_references: Sequence[CausalReference],
        causal_references: Sequence[CausalReference], observations: Sequence[OwnerObservation],
        findings: Sequence[str] = (), semantic_trace: Mapping[str, SemanticTraceDimension] | None = None,
        observation_posture: str = "owner_report") -> OwnerIntrospectionProjection:
    provisional = OwnerIntrospectionProjection("", "", owner_id, owner_kind, domain,
        context.tick_id, observation_posture, tuple(source_references), tuple(causal_references),
        tuple(observations), tuple(findings), semantic_trace or empty_semantic_trace())
    digest = _digest(_projection_payload(provisional))
    projection = replace(provisional, projection_id=f"owner-projection-{digest[:20]}", projection_digest=digest)
    validate_projection(projection, capture_posture=context.capture_posture)
    return projection


def _walk_keys(value: Any) -> Sequence[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            found.append(str(key).lower())
            found.extend(_walk_keys(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(_walk_keys(item))
    return found


def validate_projection(projection: OwnerIntrospectionProjection, *, capture_posture: str = "unknown") -> None:
    if (not isinstance(projection.owner_id, str) or not projection.owner_id
            or not projection.owner_id.strip()
            or not isinstance(projection.owner_kind, str) or not projection.owner_kind
            or not projection.owner_kind.strip()):
        raise IntrospectionError("owner_identity_required")
    if (not isinstance(projection.capture_tick, str) or not projection.capture_tick
            or not projection.capture_tick.strip()):
        raise IntrospectionError("capture_tick_required")
    if projection.domain not in DOMAINS:
        raise IntrospectionError("unregistered_domain")
    if projection.posture != ProjectionPosture():
        raise IntrospectionError("projection_authority_widened")
    if len(projection.observations) > MAX_OBSERVATIONS or len(projection.findings) > MAX_FINDINGS:
        raise IntrospectionError("projection_bounds_exceeded")
    references = projection.source_references + projection.causal_references
    if len(references) > MAX_REFERENCES:
        raise IntrospectionError("reference_bounds_exceeded")
    reference_ids: set[str] = set()
    for reference in references:
        if (not isinstance(reference.reference_kind, str)
                or reference.reference_kind not in REFERENCE_KINDS
                or not isinstance(reference.reference_id, str) or not reference.reference_id
                or not reference.reference_id.strip()
                or not isinstance(reference.reference_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", reference.reference_digest) is None
                or not isinstance(reference.relation, str) or not reference.relation
                or not reference.relation.strip()
                or not isinstance(reference.source_owner_id, str) or not reference.source_owner_id
                or not reference.source_owner_id.strip()):
            raise IntrospectionError("invalid_causal_reference")
        if reference.schema_version != SCHEMA_VERSION:
            raise IntrospectionError("invalid_causal_reference")
        if reference.reference_id in reference_ids:
            raise IntrospectionError("duplicate_causal_reference_id")
        reference_ids.add(reference.reference_id)
    for observation in projection.observations:
        key = observation.observation_key.lower()
        if (not key or observation.observation_class not in OBSERVATION_CLASSES
                or observation.production_posture not in PRODUCTION_POSTURES):
            raise IntrospectionError("invalid_observation")
        if any(token in key for token in SECRET_TOKENS) or any(any(token in nested for token in SECRET_TOKENS) for nested in _walk_keys(observation.bounded_value)):
            raise IntrospectionError("credential_material_rejected")
        if key in FORBIDDEN_KEYS:
            raise IntrospectionError("semantic_collapse_rejected")
        if (not isinstance(observation.source_refs, tuple)
                or any(not isinstance(reference_id, str) or reference_id not in reference_ids
                    for reference_id in observation.source_refs)):
            raise IntrospectionError("observation_source_reference_unresolved")
        if capture_posture == "synthetic_test" and observation.production_posture == "production":
            raise IntrospectionError("synthetic_cannot_claim_production")
        if key == "effect_proven" and observation.bounded_value is True:
            qualifying = {reference.reference_id for reference in references if reference.reference_kind in {"effect", "receipt"}}
            if not qualifying.intersection(observation.source_refs):
                raise IntrospectionError("effect_proof_reference_required")
        if key.endswith("_allocation") or key in {"cpu_allocation", "gpu_allocation", "ram_allocation", "vram_allocation", "token_allocation", "energy_allocation", "thermal_allocation"}:
            raise IntrospectionError("allocation_not_owned_by_introspection")
        if projection.domain == "canonical_memory" and key not in {"store_id", "generation", "record_count", "retention_class_counts", "receipt_ids", "tomb_count", "withdrawal_count"}:
            raise IntrospectionError("memory_metadata_only")
        if projection.domain == "persistent_epistemics" and key in {"truth", "current_truth"}:
            raise IntrospectionError("epistemic_position_not_truth")
        if projection.domain == "federation" and key in {"authority", "policy", "adoption", "truth"}:
            raise IntrospectionError("federation_sovereignty_boundary")
        if projection.domain == "model_serving" and key == "inference":
            raise IntrospectionError("serving_not_inference")
        _canonical(observation.bounded_value)
    if set(projection.semantic_trace) != set(TRACE_DIMENSIONS):
        raise IntrospectionError("semantic_trace_incomplete")
    for dimension in projection.semantic_trace.values():
        if dimension.posture not in TRACE_POSTURES or not set(dimension.observed_refs) <= reference_ids:
            raise IntrospectionError("invalid_semantic_trace")
    expected = _digest(_projection_payload(projection))
    if projection.projection_digest != expected or projection.projection_id != f"owner-projection-{expected[:20]}":
        raise IntrospectionError("projection_digest_mismatch")
    if len(_canonical(_plain(projection))) > MAX_PROJECTION_BYTES:
        raise IntrospectionError("projection_bytes_exceeded")


class MappingMetadataProvider:
    """Pure adapter over an already-bounded, explicitly supplied metadata mapping."""

    def __init__(self, *, provider_id: str, owner_id: str, owner_kind: str, domain: str,
            observations: Sequence[OwnerObservation], references: Sequence[CausalReference] = (),
            semantic_trace: Mapping[str, SemanticTraceDimension] | None = None):
        self.provider_id = provider_id
        self._owner_id = owner_id
        self._owner_kind = owner_kind
        self._domain = domain
        self._observations = tuple(observations)
        self._references = tuple(references)
        self._semantic_trace = semantic_trace

    def project(self, context: CaptureContext) -> OwnerIntrospectionProjection:
        return build_projection(owner_id=self._owner_id, owner_kind=self._owner_kind,
            domain=self._domain, context=context, source_references=self._references,
            causal_references=(), observations=self._observations,
            semantic_trace=self._semantic_trace)


class LiveOwnerMetadataProvider:
    """Read a bounded owner-local projection at capture time.

    The callback is explicitly supplied by the canonical compositor.  This is
    deliberately not discovery: it neither scans for owners nor retains a
    startup snapshot, and it has no mutation or invocation surface.
    """

    def __init__(self, *, provider_id: str, owner_id: str, owner_kind: str,
            domain: str, inspect: Callable[[], Mapping[str, Any]],
            observation_classes: Mapping[str, str]):
        self.provider_id = provider_id
        self._owner_id = owner_id
        self._owner_kind = owner_kind
        self._domain = domain
        self._inspect = inspect
        self._observation_classes = dict(observation_classes)
        if (domain not in DOMAINS or not self._observation_classes
                or any(not isinstance(key, str) or not key for key in self._observation_classes)
                or any(not isinstance(value, str) or value not in OBSERVATION_CLASSES
                    for value in self._observation_classes.values())):
            raise IntrospectionError("live_provider_observation_schema_invalid")

    def project(self, context: CaptureContext) -> OwnerIntrospectionProjection:
        metadata = dict(self._inspect())
        if set(metadata) != set(self._observation_classes):
            raise IntrospectionError("owner_projection_shape_changed")
        observations = tuple(OwnerObservation(
            observation_key=key, bounded_value=metadata[key],
            observation_class=self._observation_classes[key], freshness="current",
            production_posture=context.capture_posture)
            for key in sorted(metadata))
        return build_projection(owner_id=self._owner_id, owner_kind=self._owner_kind,
            domain=self._domain, context=context, source_references=(),
            causal_references=(), observations=observations)


def _snapshot_payload(snapshot: CausalIntrospectionSnapshot) -> dict[str, Any]:
    value = _plain(snapshot)
    value.pop("snapshot_id", None)
    value.pop("snapshot_digest", None)
    return cast(dict[str, Any], value)


def _decode_projection(payload: Mapping[str, Any]) -> OwnerIntrospectionProjection:
    def refs(values: Sequence[Mapping[str, Any]]) -> tuple[CausalReference, ...]:
        return tuple(CausalReference(**item) for item in values)
    trace = {key: SemanticTraceDimension(tuple(value["observed_refs"]), value["posture"])
        for key, value in payload["semantic_trace"].items()}
    return OwnerIntrospectionProjection(
        projection_id=payload["projection_id"], projection_digest=payload["projection_digest"],
        owner_id=payload["owner_id"], owner_kind=payload["owner_kind"], domain=payload["domain"],
        capture_tick=payload["capture_tick"], observation_posture=payload["observation_posture"],
        source_references=refs(payload["source_references"]), causal_references=refs(payload["causal_references"]),
        observations=tuple(OwnerObservation(
            observation_key=item["observation_key"], bounded_value=item["bounded_value"],
            observation_class=item["observation_class"], source_refs=tuple(item["source_refs"]),
            freshness=item["freshness"], evidence_posture=item["evidence_posture"],
            production_posture=item["production_posture"])
            for item in payload["observations"]),
        findings=tuple(payload["findings"]), semantic_trace=trace,
        posture=ProjectionPosture(**payload["posture"]), schema_version=payload["schema_version"])


def _decode_snapshot(payload: Mapping[str, Any]) -> CausalIntrospectionSnapshot:
    return CausalIntrospectionSnapshot(
        snapshot_id=payload["snapshot_id"], snapshot_digest=payload["snapshot_digest"],
        generation=int(payload["generation"]), predecessor_snapshot_digest=payload["predecessor_snapshot_digest"],
        capture_tick=payload["capture_tick"], repository_revision=payload["repository_revision"],
        repository_tree=payload["repository_tree"], projection_ids=tuple(payload["projection_ids"]),
        projection_digests=tuple(payload["projection_digests"]),
        projections=tuple(_decode_projection(item) for item in payload["projections"]),
        capture_findings=tuple(CaptureFinding(**item) for item in payload["capture_findings"]),
        conflicts=tuple(ProjectionConflict(item["observation_key"], tuple(item["projection_ids"])) for item in payload["conflicts"]),
        completion_posture=payload["completion_posture"], authority=payload["authority"],
        current_truth=payload["current_truth"], schema_version=payload["schema_version"])


def _projection_conflicts(
        projections: Sequence[OwnerIntrospectionProjection]) -> tuple[ProjectionConflict, ...]:
    """Derive conflicts from owner reports without selecting a winner."""
    groups: dict[str, dict[str, list[str]]] = {}
    for projection in projections:
        for observation in projection.observations:
            encoded = _canonical(observation.bounded_value).decode("ascii")
            groups.setdefault(observation.observation_key, {}).setdefault(encoded, []).append(
                projection.projection_id)
    return tuple(ProjectionConflict(key, tuple(sorted(
        projection_id for ids in values.values() for projection_id in ids)))
        for key, values in sorted(groups.items()) if len(values) > 1)


def _validate_snapshot_contents(snapshot: CausalIntrospectionSnapshot) -> None:
    if not isinstance(snapshot.capture_tick, str) or not snapshot.capture_tick:
        raise IntrospectionError("capture_tick_required")
    if (snapshot.schema_version != SCHEMA_VERSION or snapshot.authority is not False
            or snapshot.current_truth is not False or type(snapshot.generation) is not int
            or snapshot.generation < 1):
        raise IntrospectionError("invalid_snapshot_posture")
    if (not isinstance(snapshot.capture_findings, tuple)
            or any(not isinstance(item, CaptureFinding) for item in snapshot.capture_findings)
            or len(snapshot.capture_findings) > MAX_PROJECTIONS + len(DOMAINS)):
        raise IntrospectionError("snapshot_findings_invalid")
    expected_completion = "partial" if snapshot.capture_findings else "complete"
    if snapshot.completion_posture != expected_completion:
        raise IntrospectionError("snapshot_completion_posture_mismatch")
    if len(snapshot.projections) > MAX_PROJECTIONS:
        raise IntrospectionError("snapshot_projection_limit_exceeded")
    owner_ids = tuple(projection.owner_id for projection in snapshot.projections)
    projection_ids = tuple(projection.projection_id for projection in snapshot.projections)
    if len(set(owner_ids)) != len(owner_ids) or len(set(projection_ids)) != len(projection_ids):
        raise IntrospectionError("snapshot_projection_identity_not_unique")
    if tuple(item.projection_id for item in snapshot.projections) != snapshot.projection_ids:
        raise IntrospectionError("projection_inventory_mismatch")
    if tuple(item.projection_digest for item in snapshot.projections) != snapshot.projection_digests:
        raise IntrospectionError("projection_digest_inventory_mismatch")
    for projection in snapshot.projections:
        validate_projection(projection)
        if projection.capture_tick != snapshot.capture_tick:
            raise IntrospectionError("projection_capture_tick_mismatch")
    if (not isinstance(snapshot.conflicts, tuple)
            or snapshot.conflicts != _projection_conflicts(snapshot.projections)):
        raise IntrospectionError("snapshot_conflict_inventory_mismatch")
    expected = _digest(_snapshot_payload(snapshot))
    if snapshot.snapshot_digest != expected or snapshot.snapshot_id != f"causal-introspection-{expected[:20]}":
        raise IntrospectionError("snapshot_digest_mismatch")
    if len(_canonical(_plain(snapshot))) > MAX_SNAPSHOT_BYTES:
        raise IntrospectionError("snapshot_bytes_exceeded")


def validate_snapshot(snapshot: CausalIntrospectionSnapshot, predecessor: CausalIntrospectionSnapshot | None = None) -> None:
    _validate_snapshot_contents(snapshot)
    if predecessor is None:
        if snapshot.generation != 1 or snapshot.predecessor_snapshot_digest is not None:
            raise IntrospectionError("invalid_genesis_snapshot")
    elif (snapshot.generation != predecessor.generation + 1
            or snapshot.predecessor_snapshot_digest != predecessor.snapshot_digest):
        raise IntrospectionError("predecessor_mismatch")


def _build_snapshot_delta(previous: CausalIntrospectionSnapshot,
                          current: CausalIntrospectionSnapshot, *,
                          contents_validated: bool = False) -> Mapping[str, Any]:
    """Describe owner-local evidence changes across one verified snapshot edge.

    The report contains only digests for changed observation values. New or
    removed source references retain their declared relationship and source
    identity, but those declarations do not establish causation.
    """
    if not contents_validated:
        _validate_snapshot_contents(previous)
        _validate_snapshot_contents(current)
    if (current.generation != previous.generation + 1
            or current.predecessor_snapshot_digest != previous.snapshot_digest):
        raise IntrospectionError("predecessor_mismatch")

    previous_owners = {item.owner_id: item for item in previous.projections}
    current_owners = {item.owner_id: item for item in current.projections}
    failed_current = {(item.owner_id, item.domain) for item in current.capture_findings}
    owner_changes: list[dict[str, Any]] = []

    def observation_digests(projection: OwnerIntrospectionProjection) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {}
        for observation in projection.observations:
            grouped.setdefault(observation.observation_key, []).append(
                _digest(observation.bounded_value))
        return {key: sorted(values) for key, values in sorted(grouped.items())}

    def reference_digests(projection: OwnerIntrospectionProjection) -> dict[str, str]:
        return {item.reference_id: _digest(_plain(item))
                for item in projection.source_references + projection.causal_references}

    for owner_id in sorted(set(previous_owners) | set(current_owners)):
        before = previous_owners.get(owner_id)
        after = current_owners.get(owner_id)
        if before is None:
            if after is None:
                raise IntrospectionError("snapshot_delta_owner_index_invalid")
            status = "appeared_in_capture"
            changed_observations: list[dict[str, Any]] = []
            changed_references: list[dict[str, Any]] = []
            changed_trace: list[str] = []
        elif after is None:
            status = ("unavailable_in_current_capture"
                      if (owner_id, before.domain) in failed_current
                      or ("required-domain", before.domain) in failed_current
                      else "not_observed_in_current_capture")
            changed_observations = []
            changed_references = []
            changed_trace = []
        elif before.domain != after.domain or before.owner_kind != after.owner_kind:
            status = "owner_descriptor_changed"
            changed_observations = []
            changed_references = []
            changed_trace = []
        else:
            before_observations = observation_digests(before)
            after_observations = observation_digests(after)
            changed_observations = [
                {"observation_key": key,
                 "previous_value_digests": before_observations.get(key, []),
                 "current_value_digests": after_observations.get(key, [])}
                for key in sorted(set(before_observations) | set(after_observations))
                if before_observations.get(key, []) != after_observations.get(key, [])
            ]
            before_references = reference_digests(before)
            after_references = reference_digests(after)
            changed_references = [
                {"reference_id": reference_id,
                 "previous_reference_digest": before_references.get(reference_id),
                 "current_reference_digest": after_references.get(reference_id)}
                for reference_id in sorted(set(before_references) | set(after_references))
                if before_references.get(reference_id) != after_references.get(reference_id)
            ]
            changed_trace = [dimension for dimension in TRACE_DIMENSIONS
                if _plain(before.semantic_trace[dimension]) != _plain(after.semantic_trace[dimension])]
            status = ("changed" if changed_observations or changed_references or changed_trace
                      else "stable")

        owner_changes.append({
            "owner_id": owner_id,
            "previous_domain": before.domain if before is not None else None,
            "current_domain": after.domain if after is not None else None,
            "previous_owner_kind": before.owner_kind if before is not None else None,
            "current_owner_kind": after.owner_kind if after is not None else None,
            "previous_projection_digest": before.projection_digest if before is not None else None,
            "current_projection_digest": after.projection_digest if after is not None else None,
            "status": status,
            "changed_observations": changed_observations,
            "changed_references": changed_references,
            "changed_semantic_trace_dimensions": changed_trace,
        })

    body: dict[str, Any] = {
        "schema_version": SNAPSHOT_DELTA_SCHEMA,
        "previous_snapshot_id": previous.snapshot_id,
        "previous_snapshot_digest": previous.snapshot_digest,
        "previous_generation": previous.generation,
        "previous_capture_tick": previous.capture_tick,
        "current_snapshot_id": current.snapshot_id,
        "current_snapshot_digest": current.snapshot_digest,
        "current_generation": current.generation,
        "current_capture_tick": current.capture_tick,
        "previous_completion_posture": previous.completion_posture,
        "current_completion_posture": current.completion_posture,
        "owner_changes": owner_changes,
        "descriptive_only": True,
        "causal_inference_performed": False,
        "causal_claim_made": False,
        "current_truth": False,
        "authority": False,
    }
    digest = _digest(body)
    body["delta_id"] = f"introspection-delta-{digest[:20]}"
    body["delta_digest"] = digest
    return body


def build_snapshot_delta(history: Sequence[CausalIntrospectionSnapshot]) -> Mapping[str, Any]:
    """Build a delta from the last two snapshots after verifying full custody history."""
    if (not isinstance(history, Sequence) or isinstance(history, (str, bytes))
            or len(history) < 2 or len(history) > MAX_SNAPSHOT_GENERATIONS):
        raise IntrospectionError("snapshot_delta_history_invalid")
    predecessor: CausalIntrospectionSnapshot | None = None
    for snapshot in history:
        validate_snapshot(snapshot, predecessor)
        predecessor = snapshot
    return _build_snapshot_delta(history[-2], history[-1], contents_validated=True)


def verify_snapshot_delta(value: Mapping[str, Any],
                          history: Sequence[CausalIntrospectionSnapshot]) -> Mapping[str, Any]:
    expected = build_snapshot_delta(history)
    if dict(value) != dict(expected):
        raise IntrospectionError("snapshot_delta_mismatch")
    return expected


def _snapshot_capacity_error(generation: int, custody_bytes: int, next_snapshot_bytes: int) -> str | None:
    """Return the recovery limit that a prospective append would violate."""
    if generation < 0 or custody_bytes < 0 or next_snapshot_bytes < 0:
        return "snapshot_capacity_measurement_invalid"
    if generation >= MAX_SNAPSHOT_GENERATIONS:
        return "snapshot_generation_limit_exceeded"
    if custody_bytes + next_snapshot_bytes > MAX_SNAPSHOT_CUSTODY_BYTES:
        return "snapshot_custody_limit_exceeded"
    return None


class CausalIntrospectionRuntime:
    def __init__(self, config: IntrospectionConfig, registrations: Sequence[ProviderRegistration]):
        if not isinstance(config, IntrospectionConfig) or config.schema != SCHEMA_VERSION:
            raise IntrospectionError("unsupported_config_schema")
        if (type(config.enabled) is not bool
                or type(config.world_state_consumption_enabled) is not bool):
            raise IntrospectionError("configuration_boolean_invalid")
        if not isinstance(config.custody_root, Path) or not config.custody_root.is_absolute():
            raise IntrospectionError("absolute_custody_root_required")
        if (type(config.max_projections) is not int or config.max_projections < 1
                or config.max_projections > MAX_PROJECTIONS):
            raise IntrospectionError("invalid_max_projections")
        if (not isinstance(config.enabled_domains, tuple)
                or not isinstance(config.required_domains, tuple)
                or any(not isinstance(item, str) for item in (*config.enabled_domains, *config.required_domains))):
            raise IntrospectionError("configuration_domains_invalid")
        if (len(set(config.enabled_domains)) != len(config.enabled_domains)
                or len(set(config.required_domains)) != len(config.required_domains)):
            raise IntrospectionError("duplicate_config_domain")
        if (not set(config.enabled_domains) <= DOMAINS
                or not set(config.required_domains) <= set(config.enabled_domains)):
            raise IntrospectionError("invalid_config_domains")
        if not isinstance(registrations, Sequence) or len(registrations) > config.max_projections:
            raise IntrospectionError("provider_count_exceeded")
        self.config = config
        self.registrations = tuple(sorted(registrations, key=lambda item: (item.domain, item.owner_id)))
        if any(isinstance(item.provider, CausalIntrospectionRuntime) or item.owner_id == "causal_introspection_runtime" for item in self.registrations):
            raise IntrospectionError("recursive_fabric_provider_rejected")
        owners = [item.owner_id for item in self.registrations]
        providers = [item.provider.provider_id for item in self.registrations]
        if (any(not isinstance(owner, str) or not owner for owner in owners)
                or any(not isinstance(provider, str) or not provider for provider in providers)):
            raise IntrospectionError("provider_registration_identity_required")
        if len(set(owners)) != len(owners) or len(set(providers)) != len(providers):
            raise IntrospectionError("duplicate_provider_registration")
        if any(item.domain not in config.enabled_domains or item.domain not in DOMAINS for item in self.registrations):
            raise IntrospectionError("provider_domain_not_enabled")

    def _open_custody_root(self, *, create: bool) -> int | None:
        """Open custody ancestry without following links on supported POSIX hosts."""
        root = self.config.custody_root
        if ".." in root.parts:
            raise IntrospectionError("custody_root_invalid")
        required = (os.open, os.mkdir, os.link, os.unlink)
        descriptor_relative = bool(
            os.name == "posix" and hasattr(os, "O_NOFOLLOW")
            and hasattr(os, "O_DIRECTORY")
            and all(function in os.supports_dir_fd for function in required)
            and os.stat in os.supports_dir_fd
            and os.stat in os.supports_follow_symlinks
            and os.link in os.supports_follow_symlinks
        )
        if descriptor_relative:
            descriptor: int | None = None
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            try:
                descriptor = os.open(os.sep, flags)
                for component in root.parts[1:]:
                    if create:
                        try:
                            os.mkdir(component, 0o700, dir_fd=descriptor)
                        except FileExistsError:
                            pass
                    next_descriptor = os.open(component, flags, dir_fd=descriptor)
                    metadata = os.fstat(next_descriptor)
                    if not stat.S_ISDIR(metadata.st_mode):
                        os.close(next_descriptor)
                        raise IntrospectionError("custody_root_invalid")
                    os.close(descriptor)
                    descriptor = next_descriptor
                if descriptor is None:
                    raise IntrospectionError("custody_root_invalid")
                metadata = os.fstat(descriptor)
                if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                    raise IntrospectionError("custody_root_writable_by_other_users")
                result, descriptor = descriptor, None
                return result
            except IntrospectionError:
                raise
            except FileNotFoundError:
                if not create:
                    return None
                raise IntrospectionError("custody_root_invalid") from None
            except OSError as exc:
                raise IntrospectionError("custody_root_invalid") from exc
            finally:
                if descriptor is not None:
                    os.close(descriptor)

        # Platforms without descriptor-relative APIs retain compatibility but
        # reject every existing symlink component before path-based access.
        current = Path(root.anchor)
        for component in root.parts[1:]:
            current = current / component
            try:
                metadata = current.lstat()
            except FileNotFoundError:
                if not create:
                    return None
                current.mkdir(mode=0o700)
                metadata = current.lstat()
            if not stat.S_ISDIR(metadata.st_mode):
                raise IntrospectionError("custody_root_invalid")
        mode = current.lstat().st_mode
        if os.name == "posix" and mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise IntrospectionError("custody_root_writable_by_other_users")
        return None

    def _paths(self, directory_fd: int | None) -> list[str]:
        if directory_fd is None:
            try:
                names = os.listdir(self.config.custody_root)
            except FileNotFoundError:
                return []
        else:
            names = os.listdir(directory_fd)
        paths = sorted(name for name in names if name.startswith("generation-") and name.endswith(".json"))
        if len(paths) > MAX_SNAPSHOT_GENERATIONS:
            raise IntrospectionError("snapshot_generation_limit_exceeded")
        return paths

    def _names(self, directory_fd: int | None) -> list[str]:
        try:
            return os.listdir(directory_fd if directory_fd is not None else self.config.custody_root)
        except FileNotFoundError:
            return []

    @staticmethod
    def _read_snapshot(name: str, directory_fd: int | None, root: Path) -> bytes:
        try:
            metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False) if directory_fd is not None else (root / name).lstat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_SNAPSHOT_BYTES:
                raise IntrospectionError("snapshot_file_unbounded_or_not_regular")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            descriptor = os.open(name if directory_fd is not None else root / name, flags,
                dir_fd=directory_fd) if directory_fd is not None else os.open(root / name, flags)
            try:
                opened = os.fstat(descriptor)
                if (not stat.S_ISREG(opened.st_mode) or opened.st_ino != metadata.st_ino
                        or opened.st_dev != metadata.st_dev or opened.st_size > MAX_SNAPSHOT_BYTES):
                    raise IntrospectionError("snapshot_file_changed_during_open")
                chunks: list[bytes] = []
                remaining = MAX_SNAPSHOT_BYTES + 1
                while remaining:
                    chunk = os.read(descriptor, min(65_536, remaining))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                data = b"".join(chunks)
                if len(data) > MAX_SNAPSHOT_BYTES:
                    raise IntrospectionError("snapshot_file_unbounded_or_not_regular")
                return data
            finally:
                os.close(descriptor)
        except IntrospectionError:
            raise
        except OSError as exc:
            raise IntrospectionError("snapshot_file_unavailable") from exc

    @staticmethod
    def _publish_snapshot(name: str, data: bytes, directory_fd: int | None, root: Path) -> None:
        if directory_fd is None:
            descriptor, temporary_path = tempfile.mkstemp(prefix=".causal-introspection-",
                suffix=".tmp", dir=str(root))
            target = root / name
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.link(temporary_path, target, follow_symlinks=False)
                directory = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                try:
                    os.unlink(temporary_path)
                except FileNotFoundError:
                    pass
            return
        temporary = f".causal-introspection-{os.getpid()}-{os.urandom(8).hex()}.tmp"
        try:
            descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=directory_fd)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temporary, name, src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd, follow_symlinks=False)
            os.fsync(directory_fd)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except FileNotFoundError:
                pass

    def _reconstruct_with_size(self) -> tuple[tuple[CausalIntrospectionSnapshot, ...], int]:
        snapshots: list[CausalIntrospectionSnapshot] = []
        directory_fd = self._open_custody_root(create=False)
        try:
            paths = self._paths(directory_fd)
            total_bytes = 0
            for expected_generation, name in enumerate(paths, 1):
                if name != f"generation-{expected_generation:020d}.json":
                    raise IntrospectionError("missing_or_ambiguous_generation")
                data = self._read_snapshot(name, directory_fd, self.config.custody_root)
                total_bytes += len(data)
                if total_bytes > MAX_SNAPSHOT_CUSTODY_BYTES:
                    raise IntrospectionError("snapshot_custody_limit_exceeded")
                try:
                    snapshot = _decode_snapshot(json.loads(data.decode("utf-8")))
                except IntrospectionError:
                    raise
                except (UnicodeError, json.JSONDecodeError, KeyError, TypeError,
                        ValueError, RecursionError) as exc:
                    raise IntrospectionError("snapshot_payload_invalid") from exc
                if data != _canonical(_plain(snapshot)):
                    raise IntrospectionError("snapshot_noncanonical")
                validate_snapshot(snapshot, snapshots[-1] if snapshots else None)
                snapshots.append(snapshot)
            return tuple(snapshots), total_bytes
        finally:
            if directory_fd is not None:
                os.close(directory_fd)

    def reconstruct(self) -> tuple[CausalIntrospectionSnapshot, ...]:
        snapshots, _total_bytes = self._reconstruct_with_size()
        return snapshots

    def capture(self, context: CaptureContext) -> CausalIntrospectionSnapshot:
        if not self.config.enabled:
            raise IntrospectionError("introspection_disabled")
        if (not isinstance(context, CaptureContext)
                or not isinstance(context.tick_id, str) or not context.tick_id):
            raise IntrospectionError("capture_tick_required")
        history, custody_bytes = self._reconstruct_with_size()
        prior = history[-1] if history else None
        # A crash before the atomic hard-link publication can leave a private
        # staging file. It is not a committed generation and must never be
        # silently carried alongside later captures or treated as evidence.
        existing_directory_fd = self._open_custody_root(create=False)
        try:
            names = self._names(existing_directory_fd) if existing_directory_fd is not None else []
        finally:
            if existing_directory_fd is not None:
                os.close(existing_directory_fd)
        if any(name.startswith(".causal-introspection-") and name.endswith(".tmp") for name in names):
            raise IntrospectionError("snapshot_staging_recovery_required")
        projections: list[OwnerIntrospectionProjection] = []
        findings: list[CaptureFinding] = []
        for registration in self.registrations:
            try:
                projection = registration.provider.project(context)
                if projection.owner_id != registration.owner_id or projection.domain != registration.domain:
                    raise IntrospectionError("provider_registration_mismatch")
                if projection.capture_tick != context.tick_id:
                    raise IntrospectionError("provider_projection_tick_mismatch")
                validate_projection(projection, capture_posture=context.capture_posture)
                projections.append(projection)
            except Exception as exc:
                findings.append(CaptureFinding(registration.owner_id, registration.domain,
                    "provider_projection_failed", type(exc).__name__[:80]))
        provided_domains = {item.domain for item in projections}
        missing = set(self.config.required_domains) - provided_domains
        for domain in sorted(missing):
            findings.append(CaptureFinding("required-domain", domain, "required_provider_missing", "CoverageError"))
        projections.sort(key=lambda item: (item.domain, item.owner_id, item.projection_id))
        conflicts = self._conflicts(projections)
        if prior is not None and prior.capture_tick == context.tick_id:
            if (prior.projections == tuple(projections) and prior.capture_findings == tuple(findings)
                    and prior.conflicts == conflicts and prior.repository_revision == context.repository_revision
                    and prior.repository_tree == context.repository_tree):
                return prior
            raise IntrospectionError("same_tick_content_conflict")
        capacity_error = _snapshot_capacity_error(
            prior.generation if prior else 0, custody_bytes, 0
        )
        if capacity_error is not None:
            raise IntrospectionError(capacity_error)
        provisional = CausalIntrospectionSnapshot("", "", (prior.generation + 1 if prior else 1),
            prior.snapshot_digest if prior else None, context.tick_id, context.repository_revision,
            context.repository_tree, tuple(item.projection_id for item in projections),
            tuple(item.projection_digest for item in projections), tuple(projections), tuple(findings),
            conflicts, "partial" if findings else "complete")
        digest = _digest(_snapshot_payload(provisional))
        snapshot = replace(provisional, snapshot_id=f"causal-introspection-{digest[:20]}", snapshot_digest=digest)
        validate_snapshot(snapshot, prior)
        directory_fd = self._open_custody_root(create=True)
        name = f"generation-{snapshot.generation:020d}.json"
        data = _canonical(_plain(snapshot))
        capacity_error = _snapshot_capacity_error(snapshot.generation - 1, custody_bytes, len(data))
        if capacity_error is not None:
            raise IntrospectionError(capacity_error)
        try:
            self._publish_snapshot(name, data, directory_fd, self.config.custody_root)
        except FileExistsError:
            existing = self._read_snapshot(name, directory_fd, self.config.custody_root)
            if existing != data:
                raise IntrospectionError("same_generation_content_conflict")
            return _decode_snapshot(json.loads(existing))
        finally:
            if directory_fd is not None:
                os.close(directory_fd)
        return snapshot

    @staticmethod
    def _conflicts(projections: Sequence[OwnerIntrospectionProjection]) -> tuple[ProjectionConflict, ...]:
        return _projection_conflicts(projections)

    def prior_snapshot(self, *, before_generation: int) -> CausalIntrospectionSnapshot | None:
        eligible = [item for item in self.reconstruct() if item.generation < before_generation]
        return eligible[-1] if eligible else None

    def world_state_records(self, *, before_generation: int) -> list[dict[str, Any]]:
        if not self.config.world_state_consumption_enabled:
            return []
        eligible = [item for item in self.reconstruct() if item.generation < before_generation]
        if not eligible:
            return []
        snapshot = eligible[-1]
        records: list[dict[str, Any]] = []
        for projection in snapshot.projections:
            records.append({
                "source_kind": "owner_introspection", "source_id": projection.projection_id,
                "schema_version": projection.schema_version, "subject_id": projection.owner_id,
                "subject_kind": projection.domain, "stage": "observation",
                "disposition": "owner_reported", "evidence_strength": "owner_self_observation",
                "payload": {"projection_id": projection.projection_id,
                    "projection_digest": projection.projection_digest,
                    "introspection_snapshot_id": snapshot.snapshot_id,
                    "introspection_snapshot_digest": snapshot.snapshot_digest,
                    "introspection_snapshot_generation": snapshot.generation,
                    "introspection_snapshot_predecessor_digest": snapshot.predecessor_snapshot_digest,
                    "introspection_capture_tick": snapshot.capture_tick,
                    "introspection_snapshot_completion_posture": snapshot.completion_posture,
                    "owner_kind": projection.owner_kind,
                    "observations": [{"key": item.observation_key,
                        "value": item.bounded_value, "class": item.observation_class,
                        "freshness": item.freshness, "evidence_posture": item.evidence_posture,
                        "production_posture": item.production_posture,
                        "source_refs": list(item.source_refs)}
                        for item in projection.observations],
                    "source_references": [_plain(item) for item in projection.source_references],
                    "causal_references": [_plain(item) for item in projection.causal_references],
                    "semantic_trace": {key: _plain(value)
                        for key, value in projection.semantic_trace.items()},
                    "read_only": True, "current_truth": False, "authority": False},
                # The projection capture is the event time. This record is only
                # made available by a later-generation board and keeps its
                # original observation time through that temporal boundary.
                "observed_at": projection.capture_tick,
                "effect_claimed": False, "effect_proven": False,
            })
        if len(eligible) > 1:
            delta = _build_snapshot_delta(
                eligible[-2], snapshot, contents_validated=True)
            for owner_change in delta["owner_changes"]:
                if owner_change["status"] == "stable":
                    continue
                records.append({
                    "source_kind": "owner_introspection_delta",
                    "source_id": f"{delta['delta_id']}:{owner_change['owner_id']}",
                    "schema_version": SNAPSHOT_DELTA_SCHEMA,
                    "subject_id": owner_change["owner_id"],
                    "subject_kind": (owner_change["current_domain"]
                                     or owner_change["previous_domain"]
                                     or "unknown_owner_domain"),
                    "stage": "observation",
                    "disposition": owner_change["status"],
                    "evidence_strength": "predecessor_bound_owner_report_delta",
                    "payload": {
                        "snapshot_delta_id": delta["delta_id"],
                        "snapshot_delta_digest": delta["delta_digest"],
                        "previous_snapshot_id": delta["previous_snapshot_id"],
                        "previous_snapshot_digest": delta["previous_snapshot_digest"],
                        "previous_generation": delta["previous_generation"],
                        "current_snapshot_id": delta["current_snapshot_id"],
                        "current_snapshot_digest": delta["current_snapshot_digest"],
                        "current_generation": delta["current_generation"],
                        "owner_change": owner_change,
                        "descriptive_only": True,
                        "causal_inference_performed": False,
                        "causal_claim_made": False,
                        "current_truth": False,
                        "authority": False,
                    },
                    "observed_at": snapshot.capture_tick,
                    "effect_claimed": False,
                    "effect_proven": False,
                })
        if snapshot.capture_findings or snapshot.conflicts:
            retained_findings = snapshot.capture_findings[:MAX_PROJECTIONS]
            retained_conflicts = snapshot.conflicts[:MAX_PROJECTIONS]
            records.append({
                "source_kind": "owner_introspection",
                "source_id": f"introspection-diagnostics:{snapshot.snapshot_id}",
                "schema_version": snapshot.schema_version,
                "subject_id": "causal-introspection-snapshot",
                "subject_kind": "snapshot_diagnostics",
                "stage": "observation",
                "disposition": "incomplete" if snapshot.capture_findings else "recorded",
                "evidence_strength": "snapshot_integrity_metadata",
                "payload": {
                    "introspection_snapshot_id": snapshot.snapshot_id,
                    "introspection_snapshot_digest": snapshot.snapshot_digest,
                    "introspection_snapshot_generation": snapshot.generation,
                    "introspection_snapshot_predecessor_digest": snapshot.predecessor_snapshot_digest,
                    "introspection_capture_tick": snapshot.capture_tick,
                    "introspection_snapshot_completion_posture": snapshot.completion_posture,
                    "snapshot_completion_posture": snapshot.completion_posture,
                    "capture_findings": [{
                        "owner_id": item.owner_id, "domain": item.domain,
                        "error_code": item.error_code, "error_class": item.error_class,
                    } for item in retained_findings],
                    "omitted_capture_finding_count": len(snapshot.capture_findings) - len(retained_findings),
                    "conflicts": [{
                        "observation_key": item.observation_key,
                        "projection_ids": list(item.projection_ids),
                    } for item in retained_conflicts],
                    "omitted_conflict_count": len(snapshot.conflicts) - len(retained_conflicts),
                    "conflict_count": len(snapshot.conflicts),
                    "conflict_posture": "unresolved_no_winner_selected" if snapshot.conflicts else "none",
                    "read_only": True, "current_truth": False, "authority": False,
                },
                # These are diagnostics about the captured snapshot, timed at
                # the capture itself and exposed only through a later generation.
                "observed_at": snapshot.capture_tick,
                "effect_claimed": False, "effect_proven": False,
            })
        return records


# Static source-backed inventory.  "partial" is deliberate: composition never
# fabricates a provider merely to make the table green.
COVERAGE_MANIFEST: tuple[Mapping[str, str], ...] = tuple(
    {"domain": domain, "coverage": coverage, "rationale": rationale}
    for domain, coverage, rationale in (
        ("installation", "partial", "installation registry metadata is inspectable; production commissioning is not inferred"),
        ("model_supply", "partial", "publication, acquisition, commissioning, and activation remain distinct owners"),
        ("model_serving", "implemented", "serving controller has bounded non-model session metadata"),
        ("model_succession", "implemented", "transition journal and stage metadata are inspectable"),
        ("software_succession", "partial", "landing and running-generation evidence remain distinct"),
        ("maintenance", "implemented", "independent maintenance owners expose bounded feedback"),
        ("authority_admission", "implemented", "definition and admission ledgers expose metadata only"),
        ("effects", "partial", "receipt references are composable; claims require domain proof"),
        ("world_state", "implemented", "snapshot identity and shape metadata are bounded"),
        ("longitudinal_self_model", "implemented", "reconciliation identity and counts are bounded"),
        ("developmental_history", "implemented", "history custody identities and counts are bounded"),
        ("persistent_epistemics", "implemented", "state custody counts and mutation receipt references are bounded"),
        ("canonical_memory", "partial", "privacy-safe custody metadata only"),
        ("causal_resources", "partial", "explicit installation-scoped principal/allocation/attempt/receipt custody is observable; shared host use and cross-service attribution remain unavailable"),
        ("embodiment", "implemented", "renderer, independent observation, and fulfillment evidence remain distinct"),
        ("federation", "partial", "local lifecycle/candidate metadata carries no adoption authority"),
        ("runtime_supervision", "implemented", "service lifecycle and restart evidence is inspectable without control"),
    )
)
