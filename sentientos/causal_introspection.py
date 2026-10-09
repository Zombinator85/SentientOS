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
import stat
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence, cast

SCHEMA_VERSION = "sentientos.causal_introspection:v1"
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
    config_path = Path(selected)
    try:
        metadata = config_path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_CONFIG_BYTES:
            raise IntrospectionError("configuration_file_unbounded_or_not_regular")
        descriptor = os.open(config_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
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
    if projection.domain not in DOMAINS:
        raise IntrospectionError("unregistered_domain")
    if projection.posture != ProjectionPosture():
        raise IntrospectionError("projection_authority_widened")
    if len(projection.observations) > MAX_OBSERVATIONS or len(projection.findings) > MAX_FINDINGS:
        raise IntrospectionError("projection_bounds_exceeded")
    references = projection.source_references + projection.causal_references
    if len(references) > MAX_REFERENCES:
        raise IntrospectionError("reference_bounds_exceeded")
    reference_ids = {reference.reference_id for reference in references}
    for reference in references:
        if reference.reference_kind not in REFERENCE_KINDS or not reference.reference_id or not reference.source_owner_id:
            raise IntrospectionError("invalid_causal_reference")
    for observation in projection.observations:
        key = observation.observation_key.lower()
        if (not key or observation.observation_class not in OBSERVATION_CLASSES
                or observation.production_posture not in PRODUCTION_POSTURES):
            raise IntrospectionError("invalid_observation")
        if any(token in key for token in SECRET_TOKENS) or any(any(token in nested for token in SECRET_TOKENS) for nested in _walk_keys(observation.bounded_value)):
            raise IntrospectionError("credential_material_rejected")
        if key in FORBIDDEN_KEYS:
            raise IntrospectionError("semantic_collapse_rejected")
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


def validate_snapshot(snapshot: CausalIntrospectionSnapshot, predecessor: CausalIntrospectionSnapshot | None = None) -> None:
    if snapshot.authority or snapshot.current_truth or snapshot.generation < 1:
        raise IntrospectionError("invalid_snapshot_posture")
    if tuple(item.projection_id for item in snapshot.projections) != snapshot.projection_ids:
        raise IntrospectionError("projection_inventory_mismatch")
    if tuple(item.projection_digest for item in snapshot.projections) != snapshot.projection_digests:
        raise IntrospectionError("projection_digest_inventory_mismatch")
    for projection in snapshot.projections:
        validate_projection(projection)
    if predecessor is None:
        if snapshot.generation != 1 or snapshot.predecessor_snapshot_digest is not None:
            raise IntrospectionError("invalid_genesis_snapshot")
    elif (snapshot.generation != predecessor.generation + 1
            or snapshot.predecessor_snapshot_digest != predecessor.snapshot_digest):
        raise IntrospectionError("predecessor_mismatch")
    expected = _digest(_snapshot_payload(snapshot))
    if snapshot.snapshot_digest != expected or snapshot.snapshot_id != f"causal-introspection-{expected[:20]}":
        raise IntrospectionError("snapshot_digest_mismatch")
    if len(_canonical(_plain(snapshot))) > MAX_SNAPSHOT_BYTES:
        raise IntrospectionError("snapshot_bytes_exceeded")


class CausalIntrospectionRuntime:
    def __init__(self, config: IntrospectionConfig, registrations: Sequence[ProviderRegistration]):
        self.config = config
        self.registrations = tuple(sorted(registrations, key=lambda item: (item.domain, item.owner_id)))
        if len(self.registrations) > config.max_projections:
            raise IntrospectionError("provider_count_exceeded")
        if any(isinstance(item.provider, CausalIntrospectionRuntime) or item.owner_id == "causal_introspection_runtime" for item in self.registrations):
            raise IntrospectionError("recursive_fabric_provider_rejected")
        owners = [item.owner_id for item in self.registrations]
        providers = [item.provider.provider_id for item in self.registrations]
        if len(set(owners)) != len(owners) or len(set(providers)) != len(providers):
            raise IntrospectionError("duplicate_provider_registration")
        if any(item.domain not in config.enabled_domains or item.domain not in DOMAINS for item in self.registrations):
            raise IntrospectionError("provider_domain_not_enabled")

    def _paths(self) -> list[Path]:
        try:
            root_mode = self.config.custody_root.lstat().st_mode
        except FileNotFoundError:
            return []
        if not stat.S_ISDIR(root_mode):
            raise IntrospectionError("custody_root_invalid")
        paths = sorted(self.config.custody_root.glob("generation-*.json"))
        if len(paths) > MAX_SNAPSHOT_GENERATIONS:
            raise IntrospectionError("snapshot_generation_limit_exceeded")
        return paths

    @staticmethod
    def _read_snapshot(path: Path) -> bytes:
        try:
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_SNAPSHOT_BYTES:
                raise IntrospectionError("snapshot_file_unbounded_or_not_regular")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags)
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
    def _publish_snapshot(path: Path, data: bytes) -> None:
        descriptor, temporary = tempfile.mkstemp(prefix=".causal-introspection-", suffix=".tmp",
            dir=str(path.parent))
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temporary, path, follow_symlinks=False)
            directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def reconstruct(self) -> tuple[CausalIntrospectionSnapshot, ...]:
        snapshots: list[CausalIntrospectionSnapshot] = []
        paths = self._paths()
        total_bytes = 0
        for expected_generation, path in enumerate(paths, 1):
            if path.name != f"generation-{expected_generation:020d}.json":
                raise IntrospectionError("missing_or_ambiguous_generation")
            data = self._read_snapshot(path)
            total_bytes += len(data)
            if total_bytes > MAX_SNAPSHOT_CUSTODY_BYTES:
                raise IntrospectionError("snapshot_custody_limit_exceeded")
            snapshot = _decode_snapshot(json.loads(data.decode("utf-8")))
            validate_snapshot(snapshot, snapshots[-1] if snapshots else None)
            snapshots.append(snapshot)
        return tuple(snapshots)

    def capture(self, context: CaptureContext) -> CausalIntrospectionSnapshot:
        if not self.config.enabled:
            raise IntrospectionError("introspection_disabled")
        history = self.reconstruct()
        prior = history[-1] if history else None
        projections: list[OwnerIntrospectionProjection] = []
        findings: list[CaptureFinding] = []
        for registration in self.registrations:
            try:
                projection = registration.provider.project(context)
                if projection.owner_id != registration.owner_id or projection.domain != registration.domain:
                    raise IntrospectionError("provider_registration_mismatch")
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
        provisional = CausalIntrospectionSnapshot("", "", (prior.generation + 1 if prior else 1),
            prior.snapshot_digest if prior else None, context.tick_id, context.repository_revision,
            context.repository_tree, tuple(item.projection_id for item in projections),
            tuple(item.projection_digest for item in projections), tuple(projections), tuple(findings),
            conflicts, "partial" if findings else "complete")
        digest = _digest(_snapshot_payload(provisional))
        snapshot = replace(provisional, snapshot_id=f"causal-introspection-{digest[:20]}", snapshot_digest=digest)
        validate_snapshot(snapshot, prior)
        self.config.custody_root.mkdir(parents=True, exist_ok=True)
        target = self.config.custody_root / f"generation-{snapshot.generation:020d}.json"
        data = _canonical(_plain(snapshot))
        try:
            self._publish_snapshot(target, data)
        except FileExistsError:
            existing = self._read_snapshot(target)
            if existing != data:
                raise IntrospectionError("same_generation_content_conflict")
            return _decode_snapshot(json.loads(existing))
        return snapshot

    @staticmethod
    def _conflicts(projections: Sequence[OwnerIntrospectionProjection]) -> tuple[ProjectionConflict, ...]:
        groups: dict[str, dict[str, list[str]]] = {}
        for projection in projections:
            for observation in projection.observations:
                encoded = _canonical(observation.bounded_value).decode("ascii")
                groups.setdefault(observation.observation_key, {}).setdefault(encoded, []).append(projection.projection_id)
        return tuple(ProjectionConflict(key, tuple(sorted(pid for ids in values.values() for pid in ids)))
            for key, values in sorted(groups.items()) if len(values) > 1)

    def prior_snapshot(self, *, before_generation: int) -> CausalIntrospectionSnapshot | None:
        eligible = [item for item in self.reconstruct() if item.generation < before_generation]
        return eligible[-1] if eligible else None

    def world_state_records(self, *, before_generation: int) -> list[dict[str, Any]]:
        if not self.config.world_state_consumption_enabled:
            return []
        snapshot = self.prior_snapshot(before_generation=before_generation)
        if snapshot is None:
            return []
        records: list[dict[str, Any]] = []
        for projection in snapshot.projections:
            records.append({
                "source_kind": "owner_introspection", "source_id": projection.projection_id,
                "schema_version": projection.schema_version, "subject_id": projection.owner_id,
                "subject_kind": projection.domain, "stage": "observation",
                "disposition": "owner_reported", "evidence_strength": "owner_self_observation",
                "payload": {"projection_id": projection.projection_id,
                    "projection_digest": projection.projection_digest,
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
        ("causal_resources", "partial", "principal attribution exists; allocation is not inferred"),
        ("embodiment", "implemented", "renderer, independent observation, and fulfillment evidence remain distinct"),
        ("federation", "partial", "local lifecycle/candidate metadata carries no adoption authority"),
        ("runtime_supervision", "implemented", "service lifecycle and restart evidence is inspectable without control"),
    )
)
