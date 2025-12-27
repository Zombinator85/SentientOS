from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import control_plane.policy
import task_admission
import task_executor
from logging_config import get_log_path
from log_utils import append_json, read_json
from sentientos.external_adapters import list_adapters
from sentientos.governance.routine_delegation import DEFAULT_LOG_PATH as ROUTINE_LOG_PATH
from sentientos.governance.routine_delegation import RoutineDefinition, RoutineRegistry
from sentientos.governance.semantic_habit_class import DEFAULT_LOG_PATH as SEMANTIC_CLASS_LOG_PATH
from sentientos.system_identity import compute_system_identity_digest

AUTHORITY_SURFACE_VERSION = "authority_surface_v1"
DEFAULT_SNAPSHOT_GIT_PATH = "config/authority_surface_snapshot.json"
AUTHORITY_DIFF_LOG_PATH = get_log_path(
    "authority_surface_diffs.jsonl",
    "AUTHORITY_SURFACE_DIFF_LOG",
)


def build_authority_surface_snapshot() -> dict[str, object]:
    adapters = _snapshot_adapters()
    routines = _snapshot_routines()
    semantic_classes = _snapshot_semantic_habits()
    privilege_posture = _snapshot_privilege_posture(adapters, routines)
    execution_rules = _snapshot_execution_rules(privilege_posture)

    snapshot = {
        "version": AUTHORITY_SURFACE_VERSION,
        "adapters": adapters,
        "delegated_routines": routines,
        "semantic_habit_classes": semantic_classes,
        "privilege_posture": privilege_posture,
        "execution_rules": execution_rules,
    }
    snapshot["snapshot_hash"] = compute_authority_surface_hash(snapshot)
    return snapshot


