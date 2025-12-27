from __future__ import annotations

from typing import Mapping

from sentientos.authority_surface import compute_authority_surface_hash, diff_authority_surfaces


def _snapshot(
    *,
    adapters: list[Mapping[str, object]] | None = None,
    routines: list[Mapping[str, object]] | None = None,
    semantic_classes: list[Mapping[str, object]] | None = None,
    privilege_posture: Mapping[str, object] | None = None,
    execution_rules: Mapping[str, object] | None = None,
) -> dict[str, object]:
    snapshot: dict[str, object] = {
        "version": "authority_surface_v1",
        "adapters": adapters or [],
        "delegated_routines": routines or [],
        "semantic_habit_classes": semantic_classes or [],
        "privilege_posture": privilege_posture
        or {
            "required_privileges": [],
            "approval_envelope": {},
            "privilege_surface": {},
        },
        "execution_rules": execution_rules
        or {
            "enabled_epr_categories": ["none"],
            "irreversible_blocks": [],
            "external_effects_forbidden": True,
            "approval_rules": [],
            "closure_limits": {},
        },
    }
    snapshot["snapshot_hash"] = compute_authority_surface_hash(snapshot)
    return snapshot


def _adapter_snapshot(adapter_id: str, scope: list[str]) -> dict[str, object]:
    return {
        "adapter_id": adapter_id,
        "capabilities": ["read"],
        "scope": scope,
        "reversibility": "guaranteed",
        "external_effects": "no",
        "requires_privilege": False,
        "privilege_requirements": [],
    }


def _routine_snapshot(routine_id: str, state: str) -> dict[str, object]:
    return {
        "routine_id": routine_id,
        "trigger": {"id": "t1", "description": "trigger"},
        "scope": ["core"],
        "state": state,
        "authority_impact": "none",
        "reversibility": "guaranteed",
        "policy": {},
        "privilege_requirements": [],
    }


def test_adapter_scope_expansion_detected() -> None:
    before = _snapshot(adapters=[_adapter_snapshot("filesystem", ["core"])])
    after = _snapshot(adapters=[_adapter_snapshot("filesystem", ["core", "extended"])])
    diff = diff_authority_surfaces(before, after)
    assert any(
        change["category"] == "adapter" and change["change_type"] == "expand"
        for change in diff["changes"]
    )


def test_privilege_requirement_changes_detected() -> None:
    before = _snapshot(
        privilege_posture={
            "required_privileges": ["privilege:adapter:filesystem:read"],
            "approval_envelope": {},
            "privilege_surface": {},
        }
    )
    after = _snapshot(
        privilege_posture={
            "required_privileges": [
                "privilege:adapter:filesystem:read",
                "privilege:adapter:filesystem:write",
            ],
            "approval_envelope": {},
            "privilege_surface": {},
        }
    )
    diff = diff_authority_surfaces(before, after)
    assert any(
        change["category"] == "privilege" and change["change_type"] == "expand"
        for change in diff["changes"]
    )


def test_routine_activation_deactivation_detected() -> None:
    before = _snapshot(routines=[_routine_snapshot("routine-1", "active")])
    after = _snapshot(routines=[_routine_snapshot("routine-1", "paused")])
    diff = diff_authority_surfaces(before, after)
    assert any(
        change["category"] == "routine"
        and change["change_type"] == "modify"
        and "state changed from active to paused" in change["description"]
        for change in diff["changes"]
    )


def test_semantic_only_changes_flagged() -> None:
    before = _snapshot(
        semantic_classes=[
            {
                "class_id": "class-1",
                "name": "Pattern",
                "member_routines": ["routine-1", "routine-2"],
                "semantic_only": True,
                "scope": ["core"],
            }
        ]
    )
    after = _snapshot(
        semantic_classes=[
            {
                "class_id": "class-1",
                "name": "Pattern",
                "member_routines": ["routine-1", "routine-2", "routine-3"],
                "semantic_only": True,
                "scope": ["core"],
            }
        ]
    )
    diff = diff_authority_surfaces(before, after)
    assert any(change["impact"] == "semantic_only" for change in diff["changes"])


def test_noop_changes_produce_empty_diff() -> None:
    snapshot = _snapshot(adapters=[_adapter_snapshot("filesystem", ["core"])])
    diff = diff_authority_surfaces(snapshot, snapshot)
    assert diff["changes"] == []


def test_deterministic_ordering_of_diff_output() -> None:
    before = _snapshot(
        adapters=[_adapter_snapshot("filesystem", ["core"])],
        routines=[_routine_snapshot("routine-1", "active")],
    )
    after = _snapshot(
        adapters=[
            _adapter_snapshot("filesystem", ["core", "extended"]),
            _adapter_snapshot("network", ["edge"]),
        ],
        routines=[_routine_snapshot("routine-1", "paused")],
        privilege_posture={
            "required_privileges": ["privilege:adapter:network:read"],
            "approval_envelope": {},
            "privilege_surface": {},
        },
    )
    diff = diff_authority_surfaces(before, after)
    order = {"add": 0, "remove": 1, "expand": 2, "narrow": 3, "modify": 4}
    changes = diff["changes"]
    sorted_changes = sorted(
        changes,
        key=lambda item: (
            order.get(item.get("change_type", ""), 99),
            str(item.get("category", "")),
            str(item.get("description", "")),
        ),
    )
    assert changes == sorted_changes
