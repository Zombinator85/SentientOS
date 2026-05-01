from __future__ import annotations

from sentientos import orchestration_internal_adapters
from sentientos import orchestration_projection_policy
from sentientos.orchestration_spine.adapters import (
    ADAPTER_FAMILIES,
    ADAPTER_FAMILY_INTERNAL_MAINTENANCE,
    internal_maintenance,
)
from sentientos.orchestration_spine.projection import (
    PROJECTION_FAMILIES,
    PROJECTION_FAMILY_CURRENT_STATE,
    PROJECTION_FAMILY_POLICY,
    current_state,
    policy_helpers,
    resolve_current_orchestration_bundle_projection,
)
from sentientos.orchestration_intent_fabric import resolve_current_orchestration_bundle


def test_projection_policy_compatibility_shim_exports_same_callable() -> None:
    assert orchestration_projection_policy.derive_attention_projection is policy_helpers.derive_attention_projection


def test_internal_adapter_compatibility_shim_exports_same_callable() -> None:
    assert orchestration_internal_adapters.build_internal_maintenance_task is internal_maintenance.build_internal_maintenance_task


def test_projection_module_exposes_documented_family_inventory() -> None:
    assert PROJECTION_FAMILIES == (PROJECTION_FAMILY_CURRENT_STATE, PROJECTION_FAMILY_POLICY)
    assert PROJECTION_FAMILY_CURRENT_STATE == "current_state"
    assert PROJECTION_FAMILY_POLICY == "policy"
    assert "resolve_current_orchestration_digest" in current_state.CURRENT_STATE_PROJECTION_FAMILY_PICTURE_COMPRESSION
    assert resolve_current_orchestration_bundle_projection is current_state.resolve_current_orchestration_bundle_projection
    assert "derive_next_venue_projection" in policy_helpers.POLICY_PROJECTION_FAMILY_RECOMMENDATION


def test_bundle_exports_available_from_projection_and_facade() -> None:
    assert callable(resolve_current_orchestration_bundle_projection)
    assert callable(resolve_current_orchestration_bundle)


def test_adapter_module_exposes_documented_family_inventory() -> None:
    assert ADAPTER_FAMILIES == (ADAPTER_FAMILY_INTERNAL_MAINTENANCE,)
    assert ADAPTER_FAMILY_INTERNAL_MAINTENANCE == "internal_maintenance"
    assert internal_maintenance.ADAPTER_GROUPS == (
        internal_maintenance.ADAPTER_GROUP_MAINTENANCE_TASK_MATERIALIZATION,
        internal_maintenance.ADAPTER_GROUP_ADMISSION_HANDSHAKE,
        internal_maintenance.ADAPTER_GROUP_EXECUTOR_RESULT_LINKAGE,
    )
