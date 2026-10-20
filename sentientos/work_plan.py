from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping


WORK_PLAN_DIR = Path("glow/forge/work_plans")
WORK_PLAN_EVIDENCE_DIR = Path("glow/forge/work_plan_evidence")
WORK_PLAN_PULSE_PATH = Path("pulse/work_plans.jsonl")
WORK_RUN_DIR = Path("glow/forge/work_runs")
MAX_WORK_RUN_BYTES = 1_048_576
MAX_WORK_PLAN_EVIDENCE_INLINE_BINDING_BYTES = 262_144
MAX_EPISTEMIC_WORK_PLAN_EVIDENCE_BINDING_BYTES = 12_582_912
MAX_WORK_PLAN_EVIDENCE_FILE_BYTES = 524_288
MAX_EPISTEMIC_WORK_PLAN_EVIDENCE_BINDING_FILE_BYTES = 12_582_912
_PLAN_FIELDS = {"schema_version", "plan_id", "created_at", "context", "selected_goals", "tasks"}
_TASK_FIELDS = {"schema_version", "task_id", "goal_id", "kind", "commands", "callable_ref",
    "risk_cost", "throughput_cost", "preconditions", "expected_artifacts", "destructive",
    "depends_on"}
_LEGACY_TASK_FIELDS = _TASK_FIELDS - {"depends_on"}
_OMISSION_FIELDS = {"goal_id", "kind", "reason"}
_OMISSION_KINDS_BY_REASON = {
    "task_kind_not_implemented": {"fetch", "doc_update"},
    "risk_budget_exceeded": {"diagnostic", "verify", "forge_propose", "forge_apply"},
    "throughput_budget_exceeded": {"diagnostic", "verify", "forge_propose", "forge_apply"},
    "prior_terminal_outcome_requires_review": {"forge_apply"},
    "epistemic_position_requires_review": {"forge_apply"},
}


class WorkPlanError(ValueError):
    """A persisted plan is malformed or internally inconsistent."""


