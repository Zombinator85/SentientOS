"""Governed avatar-body authoring, succession, adoption, and rollback.

Plans are data, never executable code.  Authoring and inspection are separate
roles, and neither role can adopt a body generation.
"""
from __future__ import annotations

import hashlib
import fcntl
import json
import os
import shutil
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Protocol, Sequence, cast

from .bounded_subprocess import run_supervised
from .embodiment_self_observation import AvatarBodyManifest, EmbodimentObservation

PLAN_SCHEMA = "sentientos.avatar_authoring_plan:v1"
POINTER_SCHEMA = "sentientos.current_avatar_body:v1"
ADMISSION_SCHEMA = "sentientos.avatar_authoring_admission:v1"
INSPECTION_SCHEMA = "sentientos.avatar_artifact_inspection:v1"
COMPARISON_SCHEMA = "sentientos.avatar_authoring_comparison:v1"
RECEIPT_SCHEMA = "sentientos.avatar_authoring_receipt:v1"
ADOPTION_SCHEMA = "sentientos.avatar_body_adoption_receipt:v1"
ROLLBACK_SCHEMA = "sentientos.avatar_body_rollback_receipt:v1"
HANDOFF_SCHEMA = "sentientos.avatar_renderer_handoff:v1"
LINEAGE_SCHEMA = "sentientos.avatar_body_lineage_event:v1"
SUPPORTED_FORMATS = frozenset({"blend", "glb", "gltf"})
MAX_OPERATIONS = 64
MAX_ARTIFACT_BYTES = 256 * 1024 * 1024
MAX_INVENTORY = 128
FALSE_AUTHORITY = {"decision_authority": False, "admission_authority": False,
                   "execution_authority": False, "adoption_authority": False,
                   "renderer_authority": False, "observation_authority": False}
OP_ARGUMENTS: dict[str, frozenset[str]] = {
    "create_primitive_mesh": frozenset({"primitive", "vertices"}),
    "duplicate_object": frozenset({"source"}), "rename_object": frozenset({"new_name"}),
    "set_transform": frozenset({"location", "rotation", "scale", "tolerance"}),
    "assign_material": frozenset({"material"}), "create_armature": frozenset(),
    "create_bone": frozenset({"parent", "head", "tail"}),
    "parent_object": frozenset({"armature", "bone"}),
    "bind_armature": frozenset({"armature"}),
    "create_shape_key": frozenset({"shape_key"}),
    "register_channel": frozenset({"channel", "channel_kind", "control"}),
    "set_label": frozenset({"label", "value"}),
}


