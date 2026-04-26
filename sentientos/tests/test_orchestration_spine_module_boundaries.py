from __future__ import annotations

from sentientos import orchestration_internal_adapters
from sentientos import orchestration_projection_policy
from sentientos.orchestration_spine.adapters import internal_maintenance
from sentientos.orchestration_spine.projection import (
    PROJECTION_FAMILIES,
    PROJECTION_FAMILY_CURRENT_STATE,
    PROJECTION_FAMILY_POLICY,
    current_state,
    policy_helpers,
)


def test_projection_policy_compatibility_shim_exports_same_callable() -> None:
    assert orchestration_projection_policy.derive_attention_projection is policy_helpers.derive_attention_projection


def test_internal_adapter_compatibility_shim_exports_same_callable() -> None:
    assert orchestration_internal_adapters.build_internal_maintenance_task is internal_maintenance.build_internal_maintenance_task


def test_projection_module_exposes_documented_family_inventory() -> None:
    assert PROJECTION_FAMILIES == (PROJECTION_FAMILY_CURRENT_STATE, PROJECTION_FAMILY_POLICY)
    assert PROJECTION_FAMILY_CURRENT_STATE == "current_state"
    assert PROJECTION_FAMILY_POLICY == "policy"
    assert "resolve_current_orchestration_digest" in current_state.CURRENT_STATE_PROJECTION_FAMILY_PICTURE_COMPRESSION
    assert "derive_next_venue_projection" in policy_helpers.POLICY_PROJECTION_FAMILY_RECOMMENDATION