def compute_authority_surface_hash(snapshot: Mapping[str, object]) -> str:
    payload = dict(snapshot)
    payload.pop("snapshot_hash", None)
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def load_authority_surface_snapshot(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Authority surface snapshot must be a JSON object")
    if "snapshot_hash" not in payload:
        payload["snapshot_hash"] = compute_authority_surface_hash(payload)
    return payload


def resolve_snapshot_source(source: str | None) -> tuple[dict[str, object], str]:
    if source is None or source in {"runtime", "current", "now"}:
        snapshot = build_authority_surface_snapshot()
        return snapshot, "runtime"

    if source.startswith("snapshot:"):
        path = Path(source.split(":", 1)[1])
        return load_authority_surface_snapshot(path), f"snapshot:{path}"

    if source.startswith("config:"):
        path = Path(source.split(":", 1)[1])
        return load_authority_surface_snapshot(path), f"config:{path}"

    if source.startswith("git:"):
        snapshot = _load_snapshot_from_git(source)
        return snapshot, source

    path = Path(source)
    if path.exists():
        return load_authority_surface_snapshot(path), str(path)

    raise ValueError(f"Unknown authority surface source: {source}")


def diff_authority_surfaces(
    before: Mapping[str, object],
    after: Mapping[str, object],
) -> dict[str, object]:
    changes: list[dict[str, str]] = []

    _diff_adapters(before.get("adapters", ()), after.get("adapters", ()), changes)
    _diff_routines(before.get("delegated_routines", ()), after.get("delegated_routines", ()), changes)
    _diff_semantic_classes(
        before.get("semantic_habit_classes", ()),
        after.get("semantic_habit_classes", ()),
        changes,
    )
    _diff_privilege_posture(
        before.get("privilege_posture", {}),
        after.get("privilege_posture", {}),
        changes,
    )
    _diff_execution_rules(
        before.get("execution_rules", {}),
        after.get("execution_rules", {}),
        changes,
    )

    ordered = _order_changes(changes)
    return {
        "view": "authority_surface_diff",
        "from_hash": str(before.get("snapshot_hash", "")),
        "to_hash": str(after.get("snapshot_hash", "")),
        "changes": ordered,
        "summary": _summarize_changes(ordered),
    }


def log_authority_surface_diff(
    diff: Mapping[str, object],
    *,
    source_from: str,
    source_to: str,
) -> None:
    entry = {
        "event": "authority_surface_diff",
        "authority": "none",
        "side_effects": "none",
        "source_from": source_from,
        "source_to": source_to,
        "from_hash": diff.get("from_hash"),
        "to_hash": diff.get("to_hash"),
        "change_count": len(diff.get("changes", ())),
        "summary": diff.get("summary"),
        "changes": diff.get("changes"),
    }
    append_json(Path(AUTHORITY_DIFF_LOG_PATH), entry)


def _snapshot_adapters() -> list[dict[str, object]]:
    adapters = []
    for adapter_id, adapter_cls in list_adapters().items():
        metadata = adapter_cls.metadata
        privilege_requirements = _adapter_privileges(adapter_id, adapter_cls)
        adapters.append({
            "adapter_id": adapter_id,
            "capabilities": sorted(metadata.capabilities),
            "scope": metadata.scope,
            "reversibility": metadata.reversibility,
            "external_effects": metadata.external_effects,
            "requires_privilege": metadata.requires_privilege,
            "privilege_requirements": privilege_requirements,
        })
    adapters.sort(key=lambda item: item["adapter_id"])
    return adapters


def _adapter_privileges(adapter_id: str, adapter_cls: object) -> list[str]:
    privileges: set[str] = set()
    metadata = getattr(adapter_cls, "metadata", None)
    if metadata is not None and getattr(metadata, "requires_privilege", False):
        privileges.add(f"privilege:adapter:{adapter_id}")
    action_specs = getattr(adapter_cls, "action_specs", {})
    if isinstance(action_specs, Mapping):
        for action, spec in action_specs.items():
            requires_priv = getattr(spec, "requires_privilege", False)
            if requires_priv:
                privileges.add(f"privilege:adapter:{adapter_id}:{action}")
    return sorted(privileges)


def _snapshot_routines() -> list[dict[str, object]]:
    registry = RoutineRegistry()
    routine_statuses = _routine_statuses(_read_log(Path(ROUTINE_LOG_PATH)))
    routines: list[dict[str, object]] = []
    for routine in registry.list_routines():
        routines.append(_routine_snapshot(routine, routine_statuses.get(routine.routine_id)))
    routines.sort(key=lambda item: item["routine_id"])
    return routines


def _routine_snapshot(
    routine: RoutineDefinition,
    status: str | None,
) -> dict[str, object]:
    privilege_requirements = _routine_privileges(routine)
    return {
        "routine_id": routine.routine_id,
        "trigger": {
            "id": routine.trigger_id,
            "description": routine.trigger_description,
        },
        "scope": list(routine.scope),
        "state": status or "active",
        "authority_impact": routine.authority_impact,
        "reversibility": routine.reversibility,
        "policy": dict(routine.policy),
        "privilege_requirements": privilege_requirements,
    }


def _routine_privileges(routine: RoutineDefinition) -> list[str]:
    privileges: set[str] = set()
    for key, value in routine.policy.items():
        if key.startswith("allows_") and value:
            privileges.add(f"privilege:routine:{routine.routine_id}:{key}")
    if routine.authority_impact and routine.authority_impact != "none":
        privileges.add(f"privilege:routine:{routine.routine_id}:authority:{routine.authority_impact}")
    return sorted(privileges)


def _routine_statuses(entries: Iterable[Mapping[str, object]]) -> dict[str, str]:
    last_outcome: dict[str, str] = {}
    conflict_prompted: set[str] = set()
    for entry in entries:
        event = entry.get("event")
        if event == "routine_evaluation":
            routine_id = entry.get("routine_id")
            outcome = entry.get("outcome")
            if isinstance(routine_id, str) and isinstance(outcome, str):
                last_outcome[routine_id] = outcome
        if event == "routine_conflict_prompt":
            routines_payload = entry.get("routines")
            if isinstance(routines_payload, list):
                for routine in routines_payload:
                    routine_id = routine.get("routine_id") if isinstance(routine, Mapping) else None
                    if isinstance(routine_id, str):
                        conflict_prompted.add(routine_id)

    statuses: dict[str, str] = {}
    for routine_id, outcome in last_outcome.items():
        status = "active"
        if routine_id in conflict_prompted or outcome == "conflict_suppressed":
            status = "conflicted"
        elif outcome == "conflict_paused":
            status = "paused"
        statuses[routine_id] = status
    for routine_id in conflict_prompted:
        statuses.setdefault(routine_id, "conflicted")
    return statuses


def _snapshot_semantic_habits() -> list[dict[str, object]]:
    entries = _read_log(Path(SEMANTIC_CLASS_LOG_PATH))
    classes: dict[str, dict[str, object]] = {}
    for entry in entries:
        event = entry.get("event")
        if event not in {
            "semantic_class_created",
            "semantic_class_approved",
            "semantic_class_revoked",
        }:
            continue
        class_id = str(entry.get("class_id", ""))
        name = str(entry.get("name", ""))
        if not class_id or not name:
            continue
        if event == "semantic_class_revoked":
            classes.pop(class_id, None)
            continue
        routine_ids = entry.get("routine_ids", ())
        routines = [str(rid) for rid in routine_ids if rid]
        classes[class_id] = {
            "class_id": class_id,
            "name": name,
            "member_routines": sorted(routines),
            "semantic_only": True,
            "scope": sorted(entry.get("scope", ())),
        }
    snapshot = list(classes.values())
    snapshot.sort(key=lambda item: item["class_id"])
    return snapshot


def _snapshot_privilege_posture(
    adapters: Sequence[Mapping[str, object]],
    routines: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    required_privileges: set[str] = set()
    for adapter in adapters:
        required_privileges.update(adapter.get("privilege_requirements", ()))
    for routine in routines:
        required_privileges.update(routine.get("privilege_requirements", ()))

    admission_policy = _default_admission_policy()
    identity = compute_system_identity_digest(
        admission_policy=admission_policy,
        control_policy=control_plane.policy.load_policy(),
        closure_limits=task_executor.load_closure_limits(),
        metadata={
            "policy_source": "default_admission_policy",
            "policy_version": admission_policy.policy_version,
        },
    )
    components = identity.get("components", {})
    governance = components.get("governance", {})
    privilege_surface = components.get("privilege_surface", {})

    return {
        "required_privileges": sorted(required_privileges),
        "approval_envelope": {
            "admission_policy": governance.get("admission", {}),
            "control_policy": governance.get("authorization", {}),
            "closure_limits": governance.get("closure_rules", {}),
        },
        "privilege_surface": privilege_surface,
    }


def _snapshot_execution_rules(privilege_posture: Mapping[str, object]) -> dict[str, object]:
    execution = privilege_posture.get("approval_envelope", {})
    identity = compute_system_identity_digest(
        admission_policy=execution.get("admission_policy", {}),
        control_policy=execution.get("control_policy", {}),
        closure_limits=execution.get("closure_limits", {}),
        metadata={"policy_source": "authority_surface_snapshot"},
    )
    execution_rules = identity.get("components", {}).get("execution", {})
    epr_rules = execution_rules.get("epr_rules", {})
    return {
        "enabled_epr_categories": tuple(epr_rules.get("allowed_authority_impact", ())),
        "irreversible_blocks": tuple(epr_rules.get("prohibited_mutations", ())),
        "external_effects_forbidden": bool(epr_rules.get("external_effects_forbidden", False)),
        "approval_rules": epr_rules.get("approval_rules", ()),
        "closure_limits": execution_rules.get("exhaustion_limits", {}),
    }


def _default_admission_policy() -> task_admission.AdmissionPolicy:
    policy_version = os.getenv("SENTIENTOS_ADMISSION_POLICY_VERSION", "default")
    return task_admission.AdmissionPolicy(policy_version=policy_version)


def _load_snapshot_from_git(source: str) -> dict[str, object]:
    _, _, remainder = source.partition(":")
    ref, _, path = remainder.partition(":")
    if not ref:
        raise ValueError("git source must include a ref")
    snapshot_path = path or DEFAULT_SNAPSHOT_GIT_PATH
    command = ["git", "show", f"{ref}:{snapshot_path}"]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise ValueError(
            f"Unable to load snapshot from git ref '{ref}' at '{snapshot_path}': {result.stderr.strip()}"
        )
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise ValueError("Authority surface snapshot must be a JSON object")
    if "snapshot_hash" not in payload:
        payload["snapshot_hash"] = compute_authority_surface_hash(payload)
    return payload


def _read_log(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    try:
        return read_json(path)
    except Exception:
        return []


def _diff_adapters(
    before: object,
    after: object,
    changes: list[dict[str, str]],
) -> None:
    before_map = _map_by_id(before, "adapter_id")
    after_map = _map_by_id(after, "adapter_id")
    all_ids = sorted(set(before_map) | set(after_map))

    for adapter_id in all_ids:
        if adapter_id not in before_map:
            adapter = after_map[adapter_id]
            changes.append(_change(
                "adapter",
                "add",
                "authority",
                f"Adapter '{adapter_id}' added with scope '{adapter.get('scope')}'.",
            ))
            continue
        if adapter_id not in after_map:
            changes.append(_change(
                "adapter",
                "remove",
                "authority",
                f"Adapter '{adapter_id}' removed from authority surface.",
            ))
            continue
        _diff_adapter_details(before_map[adapter_id], after_map[adapter_id], changes)


def _diff_adapter_details(
    before: Mapping[str, object],
    after: Mapping[str, object],
    changes: list[dict[str, str]],
) -> None:
    adapter_id = str(after.get("adapter_id", before.get("adapter_id", "")))
    _diff_scope(
        "adapter",
        adapter_id,
        before.get("scope"),
        after.get("scope"),
        changes,
    )
    _diff_set_changes(
        "adapter",
        adapter_id,
        "capabilities",
        before.get("capabilities", ()),
        after.get("capabilities", ()),
        changes,
    )
    _diff_set_changes(
        "privilege",
        adapter_id,
        "privilege_requirements",
        before.get("privilege_requirements", ()),
        after.get("privilege_requirements", ()),
        changes,
    )
    _diff_value_change(
        "adapter",
        adapter_id,
        "external_effects",
        before.get("external_effects"),
        after.get("external_effects"),
        changes,
    )
    _diff_value_change(
        "adapter",
        adapter_id,
        "reversibility",
        before.get("reversibility"),
        after.get("reversibility"),
        changes,
    )
    _diff_value_change(
        "privilege",
        adapter_id,
        "requires_privilege",
        before.get("requires_privilege"),
        after.get("requires_privilege"),
        changes,
    )


def _diff_routines(
    before: object,
    after: object,
    changes: list[dict[str, str]],
) -> None:
    before_map = _map_by_id(before, "routine_id")
    after_map = _map_by_id(after, "routine_id")
    all_ids = sorted(set(before_map) | set(after_map))

    for routine_id in all_ids:
        if routine_id not in before_map:
            routine = after_map[routine_id]
            changes.append(_change(
                "routine",
                "add",
                "authority",
                f"Routine '{routine_id}' added with scope {routine.get('scope')}",
            ))
            continue
        if routine_id not in after_map:
            changes.append(_change(
                "routine",
                "remove",
                "authority",
                f"Routine '{routine_id}' removed from delegation registry.",
            ))
            continue
        _diff_routine_details(before_map[routine_id], after_map[routine_id], changes)


def _diff_routine_details(
    before: Mapping[str, object],
    after: Mapping[str, object],
    changes: list[dict[str, str]],
) -> None:
    routine_id = str(after.get("routine_id", before.get("routine_id", "")))
    _diff_scope(
        "routine",
        routine_id,
        before.get("scope"),
        after.get("scope"),
        changes,
    )
    _diff_set_changes(
        "privilege",
        routine_id,
        "privilege_requirements",
        before.get("privilege_requirements", ()),
        after.get("privilege_requirements", ()),
        changes,
    )
    _diff_value_change(
        "routine",
        routine_id,
        "state",
        before.get("state"),
        after.get("state"),
        changes,
    )
    _diff_value_change(
        "routine",
        routine_id,
        "authority_impact",
        before.get("authority_impact"),
        after.get("authority_impact"),
        changes,
    )
    _diff_value_change(
        "routine",
        routine_id,
        "reversibility",
        before.get("reversibility"),
        after.get("reversibility"),
        changes,
    )
    _diff_trigger(before.get("trigger"), after.get("trigger"), routine_id, changes)
    _diff_value_change(
        "routine",
        routine_id,
        "policy",
        before.get("policy"),
        after.get("policy"),
        changes,
    )


def _diff_semantic_classes(
    before: object,
    after: object,
    changes: list[dict[str, str]],
) -> None:
    before_map = _map_by_id(before, "class_id")
    after_map = _map_by_id(after, "class_id")
    all_ids = sorted(set(before_map) | set(after_map))

    for class_id in all_ids:
        if class_id not in before_map:
            name = after_map[class_id].get("name")
            changes.append(_change(
                "routine",
                "add",
                "semantic_only",
                f"Semantic habit class '{name}' ({class_id}) added.",
            ))
            continue
        if class_id not in after_map:
            name = before_map[class_id].get("name")
            changes.append(_change(
                "routine",
                "remove",
                "semantic_only",
                f"Semantic habit class '{name}' ({class_id}) removed.",
            ))
            continue
        _diff_semantic_class_details(before_map[class_id], after_map[class_id], changes)


def _diff_semantic_class_details(
    before: Mapping[str, object],
    after: Mapping[str, object],
    changes: list[dict[str, str]],
) -> None:
    class_id = str(after.get("class_id", before.get("class_id", "")))
    name = str(after.get("name", before.get("name", "")))
    _diff_set_changes(
        "routine",
        class_id,
        f"semantic class '{name}' member routines",
        before.get("member_routines", ()),
        after.get("member_routines", ()),
        changes,
        impact="semantic_only",
    )
    _diff_scope(
        "routine",
        f"semantic class '{name}'",
        before.get("scope"),
        after.get("scope"),
        changes,
        impact="semantic_only",
    )


def _diff_privilege_posture(
    before: object,
    after: object,
    changes: list[dict[str, str]],
) -> None:
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        return
    _diff_set_changes(
        "privilege",
        "privilege_posture",
        "required_privileges",
        before.get("required_privileges", ()),
        after.get("required_privileges", ()),
        changes,
    )
    _diff_value_change(
        "privilege",
        "privilege_posture",
        "approval_envelope",
        before.get("approval_envelope"),
        after.get("approval_envelope"),
        changes,
    )
    _diff_value_change(
        "privilege",
        "privilege_posture",
        "privilege_surface",
        before.get("privilege_surface"),
        after.get("privilege_surface"),
        changes,
    )


def _diff_execution_rules(
    before: object,
    after: object,
    changes: list[dict[str, str]],
) -> None:
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        return
    _diff_set_changes(
        "execution",
        "execution_rules",
        "enabled_epr_categories",
        before.get("enabled_epr_categories", ()),
        after.get("enabled_epr_categories", ()),
        changes,
    )
    _diff_set_changes(
        "execution",
        "execution_rules",
        "irreversible_blocks",
        before.get("irreversible_blocks", ()),
        after.get("irreversible_blocks", ()),
        changes,
    )
    _diff_value_change(
        "execution",
        "execution_rules",
        "approval_rules",
        before.get("approval_rules"),
        after.get("approval_rules"),
        changes,
    )
    _diff_value_change(
        "execution",
        "execution_rules",
        "closure_limits",
        before.get("closure_limits"),
        after.get("closure_limits"),
        changes,
    )
    _diff_value_change(
        "execution",
        "execution_rules",
        "external_effects_forbidden",
        before.get("external_effects_forbidden"),
        after.get("external_effects_forbidden"),
        changes,
    )


def _diff_trigger(
    before: object,
    after: object,
    routine_id: str,
    changes: list[dict[str, str]],
) -> None:
    if before == after:
        return
    changes.append(_change(
        "routine",
        "modify",
        "authority",
        f"Routine '{routine_id}' trigger changed from {before} to {after}.",
    ))


def _diff_scope(
    category: str,
    entity_id: str,
    before: object,
    after: object,
    changes: list[dict[str, str]],
    *,
    impact: str = "authority",
) -> None:
    before_set = _as_scope_set(before)
    after_set = _as_scope_set(after)
    if before_set == after_set:
        return
    change_type = "modify"
    if before_set and after_set:
        if before_set < after_set:
            change_type = "expand"
        elif before_set > after_set:
            change_type = "narrow"
    elif after_set and not before_set:
        change_type = "expand"
    elif before_set and not after_set:
        change_type = "narrow"
    changes.append(_change(
        category,
        change_type,
        impact,
        f"{category.title()} '{entity_id}' scope changed from {sorted(before_set)} to {sorted(after_set)}.",
    ))


def _diff_set_changes(
    category: str,
    entity_id: str,
    label: str,
    before: object,
    after: object,
    changes: list[dict[str, str]],
    *,
    impact: str = "authority",
) -> None:
    before_set = _as_set(before)
    after_set = _as_set(after)
    if before_set == after_set:
        return
    added = sorted(after_set - before_set)
    removed = sorted(before_set - after_set)
    if added and removed:
        change_type = "modify"
        detail = f"added {added} and removed {removed}"
    elif added:
        change_type = "expand"
        detail = f"added {added}"
    else:
        change_type = "narrow"
        detail = f"removed {removed}"
    changes.append(_change(
        category,
        change_type,
        impact,
        f"{category.title()} '{entity_id}' {label} {detail}.",
    ))


def _diff_value_change(
    category: str,
    entity_id: str,
    label: str,
    before: object,
    after: object,
    changes: list[dict[str, str]],
) -> None:
    if before == after:
        return
    changes.append(_change(
        category,
        "modify",
        "authority",
        f"{category.title()} '{entity_id}' {label} changed from {before} to {after}.",
    ))


def _map_by_id(items: object, key: str) -> dict[str, Mapping[str, object]]:
    if not isinstance(items, Sequence):
        return {}
    output: dict[str, Mapping[str, object]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        identifier = item.get(key)
        if isinstance(identifier, str) and identifier:
            output[identifier] = item
    return output


def _as_set(value: object) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        return {str(item) for item in value if item is not None}
    if value is None:
        return set()
    return {str(value)}


def _as_scope_set(value: object) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        return {str(item) for item in value if item}
    if value is None:
        return set()
    return {str(value)}


def _change(
    category: str,
    change_type: str,
    impact: str,
    description: str,
) -> dict[str, str]:
    return {
        "category": category,
        "change_type": change_type,
        "impact": impact,
        "description": description,
    }


def _summarize_changes(changes: Iterable[Mapping[str, str]]) -> dict[str, int]:
    summary = {"total": 0, "authority": 0, "semantic_only": 0}
    for change in changes:
        summary["total"] += 1
        impact = change.get("impact")
        if impact == "semantic_only":
            summary["semantic_only"] += 1
        else:
            summary["authority"] += 1
    return summary


def _order_changes(changes: list[dict[str, str]]) -> list[dict[str, str]]:
    order = {"add": 0, "remove": 1, "expand": 2, "narrow": 3, "modify": 4}

    def sort_key(item: Mapping[str, str]) -> tuple[int, str, str]:
        return (
            order.get(item.get("change_type", ""), 99),
            str(item.get("category", "")),
            str(item.get("description", "")),
        )

    return sorted(changes, key=sort_key)