def work_plan_id_from_evidence(
    created_at: str, goal_graph_hash: str, allocation_id: str,
    evidence_binding: Mapping[str, object],
) -> str:
    """Derive the stable plan ID from its graph, allocation, and rationale."""
    if (not isinstance(created_at, str) or not isinstance(goal_graph_hash, str)
            or not isinstance(allocation_id, str) or not isinstance(evidence_binding, Mapping)):
        raise WorkPlanError("work_plan_evidence_shape_invalid")
    short_graph_hash = goal_graph_hash[:8]
    allocation_digest = hashlib.sha256(allocation_id.encode("utf-8")).hexdigest()[:6]
    evidence_digest = hashlib.sha256(json.dumps(
        evidence_binding, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")).hexdigest()[:10]
    return (f"{created_at.replace(':', '-').replace('.', '-')}_"
        f"{short_graph_hash}_{allocation_digest}_{evidence_digest}")


@dataclass(frozen=True, slots=True)
class TaskOmission:
    goal_id: str
    kind: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"goal_id": self.goal_id, "kind": self.kind, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class Task:
    schema_version: int
    task_id: str
    goal_id: str
    kind: str
    commands: tuple[str, ...]
    callable_ref: str | None
    risk_cost: int
    throughput_cost: int
    preconditions: dict[str, object]
    expected_artifacts: tuple[str, ...]
    destructive: bool
    depends_on: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["commands"] = list(self.commands)
        payload["expected_artifacts"] = list(self.expected_artifacts)
        payload["depends_on"] = list(self.depends_on)
        return payload


@dataclass(frozen=True, slots=True)
class WorkPlan:
    schema_version: int
    plan_id: str
    created_at: str
    context: str
    selected_goals: tuple[str, ...]
    tasks: tuple[Task, ...]
    omissions: tuple[TaskOmission, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "created_at": self.created_at,
            "context": self.context,
            "selected_goals": list(self.selected_goals),
            "tasks": [task.to_dict() for task in self.tasks],
            "omissions": [omission.to_dict() for omission in self.omissions],
        }

    def identity_digest(self) -> str:
        """Bind a completed run to every persisted plan field and task cost."""
        canonical = json.dumps(self.to_dict(), sort_keys=True,
            separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True, slots=True)
class TaskRun:
    task_id: str
    goal_id: str
    kind: str
    status: str
    reason: str | None
    started_at: str
    finished_at: str
    duration_ms: int
    artifacts: tuple[str, ...]
    destructive: bool

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["artifacts"] = list(self.artifacts)
        return payload


@dataclass(frozen=True, slots=True)
class WorkPlanRun:
    schema_version: int
    run_id: str
    plan_id: str
    created_at: str
    status: str
    operating_mode: str
    quarantine_active: bool
    task_runs: tuple[TaskRun, ...]
    reason_stack: tuple[str, ...]
    plan_digest: str = ""
    evidence_digest: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "plan_id": self.plan_id,
            "created_at": self.created_at,
            "status": self.status,
            "operating_mode": self.operating_mode,
            "quarantine_active": self.quarantine_active,
            "task_runs": [task.to_dict() for task in self.task_runs],
            "reason_stack": list(self.reason_stack),
            "plan_digest": self.plan_digest,
        }
        if self.schema_version == 3:
            payload["evidence_digest"] = self.evidence_digest
        return payload



def persist_work_plan(repo_root: Path, plan: WorkPlan) -> str:
    root = repo_root.resolve()
    plan_path = root / WORK_PLAN_DIR / f"plan_{_safe_id(plan.created_at)}.json"
    if _write_json_once(plan_path, plan.to_dict()):
        _append_jsonl(
            root / WORK_PLAN_PULSE_PATH,
            {
                "created_at": plan.created_at,
                "plan_id": plan.plan_id,
                "context": plan.context,
                "selected_goals": list(plan.selected_goals),
                "task_count": len(plan.tasks),
                "path": str(plan_path.relative_to(root)),
            },
        )
    return str(plan_path.relative_to(root))


def persist_work_plan_evidence(
    repo_root: Path, plan: WorkPlan, evidence_binding: Mapping[str, object],
) -> tuple[str, str]:
    """Persist the immutable evidence binding that gives a canonical plan its rationale."""
    if not isinstance(plan, WorkPlan) or not isinstance(evidence_binding, Mapping):
        raise WorkPlanError("work_plan_evidence_shape_invalid")
    try:
        canonical_binding = json.dumps(
            evidence_binding, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False,
        )
        binding_bytes = canonical_binding.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise WorkPlanError("work_plan_evidence_shape_invalid") from exc
    binding_is_external = len(binding_bytes) > MAX_WORK_PLAN_EVIDENCE_INLINE_BINDING_BYTES
    if binding_is_external and (
            len(binding_bytes) > MAX_EPISTEMIC_WORK_PLAN_EVIDENCE_BINDING_BYTES
            or not _has_epistemic_projection_identity(evidence_binding)):
        raise WorkPlanError("work_plan_evidence_bounds_invalid")
    graph_hash = evidence_binding.get("goal_graph_hash")
    allocation_id = evidence_binding.get("allocation_artifact_path")
    allocation_digest = evidence_binding.get("allocation_artifact_digest")
    if (not isinstance(graph_hash, str) or not isinstance(allocation_id, str)
            or not _optional_sha256_digest(allocation_digest)
            or work_plan_id_from_evidence(plan.created_at, graph_hash,
                allocation_id, evidence_binding) != plan.plan_id):
        raise WorkPlanError("work_plan_evidence_identity_mismatch")
    _verify_allocation_artifact_digest(repo_root, allocation_id, allocation_digest)
    basis: dict[str, object] = {
        "schema_version": 1,
        "plan_id": plan.plan_id,
        "plan_digest": plan.identity_digest(),
        "evidence_binding": json.loads(canonical_binding),
    }
    evidence_digest = hashlib.sha256(json.dumps(
        basis, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    root = repo_root.resolve()
    plan_key = hashlib.sha256(plan.plan_id.encode("utf-8")).hexdigest()
    path = root / WORK_PLAN_EVIDENCE_DIR / f"evidence_{plan_key}.json"
    if binding_is_external:
        sidecar_path = root / WORK_PLAN_EVIDENCE_DIR / f"binding_{plan_key}.json"
        _write_bytes_once(sidecar_path, binding_bytes)
        payload: dict[str, object] = {
            "schema_version": 2,
            "plan_id": plan.plan_id,
            "plan_digest": plan.identity_digest(),
            "evidence_binding_reference": {
                "schema_version": "sentientos.work_plan_evidence_binding_reference:v1",
                "sha256": hashlib.sha256(binding_bytes).hexdigest(),
                "byte_count": len(binding_bytes),
            },
            "evidence_digest": evidence_digest,
        }
    else:
        payload = {**basis, "evidence_digest": evidence_digest}
    _write_json_once(path, payload)
    return str(path.relative_to(root)), evidence_digest


def _has_epistemic_projection_identity(evidence_binding: Mapping[str, object]) -> bool:
    projection_digest = evidence_binding.get("projection_digest")
    review_scopes = evidence_binding.get("review_scopes")
    if not (
        isinstance(projection_digest, str)
        and len(projection_digest) == 71
        and projection_digest.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in projection_digest[7:])
        and isinstance(review_scopes, Mapping)
    ):
        return False
    manifest = evidence_binding.get("projection_omission_manifest")
    if manifest is None:
        return not any(
            isinstance(scope, Mapping)
            and scope.get("omitted_from_prior_projection") is True
            for scope in review_scopes.values()
        )
    if not isinstance(manifest, Mapping):
        return False
    rows = manifest.get("omitted_state_identities")
    selected_count = manifest.get("selected_state_count")
    available_count = manifest.get("available_prior_state_count")
    if (manifest.get("schema_version") !=
            "sentientos.epistemic_projection_omission_manifest:v1"
            or not isinstance(rows, (list, tuple))
            or type(manifest.get("omitted_state_count")) is not int
            or manifest.get("omitted_state_count") != len(rows)
            or type(selected_count) is not int
            or type(available_count) is not int
            or selected_count + len(rows) != available_count):
        return False
    digest = hashlib.sha256(json.dumps(
        rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    if manifest.get("omitted_identity_digest") != "sha256:" + digest:
        return False
    omitted_by_proposition: dict[str, Mapping[str, object]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            return False
        proposition_id = row.get("proposition_id")
        if not isinstance(proposition_id, str) or proposition_id in omitted_by_proposition:
            return False
        omitted_by_proposition[proposition_id] = row
    scoped_omissions: dict[str, Mapping[str, object]] = {}
    for proposition_id, scope in review_scopes.items():
        if isinstance(scope, Mapping) and scope.get("omitted_from_prior_projection") is True:
            if not isinstance(proposition_id, str):
                return False
            scoped_omissions[proposition_id] = scope
    if set(omitted_by_proposition) != set(scoped_omissions):
        return False
    return all(
        isinstance(proposition_id, str)
        and isinstance(scope, Mapping)
        and isinstance(scope.get("omitted_state_identity"), Mapping)
        and json.dumps(scope["omitted_state_identity"], sort_keys=True,
            separators=(",", ":"), ensure_ascii=False)
        == json.dumps(omitted_by_proposition[proposition_id], sort_keys=True,
            separators=(",", ":"), ensure_ascii=False)
        for proposition_id, scope in scoped_omissions.items()
    )


def _read_bounded_regular_file(path: Path, *, maximum: int, error_prefix: str) -> bytes:
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum:
            raise WorkPlanError(f"{error_prefix}_bounds_invalid")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            opened = os.fstat(descriptor)
            if (not stat.S_ISREG(opened.st_mode) or opened.st_dev != metadata.st_dev
                    or opened.st_ino != metadata.st_ino or opened.st_size > maximum):
                raise WorkPlanError(f"{error_prefix}_changed_during_open")
            raw = bytearray()
            while len(raw) <= maximum:
                chunk = os.read(descriptor, min(65_536, maximum + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
        finally:
            os.close(descriptor)
    except WorkPlanError:
        raise
    except (OSError, ValueError) as exc:
        raise WorkPlanError(f"{error_prefix}_unreadable") from exc
    if len(raw) > maximum:
        raise WorkPlanError(f"{error_prefix}_bounds_invalid")
    return bytes(raw)


def _write_bytes_once(path: Path, value: bytes) -> bool:
    """Publish one immutable evidence binding sidecar without following links."""
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        existing = _read_bounded_regular_file(
            path, maximum=MAX_EPISTEMIC_WORK_PLAN_EVIDENCE_BINDING_FILE_BYTES,
            error_prefix="work_plan_evidence_binding_sidecar")
        if existing != value:
            raise WorkPlanError("work_plan_evidence_binding_sidecar_identity_conflict")
        return False
    except OSError as exc:
        raise WorkPlanError("work_plan_evidence_binding_sidecar_write_failed") from exc
    try:
        remaining = memoryview(value)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("short_write")
            remaining = remaining[written:]
    except OSError as exc:
        raise WorkPlanError("work_plan_evidence_binding_sidecar_write_failed") from exc
    finally:
        os.close(descriptor)
    return True


def load_work_plan_evidence(repo_root: Path, plan: WorkPlan) -> dict[str, object]:
    """Read back and verify the immutable plan and rationale binding."""
    if not isinstance(plan, WorkPlan):
        raise WorkPlanError("work_plan_evidence_plan_invalid")
    plan_key = hashlib.sha256(plan.plan_id.encode("utf-8")).hexdigest()
    evidence_dir = repo_root.resolve() / WORK_PLAN_EVIDENCE_DIR
    path = evidence_dir / f"evidence_{plan_key}.json"
    raw = _read_bounded_regular_file(
        path, maximum=MAX_WORK_PLAN_EVIDENCE_FILE_BYTES,
        error_prefix="work_plan_evidence")
    try:
        stored_payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise WorkPlanError("work_plan_evidence_unreadable") from exc
    if (not isinstance(stored_payload, dict)
            or raw != (json.dumps(stored_payload, indent=2, sort_keys=True) + "\n").encode("utf-8")):
        raise WorkPlanError("work_plan_evidence_noncanonical")
    if isinstance(stored_payload, dict) and stored_payload.get("schema_version") == 2:
        reference = stored_payload.get("evidence_binding_reference")
        if (set(stored_payload) != {"schema_version", "plan_id", "plan_digest",
                "evidence_binding_reference", "evidence_digest"}
                or stored_payload.get("plan_id") != plan.plan_id
                or stored_payload.get("plan_digest") != plan.identity_digest()
                or not isinstance(reference, dict)
                or set(reference) != {"schema_version", "sha256", "byte_count"}
                or reference.get("schema_version") !=
                    "sentientos.work_plan_evidence_binding_reference:v1"
                or not isinstance(reference.get("sha256"), str)
                or type(reference.get("byte_count")) is not int
                or reference["byte_count"] < 1
                or reference["byte_count"] >
                    MAX_EPISTEMIC_WORK_PLAN_EVIDENCE_BINDING_FILE_BYTES):
            raise WorkPlanError("work_plan_evidence_binding_reference_invalid")
        sidecar_path = evidence_dir / f"binding_{plan_key}.json"
        sidecar = _read_bounded_regular_file(
            sidecar_path, maximum=MAX_EPISTEMIC_WORK_PLAN_EVIDENCE_BINDING_FILE_BYTES,
            error_prefix="work_plan_evidence_binding_sidecar")
        if (len(sidecar) != reference["byte_count"]
                or hashlib.sha256(sidecar).hexdigest() != reference["sha256"]):
            raise WorkPlanError("work_plan_evidence_binding_sidecar_digest_mismatch")
        try:
            evidence_binding = json.loads(sidecar.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise WorkPlanError("work_plan_evidence_binding_sidecar_unreadable") from exc
        if (not isinstance(evidence_binding, dict)
                or sidecar != json.dumps(evidence_binding, sort_keys=True,
                    separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                or len(sidecar) > MAX_EPISTEMIC_WORK_PLAN_EVIDENCE_BINDING_BYTES
                or not _has_epistemic_projection_identity(evidence_binding)):
            raise WorkPlanError("work_plan_evidence_binding_sidecar_noncanonical")
        payload: dict[str, object] = {
            "schema_version": 1,
            "plan_id": stored_payload.get("plan_id"),
            "plan_digest": stored_payload.get("plan_digest"),
            "evidence_binding": evidence_binding,
            "evidence_digest": stored_payload.get("evidence_digest"),
        }
    else:
        payload = stored_payload
    fields = {"schema_version", "plan_id", "plan_digest", "evidence_binding",
        "evidence_digest"}
    if (not isinstance(payload, dict) or set(payload) != fields
            or type(payload.get("schema_version")) is not int
            or payload["schema_version"] != 1
            or payload.get("plan_id") != plan.plan_id
            or payload.get("plan_digest") != plan.identity_digest()
            or not isinstance(payload.get("evidence_binding"), dict)
            or not isinstance(payload.get("evidence_digest"), str)):
        raise WorkPlanError("work_plan_evidence_identity_mismatch")
    evidence_binding = payload.get("evidence_binding")
    if not isinstance(evidence_binding, Mapping):
        raise WorkPlanError("work_plan_evidence_identity_mismatch")
    graph_hash = evidence_binding.get("goal_graph_hash")
    allocation_id = evidence_binding.get("allocation_artifact_path")
    if (not isinstance(graph_hash, str) or not isinstance(allocation_id, str)
            or not _optional_sha256_digest(
                evidence_binding.get("allocation_artifact_digest"))
            or work_plan_id_from_evidence(plan.created_at, graph_hash,
                allocation_id, evidence_binding) != plan.plan_id):
        raise WorkPlanError("work_plan_evidence_identity_mismatch")
    _verify_allocation_artifact_digest(repo_root, allocation_id,
        evidence_binding.get("allocation_artifact_digest"))
    basis = {key: payload[key] for key in fields if key != "evidence_digest"}
    expected_digest = hashlib.sha256(json.dumps(
        basis, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    if payload["evidence_digest"] != expected_digest:
        raise WorkPlanError("work_plan_evidence_digest_mismatch")
    return payload


def _optional_sha256_digest(value: object) -> bool:
    """Validate an optional digest while keeping pre-digest evidence readable."""
    return (value is None or (
        isinstance(value, str) and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])))


def _verify_allocation_artifact_digest(
        repo_root: Path, relative_path: str, digest: object) -> None:
    if digest is None:
        return
    root = repo_root.resolve()
    relative = Path(relative_path)
    if (relative.is_absolute() or any(part in {".", ".."} for part in relative.parts)):
        raise WorkPlanError("work_plan_allocation_artifact_digest_mismatch")
    path = root / relative
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise WorkPlanError("work_plan_allocation_artifact_digest_mismatch")
        raw = _read_bounded_regular_file(
            path, maximum=MAX_EPISTEMIC_WORK_PLAN_EVIDENCE_BINDING_FILE_BYTES,
            error_prefix="work_plan_allocation_artifact")
    except (OSError, ValueError) as exc:
        raise WorkPlanError("work_plan_allocation_artifact_digest_mismatch") from exc
    observed = "sha256:" + hashlib.sha256(raw).hexdigest()
    if observed != digest:
        raise WorkPlanError("work_plan_allocation_artifact_digest_mismatch")


def persist_work_run(repo_root: Path, run: WorkPlanRun) -> str:
    if (not isinstance(run, WorkPlanRun) or run.schema_version not in {2, 3}
            or not isinstance(run.plan_digest, str) or len(run.plan_digest) != 64
            or any(character not in "0123456789abcdef" for character in run.plan_digest)):
        raise WorkPlanError("work_run_plan_binding_required")
    if (run.schema_version == 2 and run.evidence_digest is not None
            or run.schema_version == 3 and not _valid_digest(run.evidence_digest)):
        raise WorkPlanError("work_run_evidence_binding_required")
    if run.run_id != f"run_{run.plan_digest}":
        raise WorkPlanError("work_run_identity_invalid")
    root = repo_root.resolve()
    run_path = root / WORK_RUN_DIR / f"{run.run_id}.json"
    if _write_json_once(run_path, run.to_dict()):
        _append_jsonl(
            root / "pulse/work_runs.jsonl",
            {
                "created_at": run.created_at,
                "run_id": run.run_id,
                "plan_id": run.plan_id,
                "status": run.status,
                "operating_mode": run.operating_mode,
                "quarantine_active": run.quarantine_active,
                "task_count": len(run.task_runs),
                "path": str(run_path.relative_to(root)),
            },
        )
    return str(run_path.relative_to(root))


def load_work_run(repo_root: Path, plan: WorkPlan, *, created_at: str) -> WorkPlanRun | None:
    """Load a prior run only when its exact plan and task identities validate."""
    if not isinstance(plan, WorkPlan) or not isinstance(created_at, str) or not created_at:
        raise WorkPlanError("work_run_lookup_identity_invalid")
    if created_at != plan.created_at:
        raise WorkPlanError("work_run_lookup_plan_time_mismatch")
    run_id = work_run_id(plan, created_at=created_at)
    path = repo_root.resolve() / WORK_RUN_DIR / f"{run_id}.json"
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        legacy_path = repo_root.resolve() / WORK_RUN_DIR / (
            f"run_{_safe_id(created_at)}_{plan.plan_id}.json")
        if legacy_path.exists():
            raise WorkPlanError("work_run_legacy_plan_binding_unavailable")
        return None
    except OSError as exc:
        raise WorkPlanError("work_run_artifact_unreadable") from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_WORK_RUN_BYTES:
        raise WorkPlanError("work_run_artifact_bounds_invalid")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            opened = os.fstat(descriptor)
            if (not stat.S_ISREG(opened.st_mode) or opened.st_ino != metadata.st_ino
                    or opened.st_dev != metadata.st_dev or opened.st_size > MAX_WORK_RUN_BYTES):
                raise WorkPlanError("work_run_artifact_changed_during_open")
            chunks: list[bytes] = []
            remaining = MAX_WORK_RUN_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
        finally:
            os.close(descriptor)
        if len(raw) > MAX_WORK_RUN_BYTES:
            raise WorkPlanError("work_run_artifact_bounds_invalid")
        payload = json.loads(raw.decode("utf-8"))
    except WorkPlanError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkPlanError("work_run_artifact_unreadable") from exc
    if isinstance(payload, dict) and payload.get("plan_digest") != plan.identity_digest():
        raise WorkPlanError("work_run_plan_identity_mismatch")
    version = payload.get("schema_version") if isinstance(payload, dict) else None
    fields_v2 = {
            "schema_version", "run_id", "plan_id", "created_at", "status",
            "operating_mode", "quarantine_active", "task_runs", "reason_stack",
            "plan_digest"}
    fields_v3 = fields_v2 | {"evidence_digest"}
    if (not isinstance(payload, dict)
            or type(version) is not int or version not in {2, 3}
            or set(payload) != (fields_v2 if version == 2 else fields_v3)
            or (version == 2 and payload.get("evidence_digest") is not None)
            or (version == 3 and not _valid_digest(payload.get("evidence_digest")))
            or payload.get("run_id") != run_id or payload.get("plan_id") != plan.plan_id
            or payload.get("created_at") != created_at
            or not isinstance(payload.get("operating_mode"), str)
            or not payload["operating_mode"]
            or type(payload.get("quarantine_active")) is not bool
            or not isinstance(payload.get("task_runs"), list)
            or len(payload["task_runs"]) != len(plan.tasks)
            or not isinstance(payload.get("reason_stack"), list)
            or len(payload["reason_stack"]) > 12
            or any(not isinstance(item, str) for item in payload["reason_stack"])):
        raise WorkPlanError("work_run_artifact_shape_invalid")
    if version == 3:
        evidence = load_work_plan_evidence(repo_root, plan)
        if evidence.get("evidence_digest") != payload.get("evidence_digest"):
            raise WorkPlanError("work_run_evidence_binding_mismatch")
    expected_task_fields = {"task_id", "goal_id", "kind", "status", "reason",
        "started_at", "finished_at", "duration_ms", "artifacts", "destructive"}
    task_runs: list[TaskRun] = []
    for task, row in zip(plan.tasks, payload["task_runs"], strict=True):
        if (not isinstance(row, dict) or set(row) != expected_task_fields
                or row.get("task_id") != task.task_id or row.get("goal_id") != task.goal_id
                or row.get("kind") != task.kind
                or row.get("status") not in {"success", "failed", "skipped", "partial"}
                or (row.get("reason") is not None and not isinstance(row["reason"], str))
                or (row.get("status") == "partial"
                    and (not isinstance(row.get("reason"), str) or not row["reason"]))
                or not isinstance(row.get("started_at"), str) or not row["started_at"]
                or not isinstance(row.get("finished_at"), str) or not row["finished_at"]
                or type(row.get("duration_ms")) is not int or row["duration_ms"] < 0
                or not isinstance(row.get("artifacts"), list)
                or any(not isinstance(item, str) or len(item) > 1024 for item in row["artifacts"])
                or type(row.get("destructive")) is not bool
                or row["destructive"] != (task.destructive or task.kind == "forge_apply")):
            raise WorkPlanError("work_run_task_identity_invalid")
        task_runs.append(TaskRun(task.task_id, task.goal_id, task.kind, row["status"],
            row["reason"], row["started_at"], row["finished_at"], row["duration_ms"],
            tuple(row["artifacts"]), row["destructive"]))
    expected_reasons = [row.reason for row in task_runs
        if row.status in {"failed", "skipped", "partial"} and row.reason][:12]
    if payload["reason_stack"] != expected_reasons:
        raise WorkPlanError("work_run_reason_stack_invalid")
    if not task_runs or all(row.status == "skipped" for row in task_runs):
        expected_status = "skipped"
    elif any(row.status == "failed" for row in task_runs):
        expected_status = "failed"
    elif any(row.status in {"skipped", "partial"} for row in task_runs):
        expected_status = "partial"
    else:
        expected_status = "ok"
    if payload.get("status") != expected_status:
        raise WorkPlanError("work_run_status_mismatch")
    canonical = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if raw != canonical:
        raise WorkPlanError("work_run_artifact_noncanonical")
    return WorkPlanRun(version, run_id, plan.plan_id, created_at, expected_status,
        payload["operating_mode"], payload["quarantine_active"], tuple(task_runs),
        tuple(payload["reason_stack"]), payload["plan_digest"],
        payload.get("evidence_digest"))


def _valid_digest(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
        and all(character in "0123456789abcdef" for character in value))


def work_run_id(plan: WorkPlan, *, created_at: str) -> str:
    """Give each exact plan a distinct immutable run artifact identity."""
    if (not isinstance(plan, WorkPlan) or created_at != plan.created_at):
        raise WorkPlanError("work_run_lookup_plan_time_mismatch")
    return f"run_{plan.identity_digest()}"


def _write_json_once(path: Path, value: dict[str, object]) -> bool:
    """Write an immutable artifact, allowing only an exact idempotent replay."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        with path.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
    except FileExistsError:
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise WorkPlanError("work_plan_artifact_unreadable") from exc
        if existing != encoded:
            raise WorkPlanError("work_plan_artifact_identity_conflict")
        return False
    except OSError as exc:
        raise WorkPlanError("work_plan_artifact_write_failed") from exc
    return True


def load_work_plan(path: Path) -> WorkPlan:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkPlanError("work_plan_unreadable") from exc
    if (not isinstance(payload, dict) or set(payload) not in (_PLAN_FIELDS, _PLAN_FIELDS | {"omissions"})
            or type(payload.get("schema_version")) is not int or payload["schema_version"] != 1
            or any(not isinstance(payload.get(key), str) or not payload[key] or len(payload[key]) > 512
                for key in ("plan_id", "created_at", "context"))
            or not isinstance(payload.get("selected_goals"), list)
            or any(not isinstance(item, str) or not item or len(item) > 256
                for item in payload["selected_goals"])
            or len(payload["selected_goals"]) != len(set(payload["selected_goals"]))
            or not isinstance(payload.get("tasks"), list)):
        raise WorkPlanError("work_plan_shape_invalid")
    tasks = []
    task_ids: set[str] = set()
    goals = set(payload["selected_goals"])
    for row in payload["tasks"]:
        if (not isinstance(row, dict) or set(row) not in (_TASK_FIELDS, _LEGACY_TASK_FIELDS)
                or type(row.get("schema_version")) is not int or row["schema_version"] != 1
                or any(not isinstance(row.get(key), str) or not row[key] or len(row[key]) > 256
                    for key in ("task_id", "goal_id", "kind"))
                or row["goal_id"] not in goals or row["task_id"] in task_ids
                or not isinstance(row.get("commands"), list)
                or any(not isinstance(item, str) or len(item) > 4096 for item in row["commands"])
                or (row.get("callable_ref") is not None and not isinstance(row["callable_ref"], str))
                or any(type(row.get(key)) is not int or row[key] < 0
                    for key in ("risk_cost", "throughput_cost"))
                or not isinstance(row.get("preconditions"), dict)
                or ("requires_mutation" in row["preconditions"]
                    and type(row["preconditions"]["requires_mutation"]) is not bool)
                or not isinstance(row.get("expected_artifacts"), list)
                or any(not isinstance(item, str) or len(item) > 1024 for item in row["expected_artifacts"])
                or type(row.get("destructive")) is not bool):
            raise WorkPlanError("work_plan_task_invalid")
        depends_on = row.get("depends_on", [])
        if (not isinstance(depends_on, list)
                or any(not isinstance(item, str) or not item or len(item) > 256
                    for item in depends_on)
                or len(depends_on) != len(set(depends_on))):
            raise WorkPlanError("work_plan_task_dependencies_invalid")
        inferred_destructive = (row["kind"] == "forge_apply"
            or row["preconditions"].get("requires_mutation") is True)
        if row["destructive"] != inferred_destructive:
            raise WorkPlanError("work_plan_destructive_classification_mismatch")
        task_ids.add(row["task_id"])
        tasks.append(Task(schema_version=row["schema_version"], task_id=row["task_id"],
            goal_id=row["goal_id"], kind=row["kind"], commands=tuple(row["commands"]),
            callable_ref=row["callable_ref"], risk_cost=row["risk_cost"],
            throughput_cost=row["throughput_cost"], preconditions=dict(row["preconditions"]),
            expected_artifacts=tuple(row["expected_artifacts"]), destructive=row["destructive"],
            depends_on=tuple(depends_on)))
    task_positions = {task.task_id: index for index, task in enumerate(tasks)}
    for index, task in enumerate(tasks):
        if any(dependency not in task_positions or task_positions[dependency] >= index
                for dependency in task.depends_on):
            raise WorkPlanError("work_plan_task_dependencies_invalid")
    omissions_raw = payload.get("omissions", [])
    if not isinstance(omissions_raw, list) or len(omissions_raw) > 256:
        raise WorkPlanError("work_plan_omissions_invalid")
    omissions: list[TaskOmission] = []
    omission_ids: set[tuple[str, str]] = set()
    for row in omissions_raw:
        if (not isinstance(row, dict) or set(row) != _OMISSION_FIELDS
                or not isinstance(row.get("goal_id"), str) or row["goal_id"] not in goals
                or not isinstance(row.get("kind"), str)
                or not isinstance(row.get("reason"), str)
                or row["kind"] not in _OMISSION_KINDS_BY_REASON.get(row["reason"], set())
                or (row["goal_id"], row["kind"]) in omission_ids):
            raise WorkPlanError("work_plan_omissions_invalid")
        omission_ids.add((row["goal_id"], row["kind"]))
        omissions.append(TaskOmission(row["goal_id"], row["kind"], row["reason"]))
    return WorkPlan(
        schema_version=payload["schema_version"],
        plan_id=payload["plan_id"],
        created_at=payload["created_at"],
        context=payload["context"],
        selected_goals=tuple(payload["selected_goals"]),
        tasks=tuple(tasks),
        omissions=tuple(omissions),
    )


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _safe_id(value: str) -> str:
    return value.replace(":", "-").replace(".", "-")


__all__ = [
    "Task",
    "TaskOmission",
    "TaskRun",
    "WorkPlan",
    "WorkPlanRun",
    "WorkPlanError",
    "load_work_plan",
    "load_work_run",
    "work_run_id",
    "work_plan_id_from_evidence",
    "load_work_plan_evidence",
    "persist_work_plan",
    "persist_work_plan_evidence",
    "persist_work_run",
]