class AvatarAuthoringError(ValueError):
    """Fail-closed workcell contract violation."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_identity(path: Path, *, maximum: int = MAX_ARTIFACT_BYTES) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise AvatarAuthoringError("artifact_not_regular")
    size = path.stat().st_size
    if not 0 < size <= maximum:
        raise AvatarAuthoringError("artifact_size_invalid")
    return {"path": str(path.resolve()), "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
            "byte_size": size}


def _name(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 128 or any(c in value for c in ("/", "\\", "\x00")):
        raise AvatarAuthoringError("plan_name_invalid")
    if value.startswith("http:") or value.startswith("https:") or value in {".", ".."}:
        raise AvatarAuthoringError("plan_name_invalid")
    return value


def _vector(value: Any) -> list[float]:
    if not isinstance(value, list) or len(value) != 3 or any(type(x) not in (int, float) or abs(x) > 10000 for x in value):
        raise AvatarAuthoringError("plan_vector_invalid")
    return [float(x) for x in value]


def validate_plan(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {"schema_version", "plan_id", "installation_body_id", "body_id", "predecessor_generation",
                "predecessor_artifact_digest", "predecessor_manifest_digest", "operations", "proposed_by"}
    if set(value) != required or value.get("schema_version") != PLAN_SCHEMA:
        raise AvatarAuthoringError("authoring_plan_shape_invalid")
    for key in ("plan_id", "installation_body_id", "body_id", "proposed_by"):
        _name(value[key])
    if type(value["predecessor_generation"]) is not int or value["predecessor_generation"] < 1:
        raise AvatarAuthoringError("authoring_plan_generation_invalid")
    operations = value["operations"]
    if not isinstance(operations, list) or not operations or len(operations) > MAX_OPERATIONS:
        raise AvatarAuthoringError("authoring_plan_operation_count_invalid")
    seen: set[str] = set()
    for operation in operations:
        if not isinstance(operation, dict) or set(operation) != {"operation_id", "kind", "target", "arguments", "preconditions", "postcondition"}:
            raise AvatarAuthoringError("authoring_operation_shape_invalid")
        op_id = _name(operation["operation_id"]); kind = operation["kind"]
        if op_id in seen: raise AvatarAuthoringError("authoring_operation_id_duplicate")
        seen.add(op_id)
        if kind not in OP_ARGUMENTS: raise AvatarAuthoringError("authoring_operation_unknown")
        _name(operation["target"])
        args = operation["arguments"]
        if not isinstance(args, dict) or set(args) - OP_ARGUMENTS[kind]:
            raise AvatarAuthoringError("authoring_operation_arguments_invalid")
        if any(key.lower() in {"python", "script", "shell", "command", "addon", "url", "path"} for key in args):
            raise AvatarAuthoringError("authoring_operation_code_or_path_forbidden")
        for key, item in args.items():
            if key in {"location", "rotation", "scale", "head", "tail"}: _vector(item)
            elif key == "vertices" and (type(item) is not int or not 3 <= item <= 10000):
                raise AvatarAuthoringError("geometry_bound_exceeded")
            elif key == "tolerance" and (type(item) not in (int, float) or not 0 <= item <= 0.1):
                raise AvatarAuthoringError("tolerance_invalid")
            elif item is not None and isinstance(item, str):
                if key == "control":
                    parts = item.split("/")
                    if len(parts) > 2 or any(not part for part in parts): raise AvatarAuthoringError("plan_control_invalid")
                    for part in parts: _name(part)
                else: _name(item)
        for field in ("preconditions", "postcondition"):
            if not isinstance(operation[field], dict) or len(operation[field]) > 16:
                raise AvatarAuthoringError("authoring_operation_condition_invalid")
            canonical_bytes(operation[field])
    result = cast(dict[str, Any], json.loads(canonical_bytes(value))); result["plan_digest"] = digest(result)
    return result


@dataclass(frozen=True)
class BackendIdentity:
    backend_class: str
    implementation: str
    version: str
    executable_path: str | None
    executable_sha256: str | None
    driver_sha256: str
    capabilities: tuple[str, ...]
    evidence_posture: str

    @property
    def semantic_digest(self) -> str: return digest(asdict(self))


class AuthoringBackend(Protocol):
    @property
    def identity(self) -> BackendIdentity: ...
    def author(self, predecessor: Path, plan: Mapping[str, Any], successor: Path) -> Mapping[str, Any]: ...


class ArtifactInspector(Protocol):
    @property
    def identity(self) -> BackendIdentity: ...
    def inspect(self, artifact: Path, asset_format: str) -> Mapping[str, Any]: ...


def _fixture_structure(path: Path) -> dict[str, Any]:
    try: value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise AvatarAuthoringError("artifact_malformed") from exc
    required = {"fixture_schema", "asset_format", "body_id", "labels", "objects", "armatures", "materials", "shape_keys", "channels"}
    if not isinstance(value, dict) or set(value) != required or value["fixture_schema"] != "sentientos.synthetic_avatar_artifact:v1":
        raise AvatarAuthoringError("artifact_malformed")
    if value["asset_format"] not in SUPPORTED_FORMATS: raise AvatarAuthoringError("artifact_format_unsupported")
    for key in ("objects", "armatures", "materials", "shape_keys", "channels"):
        if not isinstance(value[key], dict) or len(value[key]) > MAX_INVENTORY: raise AvatarAuthoringError("artifact_inventory_invalid")
    return value


def _apply_operation(model: dict[str, Any], operation: Mapping[str, Any]) -> None:
    kind, target, args = operation["kind"], operation["target"], operation["arguments"]
    objects, rigs = model["objects"], model["armatures"]
    if kind == "create_primitive_mesh": objects[target] = {"type": "MESH", "primitive": args.get("primitive", "cube"), "vertices": args.get("vertices", 8), "transform": {"location": [0.,0.,0.], "rotation": [0.,0.,0.], "scale": [1.,1.,1.]}, "materials": [], "parent": None, "armature": None}
    elif kind == "duplicate_object": objects[target] = json.loads(canonical_bytes(objects[args["source"]]))
    elif kind == "rename_object": objects[args["new_name"]] = objects.pop(target)
    elif kind == "set_transform": objects[target]["transform"] = {k: args.get(k, objects[target]["transform"][k]) for k in ("location","rotation","scale")}
    elif kind == "assign_material":
        model["materials"].setdefault(args["material"], {}); objects[target]["materials"].append(args["material"])
    elif kind == "create_armature": rigs[target] = {"bones": {}}
    elif kind == "create_bone": rigs.setdefault(target, {"bones": {}})["bones"][operation["postcondition"].get("bone", args.get("bone", operation["operation_id"]))] = {"parent": args.get("parent"), "head": args.get("head", [0.,0.,0.]), "tail": args.get("tail", [0.,1.,0.])}
    elif kind == "parent_object": objects[target]["parent"] = {"armature": args["armature"], "bone": args.get("bone")}
    elif kind == "bind_armature": objects[target]["armature"] = args["armature"]
    elif kind == "create_shape_key": model["shape_keys"].setdefault(target, []).append(args["shape_key"])
    elif kind == "register_channel": model["channels"][args["channel"]] = {"kind": args["channel_kind"], "control": args["control"]}
    elif kind == "set_label": model["labels"][args["label"]] = args["value"]


class SyntheticAuthoringBackend:
    """Deterministic fixture transformer; never represents Blender evidence."""
    identity = BackendIdentity("synthetic_fixture_author", "sentientos.avatar_authoring", "1", None, None,
                               digest("synthetic-static-transformer-v1"), tuple(OP_ARGUMENTS), "synthetic_test")
    def author(self, predecessor: Path, plan: Mapping[str, Any], successor: Path) -> Mapping[str, Any]:
        model = _fixture_structure(predecessor); results = []
        for operation in plan["operations"]:
            try: _apply_operation(model, operation); results.append({"operation_id": operation["operation_id"], "status": "applied"})
            except (KeyError, TypeError, AvatarAuthoringError) as exc:
                results.append({"operation_id": operation["operation_id"], "status": "failed", "reason": str(exc)}); break
        successor.write_bytes(canonical_bytes(model) + b"\n")
        return {"status": "completed" if all(r["status"] == "applied" for r in results) else "failed",
                "operations": results, "argv": [], "authority": dict(FALSE_AUTHORITY)}


class SyntheticArtifactInspector:
    identity = BackendIdentity("synthetic_fixture_inspector", "sentientos.avatar_authoring", "1", None, None,
                               digest("synthetic-independent-parser-v1"), ("inspect",), "synthetic_test")
    def inspect(self, artifact: Path, asset_format: str) -> Mapping[str, Any]:
        identity = file_identity(artifact); model = _fixture_structure(artifact)
        if model["asset_format"] != asset_format: raise AvatarAuthoringError("artifact_claimed_format_mismatch")
        bones = {f"{rig}/{bone}": data for rig, rd in sorted(model["armatures"].items()) for bone, data in sorted(rd["bones"].items())}
        value = {"schema_version": INSPECTION_SCHEMA, "artifact_sha256": identity["sha256"], "byte_size": identity["byte_size"],
                 "format": asset_format, "body_id": model["body_id"], "labels": model["labels"], "objects": model["objects"],
                 "armatures": model["armatures"], "bones": bones, "materials": model["materials"], "shape_keys": model["shape_keys"],
                 "channels": model["channels"], "warnings": [], "unsupported": [], "inspector_identity": asdict(self.identity)}
        value["inspection_digest"] = digest(value); return value


def compare_structure(before: Mapping[str, Any], plan: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    results = []
    for op in plan["operations"]:
        kind, target, args = op["kind"], op["target"], op["arguments"]
        satisfied = False
        if kind == "create_primitive_mesh": satisfied = target in after["objects"] and after["objects"][target]["type"] == "MESH"
        elif kind == "duplicate_object": satisfied = target in after["objects"]
        elif kind == "rename_object": satisfied = args["new_name"] in after["objects"] and target not in after["objects"]
        elif kind == "set_transform": satisfied = target in after["objects"] and all(after["objects"][target]["transform"].get(k) == v for k,v in args.items() if k in {"location","rotation","scale"})
        elif kind == "assign_material": satisfied = args["material"] in after["objects"].get(target, {}).get("materials", [])
        elif kind == "create_armature": satisfied = target in after["armatures"]
        elif kind == "create_bone": satisfied = f"{target}/{op['postcondition'].get('bone', op['operation_id'])}" in after["bones"]
        elif kind == "parent_object": satisfied = after["objects"].get(target, {}).get("parent") == {"armature": args["armature"], "bone": args.get("bone")}
        elif kind == "bind_armature": satisfied = after["objects"].get(target, {}).get("armature") == args["armature"]
        elif kind == "create_shape_key": satisfied = args["shape_key"] in after["shape_keys"].get(target, [])
        elif kind == "register_channel": satisfied = after["channels"].get(args["channel"]) == {"kind": args["channel_kind"], "control": args["control"]}
        elif kind == "set_label": satisfied = after["labels"].get(args["label"]) == args["value"]
        results.append({"operation_id": op["operation_id"], "classification": "satisfied" if satisfied else "unsatisfied"})
    requested_new = {op["target"] for op in plan["operations"] if op["kind"] in {"create_primitive_mesh","duplicate_object","create_armature"}}
    unexpected = sorted((set(after["objects"]) - set(before["objects"]) | set(after["armatures"]) - set(before["armatures"])) - requested_new)
    counts = {name: sum(r["classification"] == name for r in results) for name in ("satisfied","unsatisfied","contradicted","not_measurable")}
    value = {"schema_version": COMPARISON_SCHEMA, "predecessor_inspection_digest": before["inspection_digest"], "plan_digest": plan["plan_digest"], "successor_inspection_digest": after["inspection_digest"], "operation_results": results, "unexpected_changes": unexpected, "counts": counts}
    value["comparison_digest"] = digest(value); return value


class BlenderBackend:
    """Exactly configured Blender subprocess backend using static drivers."""
    def __init__(self, executable: Path, driver: Path, *, expected_sha256: str | None = None, timeout_seconds: float = 300) -> None:
        self.executable, self.driver, self.timeout = executable, driver, timeout_seconds
        exe = file_identity(executable)
        if not os.access(executable, os.X_OK): raise AvatarAuthoringError("blender_backend_unavailable")
        if expected_sha256 and exe["sha256"] != expected_sha256: raise AvatarAuthoringError("blender_executable_digest_mismatch")
        drv = file_identity(driver, maximum=1024 * 1024)
        self.identity = BackendIdentity("configured_blender", "blender-cli-static-driver", "1", str(executable.resolve()), exe["sha256"], drv["sha256"], tuple(OP_ARGUMENTS), "production")
    def author(self, predecessor: Path, plan: Mapping[str, Any], successor: Path) -> Mapping[str, Any]:
        plan_path = successor.parent.parent / "plan" / "authoring_plan.json"
        argv = [str(self.executable), "--background", str(predecessor), "--python", str(self.driver), "--", str(plan_path), str(successor), plan["plan_digest"]]
        result = run_supervised(argv, stage_id="avatar_blender_author", timeout_seconds=self.timeout,
                                env={"PATH": os.defpath, "PYTHONHASHSEED": "0", "LC_ALL": "C", "HOME": str(successor.parent.parent)}, shell=False)
        return {**result.to_dict(), "status": "completed" if result.return_code == 0 and not result.termination_reason else "failed", "authority": dict(FALSE_AUTHORITY)}


class BlenderArtifactInspector:
    """Distinct configured Blender invocation that reopens successor bytes."""
    def __init__(self, executable: Path, inspector_driver: Path, *, expected_sha256: str | None = None, timeout_seconds: float = 120) -> None:
        exe=file_identity(executable); drv=file_identity(inspector_driver, maximum=1024*1024)
        if not os.access(executable,os.X_OK): raise AvatarAuthoringError("blender_backend_unavailable")
        if expected_sha256 and exe["sha256"] != expected_sha256: raise AvatarAuthoringError("blender_executable_digest_mismatch")
        self.executable,self.driver,self.timeout=executable,inspector_driver,timeout_seconds
        self.identity=BackendIdentity("configured_blender_inspector","blender-cli-static-inspector","1",str(executable.resolve()),exe["sha256"],drv["sha256"],("inspect",),"production")
    def inspect(self, artifact: Path, asset_format: str) -> Mapping[str, Any]:
        before=file_identity(artifact); argv=[str(self.executable),"--background",str(artifact),"--python",str(self.driver)]
        result=run_supervised(argv,stage_id="avatar_blender_inspect",timeout_seconds=self.timeout,env={"PATH":os.defpath,"PYTHONHASHSEED":"0","LC_ALL":"C"},shell=False)
        if result.return_code or result.termination_reason: raise AvatarAuthoringError("inspector_failed")
        marker="SENTIENTOS_AVATAR_INSPECTION="; lines=[line for line in result.stdout_tail.splitlines() if line.startswith(marker)]
        if len(lines)!=1: raise AvatarAuthoringError("inspector_result_incomplete")
        try: structure=cast(dict[str,Any],json.loads(lines[0][len(marker):]))
        except json.JSONDecodeError as exc: raise AvatarAuthoringError("inspector_result_invalid") from exc
        after=file_identity(artifact)
        if before != after: raise AvatarAuthoringError("successor_digest_changed_during_inspection")
        value={"schema_version":INSPECTION_SCHEMA,"artifact_sha256":after["sha256"],"byte_size":after["byte_size"],"format":asset_format,"body_id":structure.get("body_id"),"labels":structure.get("labels",{}),"objects":structure.get("objects",{}),"armatures":structure.get("armatures",{}),"bones":structure.get("bones",{}),"materials":structure.get("materials",{}),"shape_keys":structure.get("shape_keys",{}),"channels":structure.get("channels",{}),"warnings":structure.get("warnings",[]),"unsupported":structure.get("unsupported",[]),"inspector_identity":asdict(self.identity)}
        value["inspection_digest"]=digest(value); return value


def blender_readiness(executable: Path, driver: Path, workspace_root: Path, *, expected_sha256: str | None = None) -> dict[str, Any]:
    base = {"status": "blender_backend_unavailable", "authority": dict(FALSE_AUTHORITY), "mutation_performed": False}
    try:
        workspace_root.resolve().mkdir(parents=True, exist_ok=True)
        backend = BlenderBackend(executable, driver, expected_sha256=expected_sha256, timeout_seconds=15)
    except (OSError, AvatarAuthoringError) as exc:
        return {**base, "reason": str(exc)}
    result = run_supervised([str(executable), "--background", "--version"], stage_id="avatar_blender_readiness", timeout_seconds=15, env={"PATH": os.defpath, "LC_ALL": "C"}, shell=False)
    return {"status": "blender_backend_ready" if result.return_code == 0 else "blender_backend_unavailable", "backend_identity": asdict(backend.identity), "version_stdout_tail": result.stdout_tail, "authority": dict(FALSE_AUTHORITY), "mutation_performed": False}


def prepare_workspace(root: Path, work_id: str, predecessor: Path, suffix: str) -> tuple[Path, Path, Path]:
    _name(work_id); root = root.resolve(); root.mkdir(parents=True, exist_ok=True)
    workspace = root / work_id
    if workspace.exists(): raise AvatarAuthoringError("authoring_workspace_exists")
    for child in ("input", "plan", "tool", "output", "evidence"): (workspace / child).mkdir(parents=True, mode=0o700)
    source = workspace / "input" / f"predecessor.{suffix}"; shutil.copyfile(predecessor, source); source.chmod(stat.S_IRUSR)
    return workspace, source, workspace / "output" / f"successor.{suffix}"


def build_admission(*, admission_id: str, work_id: str, pointer: Mapping[str, Any], plan: Mapping[str, Any], workspace: Path, backend: BackendIdentity, output: Path, operator_approval: str) -> dict[str, Any]:
    if not operator_approval: raise AvatarAuthoringError("authoring_approval_missing")
    value = {"schema_version": ADMISSION_SCHEMA, "admission_id": _name(admission_id), "work_id": _name(work_id), "current_generation": pointer["body_generation"], "predecessor_artifact_digest": pointer["artifact_sha256"], "predecessor_manifest_digest": pointer["manifest_digest"], "plan_digest": plan["plan_digest"], "workspace": str(workspace.resolve()), "backend_identity_digest": backend.semantic_digest, "requested_output": str(output.resolve()), "operation_count": len(plan["operations"]), "rollback_artifact_digest": pointer["artifact_sha256"], "operator_approval": operator_approval, "authority": {**FALSE_AUTHORITY, "execution_authority": True}}
    value["admission_digest"] = digest(value); return value


def run_workcell(*, current_pointer: Mapping[str, Any], predecessor_manifest: AvatarBodyManifest, predecessor: Path, plan_value: Mapping[str, Any], admission: Mapping[str, Any], workspace_root: Path, backend: AuthoringBackend, inspector: ArtifactInspector, work_id: str) -> dict[str, Any]:
    plan = validate_plan(plan_value); identity = file_identity(predecessor)
    if identity["sha256"] != current_pointer["artifact_sha256"] or predecessor_manifest.semantic_digest != current_pointer["manifest_digest"]: raise AvatarAuthoringError("predecessor_custody_mismatch")
    suffix = predecessor_manifest.asset_format
    workspace, copied, successor = prepare_workspace(workspace_root, work_id, predecessor, suffix)
    expected = build_admission(admission_id=admission["admission_id"], work_id=work_id, pointer=current_pointer, plan=plan, workspace=workspace, backend=backend.identity, output=successor, operator_approval=admission["operator_approval"])
    if admission.get("admission_digest") != expected["admission_digest"]: raise AvatarAuthoringError("authoring_admission_binding_mismatch")
    (workspace/"plan"/"authoring_plan.json").write_bytes(canonical_bytes(plan)+b"\n")
    before = dict(inspector.inspect(copied, suffix)); execution = dict(backend.author(copied, plan, successor))
    if execution.get("status") != "completed": raise AvatarAuthoringError("authoring_backend_failed")
    if not successor.exists(): raise AvatarAuthoringError("successor_artifact_missing")
    after = dict(inspector.inspect(successor, suffix)); comparison = compare_structure(before, plan, after)
    posture = "candidate_validated" if not comparison["counts"]["unsatisfied"] and not comparison["unexpected_changes"] else "candidate_rejected"
    receipt = {"schema_version": RECEIPT_SCHEMA, "work_id": work_id, "installation_body_id": plan["installation_body_id"], "body_id": plan["body_id"], "predecessor_generation": plan["predecessor_generation"], "predecessor_artifact": identity, "predecessor_manifest_digest": predecessor_manifest.semantic_digest, "predecessor_inspection_digest": before["inspection_digest"], "plan_id": plan["plan_id"], "plan_digest": plan["plan_digest"], "admission_id": admission["admission_id"], "admission_digest": admission["admission_digest"], "backend_identity": asdict(backend.identity), "execution_record": execution, "successor_artifact": file_identity(successor), "successor_inspection_digest": after["inspection_digest"], "comparison_digest": comparison["comparison_digest"], "counts": comparison["counts"], "warnings": after["warnings"], "rollback_artifact": identity, "result_posture": posture, "authority": dict(FALSE_AUTHORITY)}
    receipt["receipt_digest"] = digest(receipt)
    for name, value in (("predecessor_inspection",before),("backend_execution",execution),("successor_inspection",after),("structural_comparison",comparison),("authoring_receipt",receipt)):
        (workspace/"evidence"/f"{name}.json").write_bytes(canonical_bytes(value)+b"\n")
    return {"workspace": str(workspace), "successor_path": str(successor), "plan": plan, "predecessor_inspection": before, "successor_inspection": after, "comparison": comparison, "receipt": receipt}


def successor_manifest(predecessor: AvatarBodyManifest, result: Mapping[str, Any]) -> AvatarBodyManifest:
    if result["receipt"]["result_posture"] != "candidate_validated": raise AvatarAuthoringError("candidate_not_validated")
    ins = result["successor_inspection"]
    bones = tuple(sorted(ins["bones"])); expressions = tuple(sorted(k for values in ins["shape_keys"].values() for k in values))
    motions = tuple(sorted(k for k,v in ins["channels"].items() if v["kind"] == "motion")); visemes = tuple(sorted(k for k,v in ins["channels"].items() if v["kind"] == "viseme"))
    rig_digest = digest({"armatures": ins["armatures"], "channels": ins["channels"]})
    return AvatarBodyManifest(predecessor.installation_body_id, predecessor.avatar_asset_id, ins["artifact_sha256"], predecessor.asset_format,
        f"rig:{rig_digest[7:23]}", rig_digest, predecessor.renderer_interface_id, predecessor.coordinate_convention, bones, expressions, motions, visemes,
        predecessor.sensor_bindings, predecessor.output_bindings, predecessor.body_generation+1, predecessor.semantic_digest, result["receipt"]["receipt_digest"])


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); fd, name = tempfile.mkstemp(dir=path.parent, prefix=".avatar-", text=False)
    try:
        with os.fdopen(fd,"wb") as handle: handle.write(canonical_bytes(value)+b"\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)


@contextmanager
def _pointer_lock(path: Path) -> Iterator[None]:
    lock=path.with_suffix(path.suffix+".lock"); lock.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(lock,os.O_RDWR|os.O_CREAT|getattr(os,"O_NOFOLLOW",0),0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX); yield
    finally:
        fcntl.flock(fd,fcntl.LOCK_UN); os.close(fd)


def load_pointer(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file(): raise AvatarAuthoringError("current_body_pointer_not_regular")
    value=cast(dict[str, Any], json.loads(path.read_text())); claimed=value.pop("pointer_digest",None)
    if value.get("schema_version") != POINTER_SCHEMA or claimed != digest(value): raise AvatarAuthoringError("current_body_pointer_invalid")
    value["pointer_digest"]=claimed; return value


def genesis_adopt(*, pointer_path: Path, installation_id: str, body_id: str, artifact: Path, manifest: AvatarBodyManifest, approval: str) -> dict[str, Any]:
    if pointer_path.exists(): raise AvatarAuthoringError("genesis_requires_absent_pointer")
    if not approval: raise AvatarAuthoringError("adoption_approval_missing")
    ident=file_identity(artifact)
    if manifest.body_generation != 1 or ident["sha256"] != manifest.source_artifact_digest: raise AvatarAuthoringError("genesis_manifest_mismatch")
    value={"schema_version":POINTER_SCHEMA,"installation_identity":installation_id,"body_identity":body_id,"body_generation":1,"artifact_path":ident["path"],"artifact_sha256":ident["sha256"],"byte_size":ident["byte_size"],"manifest_digest":manifest.semantic_digest,"rig_semantic_digest":manifest.rig_semantic_digest,"predecessor_generation":None,"adoption_receipt_digest":"genesis:"+digest(approval)[7:],"update_sequence":1}
    value["pointer_digest"]=digest(value); _atomic_json(pointer_path,value); return value


def _append_lineage(path: Path, event: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_symlink(): raise AvatarAuthoringError("lineage_not_regular")
    with path.open("ab") as handle: handle.write(canonical_bytes(event)+b"\n"); handle.flush(); os.fsync(handle.fileno())


def adopt(*, pointer_path: Path, lineage_path: Path, expected_pointer_digest: str, candidate: Mapping[str, Any], manifest: AvatarBodyManifest, approval: str) -> dict[str, Any]:
    if not approval: raise AvatarAuthoringError("adoption_approval_missing")
    if candidate["receipt"]["result_posture"] != "candidate_validated": raise AvatarAuthoringError("candidate_not_validated")
    ident=file_identity(Path(candidate["successor_path"]))
    if ident["sha256"] != candidate["successor_inspection"]["artifact_sha256"] or manifest.source_artifact_digest != ident["sha256"]: raise AvatarAuthoringError("successor_digest_changed_after_inspection")
    with _pointer_lock(pointer_path):
        current=load_pointer(pointer_path)
        if current["pointer_digest"] != expected_pointer_digest or current["body_generation"]+1 != manifest.body_generation: raise AvatarAuthoringError("body_generation_compare_and_swap_failed")
        receipt={"schema_version":ADOPTION_SCHEMA,"adoption_id":"adopt:"+candidate["receipt"]["receipt_digest"][7:23],"from_generation":current["body_generation"],"to_generation":manifest.body_generation,"predecessor_pointer_digest":current["pointer_digest"],"successor_artifact_sha256":ident["sha256"],"successor_manifest_digest":manifest.semantic_digest,"authoring_receipt_digest":candidate["receipt"]["receipt_digest"],"approval":approval,"authority":dict(FALSE_AUTHORITY)}
        receipt["adoption_receipt_digest"]=digest(receipt)
        new={"schema_version":POINTER_SCHEMA,"installation_identity":current["installation_identity"],"body_identity":current["body_identity"],"body_generation":manifest.body_generation,"artifact_path":ident["path"],"artifact_sha256":ident["sha256"],"byte_size":ident["byte_size"],"manifest_digest":manifest.semantic_digest,"rig_semantic_digest":manifest.rig_semantic_digest,"predecessor_generation":current["body_generation"],"adoption_receipt_digest":receipt["adoption_receipt_digest"],"update_sequence":current["update_sequence"]+1}
        new["pointer_digest"]=digest(new); _atomic_json(pointer_path,new)
    event={"schema_version":LINEAGE_SCHEMA,"event":"adoption","generation":manifest.body_generation,"predecessor_generation":current["body_generation"],"artifact_sha256":ident["sha256"],"manifest_digest":manifest.semantic_digest,"authoring_receipt_digest":candidate["receipt"]["receipt_digest"],"adoption_receipt_digest":receipt["adoption_receipt_digest"],"rolled_back":False}; event["event_digest"]=digest(event); _append_lineage(lineage_path,event)
    return {"pointer":new,"receipt":receipt,"event":event,"predecessor_pointer":current}


def rollback(*, pointer_path: Path, lineage_path: Path, adopted: Mapping[str, Any], predecessor_manifest: AvatarBodyManifest, approval: str) -> dict[str, Any]:
    if not approval: raise AvatarAuthoringError("rollback_approval_missing")
    prior=adopted["predecessor_pointer"]
    ident=file_identity(Path(prior["artifact_path"]))
    if ident["sha256"] != prior["artifact_sha256"] or predecessor_manifest.semantic_digest != prior["manifest_digest"]: raise AvatarAuthoringError("rollback_target_digest_mismatch")
    with _pointer_lock(pointer_path):
        current=load_pointer(pointer_path)
        if current["pointer_digest"] != adopted["pointer"]["pointer_digest"]: raise AvatarAuthoringError("body_generation_compare_and_swap_failed")
        restored={**prior,"update_sequence":current["update_sequence"]+1,"adoption_receipt_digest":"rollback-pending"}; restored.pop("pointer_digest",None)
        receipt={"schema_version":ROLLBACK_SCHEMA,"from_generation":current["body_generation"],"to_generation":prior["body_generation"],"reverted_adoption_receipt_digest":adopted["receipt"]["adoption_receipt_digest"],"restored_artifact_sha256":ident["sha256"],"approval":approval,"authority":dict(FALSE_AUTHORITY)}; receipt["rollback_receipt_digest"]=digest(receipt)
        restored["adoption_receipt_digest"]=receipt["rollback_receipt_digest"]; restored["pointer_digest"]=digest(restored); _atomic_json(pointer_path,restored)
    event={"schema_version":LINEAGE_SCHEMA,"event":"rollback","generation":current["body_generation"],"restored_generation":prior["body_generation"],"rollback_receipt_digest":receipt["rollback_receipt_digest"],"historical_generation_preserved":True}; event["event_digest"]=digest(event); _append_lineage(lineage_path,event)
    return {"pointer":restored,"receipt":receipt,"event":event}


def lineage(path: Path) -> list[dict[str, Any]]:
    if path.is_symlink(): raise AvatarAuthoringError("lineage_not_regular")
    rows=[]
    for line in path.read_text().splitlines() if path.exists() else []:
        row=json.loads(line); claimed=row.pop("event_digest");
        if claimed != digest(row): raise AvatarAuthoringError("lineage_digest_mismatch")
        row["event_digest"]=claimed; rows.append(row)
    return rows


def adoption_observation(pointer: Mapping[str, Any], manifest: AvatarBodyManifest, *, observed_at: str, posture: str="production") -> EmbodimentObservation:
    payload=asdict(manifest)
    return EmbodimentObservation("body-adoption:"+pointer["adoption_receipt_digest"], ADOPTION_SCHEMA, pointer["adoption_receipt_digest"], observed_at, "adoption_receipt", "fresh", posture, "body_manifest", pointer["body_identity"], "adopted_avatar_body", payload)


def renderer_handoff(pointer: Mapping[str, Any], *, renderer_interface_id: str, requested_pose: str, requested_expression: str, correlation_id: str) -> dict[str, Any]:
    value={"schema_version":HANDOFF_SCHEMA,"body_generation":pointer["body_generation"],"artifact_sha256":pointer["artifact_sha256"],"body_manifest_digest":pointer["manifest_digest"],"renderer_interface_id":_name(renderer_interface_id),"requested_test_pose":_name(requested_pose),"requested_test_expression":_name(requested_expression),"correlation_id":_name(correlation_id),"evidence_class":"commanded_output","renderer_reported":False,"independently_observed":False,"authority":dict(FALSE_AUTHORITY)}
    value["handoff_digest"]=digest(value); return value
