from __future__ import annotations

import ast
import json
from fnmatch import fnmatch
from pathlib import Path

import pytest

pytestmark = pytest.mark.always_on_integrity

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "sentientos/system_closure/architecture_boundary_manifest.json"


def _manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _all_python_files() -> list[Path]:
    return [p for p in ROOT.rglob("*.py") if ".venv" not in p.parts and "__pycache__" not in p.parts]


def _is_legacy_surface(rel: str) -> bool:
    if "/" in rel:
        return False
    if rel.startswith(("test_", "setup")):
        return False
    blocked = ("control_plane", "task_", "ledger", "attestation", "presence_ledger", "relationship_log", "cathedral_const", "audit_chain", "intent_bundle")
    return not rel.startswith(blocked)


def _imports(path: Path) -> list[tuple[str, str | None]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: list[tuple[str, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, None))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                out.append((module, alias.name))
    return out


def _matches_known(manifest: dict[str, object], rule: str, rel: str, detail: str) -> bool:
    known = manifest["known_violations"]
    assert isinstance(known, list)
    for item in known:
        if item["rule"] == rule and item["file"] == rel and (item["detail"] in detail or detail in item["detail"]):
            return True
    return False


def test_manifest_schema_minimum_shape() -> None:
    manifest = _manifest()
    assert manifest["version"] == 1
    assert "layer_definitions" in manifest
    assert "protected_sinks" in manifest
    assert "known_violations" in manifest


def test_known_violations_are_unique_and_explicit() -> None:
    manifest = _manifest()
    seen: set[tuple[str, str]] = set()
    for row in manifest["known_violations"]:
        key = (row["rule"], row["file"])
        assert key not in seen, f"duplicate known violation entry: {key}"
        seen.add(key)
        assert row["severity"] in {"low", "medium", "high"}
        assert row["remediation"]


def test_expressive_world_dashboard_forbidden_imports_are_gated() -> None:
    manifest = _manifest()
    layer_defs = manifest["layer_definitions"]
    forbidden = set(layer_defs["expressive_apps"]["forbidden_import_patterns"])
    forbidden.update(layer_defs["world_adapters"]["forbidden_import_patterns"])
    forbidden.update(layer_defs["dashboards_views"]["forbidden_import_patterns"])

    violations: list[str] = []
    for path in _all_python_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(("tests/", "sentientos/tests/", "sentientos/")) or not _is_legacy_surface(rel):
            continue
        imports = _imports(path)
        for mod, symbol in imports:
            imp = f"{mod}.{symbol}" if symbol else mod
            for block in forbidden:
                if mod == block or mod.startswith(block) or imp == block:
                    detail = f"{imp} matches forbidden pattern {block}"
                    if not _matches_known(manifest, "expressive_forbidden_import", rel, detail) and not _matches_known(manifest, "world_forbidden_import", rel, detail) and not _matches_known(manifest, "dashboard_forbidden_import", rel, detail):
                        violations.append(f"{rel}: {detail}")
    if "expressive_forbidden_import" in manifest.get("inventory_mode_rules", []):
        assert violations
    else:
        assert not violations, "New expressive/world/dashboard boundary violations:\n" + "\n".join(sorted(violations))


def test_private_append_helpers_not_imported_by_expressive_modules() -> None:
    manifest = _manifest()
    violations: list[str] = []
    for path in _all_python_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(("tests/", "sentientos/tests/", "sentientos/")) or not _is_legacy_surface(rel):
            continue
        content = path.read_text(encoding="utf-8")
        bad = "from ledger import _append" in content or "ledger._append" in content
        if bad and not _matches_known(manifest, "expressive_private_import", rel, "ledger"):
            violations.append(rel)
    assert not violations, "New private append helper imports found: " + ", ".join(sorted(violations))


def test_formal_layers_do_not_import_symbolic_modules() -> None:
    manifest = _manifest()
    forbidden = manifest["layer_definitions"]["formal_core"]["forbidden_import_patterns"]
    violations: list[str] = []
    for path in _all_python_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel not in {"ledger.py", "audit_chain.py", "agent_privilege_policy_engine.py", "healing_sprint_ledger.py", "sentientos/formal_logging.py", "sentientos/integrity_metrics.py", "sentientos/presence_api.py"}:
            continue
        for mod, _ in _imports(path):
            for token in forbidden:
                if token in mod:
                    detail = f"imports symbolic module token {token} via {mod}"
                    if not _matches_known(manifest, "formal_symbolic_import", rel, detail):
                        violations.append(f"{rel}: {detail}")
    if "formal_symbolic_import" in manifest.get("inventory_mode_rules", []):
        assert violations
    else:
        assert not violations, "New formal->symbolic violations:\n" + "\n".join(sorted(violations))


def test_phase36_formal_modules_use_neutral_helpers() -> None:
    audit_text = (ROOT / "audit_chain.py").read_text(encoding="utf-8")
    assert "from sentientos.formal_logging import validate_log_entry" in audit_text
    assert "from cathedral_const import validate_log_entry" not in audit_text

    policy_text = (ROOT / "agent_privilege_policy_engine.py").read_text(encoding="utf-8")
    assert "from sentientos.formal_logging import log_json" in policy_text
    assert "from cathedral_const import log_json" not in policy_text

    sprint_text = (ROOT / "healing_sprint_ledger.py").read_text(encoding="utf-8")
    assert "from sentientos.integrity_metrics import gather_integrity_issues, parse_contributors" in sprint_text
    assert "from cathedral_wounds_dashboard import gather_integrity_issues, parse_contributors" not in sprint_text




def test_phase37_ledger_uses_neutral_formal_helpers() -> None:
    ledger_text = (ROOT / "ledger.py").read_text(encoding="utf-8")
    assert "from sentientos.formal_logging import PUBLIC_LOG, log_json" in ledger_text
    assert "from cathedral_const import PUBLIC_LOG, log_json" not in ledger_text
    assert "import presence_ledger" not in ledger_text
    assert "from sentientos.presence_api import recent_privilege_attempts" in ledger_text

    presence_api_text = (ROOT / "sentientos/presence_api.py").read_text(encoding="utf-8")
    assert "import presence_ledger" not in presence_api_text


def test_phase38_world_presence_modules_use_presence_facade() -> None:
    dashboard_text = (ROOT / "neos_presence_dashboard.py").read_text(encoding="utf-8")
    assert "import presence_ledger" not in dashboard_text
    assert "from sentientos.presence_api import append_presence_event, recent_privilege_attempts" in dashboard_text

    wizard_text = (ROOT / "resonite_guest_agent_consent_feedback_wizard.py").read_text(encoding="utf-8")
    assert "import presence_ledger" not in wizard_text
    assert "from sentientos.presence_api import append_presence_event" in wizard_text


def test_phase38_presence_api_remains_world_ui_neutral() -> None:
    text = (ROOT / "sentientos/presence_api.py").read_text(encoding="utf-8")
    assert "neos_" not in text
    assert "resonite_" not in text
    assert "dashboard" not in text

def test_autonomy_filenames_have_governance_annotation_or_allowlist() -> None:
    manifest = _manifest()
    policy = manifest["autonomy_naming_policy"]
    tokens = policy["filename_tokens"]
    markers = policy["annotation_markers"]
    approved = tuple(policy["approved_paths"])

    violations: list[str] = []
    for path in _all_python_files():
        rel = path.relative_to(ROOT).as_posix()
        lower = path.name.lower()
        if any(tok in lower for tok in tokens):
            if rel.startswith(approved) or "/" in rel:
                continue
            text = path.read_text(encoding="utf-8")
            if not any(marker in text for marker in markers):
                if not _matches_known(manifest, "autonomy_naming_missing_annotation", rel, "autonomy token"):
                    violations.append(rel)
    if "autonomy_naming_missing_annotation" in manifest.get("inventory_mode_rules", []):
        assert violations
    else:
        assert not violations, "New autonomy naming policy violations: " + ", ".join(sorted(violations))


def test_phase34_migrated_modules_use_public_ledger_facade() -> None:
    migrated = {
        "ritual_federation_importer.py": "append_audit_record",
        "blessing_recap_cli.py": "append_audit_record",
        "mood_wall.py": "append_audit_record",
    }
    for rel, marker in migrated.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "from sentientos.ledger_api import append_audit_record" in text
        assert marker in text


def test_phase34_migrated_modules_avoid_direct_append_writes_to_canonical_sinks() -> None:
    for rel in ("blessing_recap_cli.py", "mood_wall.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert '.open("a"' not in text
        assert "Path.write_text(" not in text or rel == "blessing_recap_cli.py"



def test_phase35_migrated_modules_use_public_control_facade() -> None:
    speech_text = (ROOT / "speech_to_avatar_bridge.py").read_text(encoding="utf-8")
    assert "from sentientos.control_api import require_authorization_for_request_types" in speech_text
    assert "from control_plane.enums" not in speech_text
    assert "from control_plane.records" not in speech_text

    patch_agent_text = (ROOT / "autonomous_self_patching_agent.py").read_text(encoding="utf-8")
    assert "from sentientos.control_api import require_self_patch_apply_authority" in patch_agent_text
    assert "import task_executor" not in patch_agent_text


def test_phase35_control_facade_public_contract_is_narrow() -> None:
    facade_text = (ROOT / "sentientos/control_api.py").read_text(encoding="utf-8")
    assert "__all__" in facade_text
    assert "AdmissionToken" not in facade_text
    assert "AuthorizationRecord" not in facade_text
    assert "def require_authorization_for_request_types" in facade_text
    assert "def require_self_patch_apply_authority" in facade_text


def test_phase39_ritual_cli_uses_ritual_facade() -> None:
    text = (ROOT / "ritual_cli.py").read_text(encoding="utf-8")
    assert "from sentientos.ritual_api import add_attestation, ritual_attestations_history, ritual_events_history" in text
    assert "import attestation" not in text
    assert "import relationship_log" not in text


def test_phase39_dashboard_and_mood_modules_use_dashboard_facade() -> None:
    emotion_text = (ROOT / "emotion_dashboard.py").read_text(encoding="utf-8")
    assert "from sentientos.dashboard_api import render_ledger_widget" in emotion_text
    assert "import ledger" not in emotion_text

    mood_text = (ROOT / "mood_wall.py").read_text(encoding="utf-8")
    assert "from sentientos.dashboard_api import log_mood_blessing" in mood_text
    assert "import ledger" not in mood_text


def test_phase39_new_facades_remain_narrow_and_presentation_neutral() -> None:
    ritual_api_text = (ROOT / "sentientos/ritual_api.py").read_text(encoding="utf-8")
    assert "__all__" in ritual_api_text
    assert "streamlit" not in ritual_api_text
    assert "dashboard" not in ritual_api_text

    dashboard_api_text = (ROOT / "sentientos/dashboard_api.py").read_text(encoding="utf-8")
    assert "__all__" in dashboard_api_text
    assert "relationship_log" not in dashboard_api_text
    assert "attestation" not in dashboard_api_text


def test_phase39_self_patching_agent_has_governance_annotation_markers() -> None:
    text = (ROOT / "autonomous_self_patching_agent.py").read_text(encoding="utf-8")
    for marker in (
        "GOVERNANCE_ANNOTATION",
        "ADMISSION_SURFACE",
        "CONSENT_BOUNDARY",
        "PROVENANCE_BOUNDARY",
        "SIMULATION_ONLY",
        "NON_SOVEREIGNTY",
    ):
        assert marker in text


def test_phase40_selected_approved_autonomy_files_have_parseable_annotations() -> None:
    required_markers = (
        "GOVERNANCE_ANNOTATION",
        "ADMISSION_SURFACE",
        "CONSENT_BOUNDARY",
        "PROVENANCE_BOUNDARY",
        "SIMULATION_ONLY",
        "NON_SOVEREIGNTY",
        "CALLER_TRIGGERED_OR_BOUNDED_RUNTIME",
    )
    for rel in (
        "daemon_autonomy_supervisor.py",
        "avatar_autonomous_ritual_scheduler.py",
        "agent_privilege_policy_engine.py",
        "sentientos/forge_daemon.py",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        for marker in required_markers:
            assert marker in text, f"{rel} missing {marker}"


def test_phase41_legacy_perception_modules_have_quarantine_annotations() -> None:
    required = [
        "LEGACY_PERCEPTION_QUARANTINE = True",
        "PERCEPTION_AUTHORITY = \"none\"",
        "RAW_RETENTION_DEFAULT = False",
        "CAN_TRIGGER_ACTIONS = ",
        "CAN_WRITE_MEMORY = ",
        "MIGRATION_TARGET = \"sentientos.perception_api\"",
        "NON_AUTHORITY_RATIONALE = ",
    ]
    for rel in ("screen_awareness.py", "mic_bridge.py", "vision_tracker.py", "multimodal_tracker.py", "feedback.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        for marker in required:
            assert marker in text, f"{rel} missing {marker}"


def test_phase45_ingress_gate_markers_visible_for_legacy_direct_effect_modules() -> None:
    mic_text = (ROOT / "mic_bridge.py").read_text(encoding="utf-8")
    assert "INGRESS_GATE_PRESENT = True" in mic_text
    assert "INGRESS_GATE_PROPOSAL_ONLY_SUPPORTED = True" in mic_text
    assert "LEGACY_DIRECT_MEMORY_WRITE_REQUIRES_EXPLICIT_MODE = True" in mic_text

    feedback_text = (ROOT / "feedback.py").read_text(encoding="utf-8")
    assert "INGRESS_GATE_PRESENT = True" in feedback_text
    assert "INGRESS_GATE_PROPOSAL_ONLY_SUPPORTED = True" in feedback_text
    assert "LEGACY_DIRECT_ACTION_REQUIRES_EXPLICIT_MODE = True" in feedback_text


def test_phase45_known_violations_remain_manifest_visible_for_direct_effect_risk() -> None:
    manifest = _manifest()
    rows = {row["file"]: row for row in manifest["known_violations"]}
    assert "mic_bridge.py" in rows
    assert "ingress gate mode" in rows["mic_bridge.py"]["detail"]
    assert "feedback.py" in rows
    assert "ingress gate mode" in rows["feedback.py"]["detail"]


def test_phase41_perception_api_boundary_purity() -> None:
    text = (ROOT / "sentientos/perception_api.py").read_text(encoding="utf-8")
    for bad in (
        "import screen_awareness",
        "import mic_bridge",
        "import vision_tracker",
        "import multimodal_tracker",
        "import feedback",
        "task_admission",
        "task_executor",
        "control_plane",
        "authority_surface",
    ):
        assert bad not in text


def test_phase42_legacy_perception_modules_are_bridged_and_marked() -> None:
    modules = {
        "screen_awareness.py": {"needs_action": False, "needs_memory": False},
        "mic_bridge.py": {"needs_action": False, "needs_memory": True},
        "vision_tracker.py": {"needs_action": False, "needs_memory": False},
        "multimodal_tracker.py": {"needs_action": False, "needs_memory": False},
        "feedback.py": {"needs_action": True, "needs_memory": False},
    }
    for rel, flags in modules.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "LEGACY_PERCEPTION_QUARANTINE = True" in text
        assert "PULSE_COMPATIBLE_TELEMETRY = True" in text
        assert "from sentientos.perception_api import" in text
        assert "emit_legacy_perception_telemetry" in text
        if flags["needs_action"]:
            assert "CAN_TRIGGER_ACTIONS = True" in text
        if flags["needs_memory"]:
            assert "CAN_WRITE_MEMORY = True" in text


def test_phase42_perception_api_import_purity_against_authority_surfaces() -> None:
    text = (ROOT / "sentientos/perception_api.py").read_text(encoding="utf-8")
    forbidden = [
        "task_admission",
        "task_executor",
        "control_plane",
        "authority_surface",
        "sentientos.introspection.spine",
    ]
    for token in forbidden:
        assert token not in text

def test_phase43_embodiment_fusion_forbidden_imports() -> None:
    manifest = _manifest()
    forbidden = set(manifest["layer_definitions"]["embodiment_fusion"]["forbidden_import_patterns"])
    path = ROOT / "sentientos/embodiment_fusion.py"
    violations: list[str] = []
    for mod, symbol in _imports(path):
        imp = f"{mod}.{symbol}" if symbol else mod
        for token in forbidden:
            if mod == token or mod.startswith(token) or imp == token:
                violations.append(f"{imp} matches forbidden pattern {token}")
    assert not violations, "Embodiment fusion forbidden imports found: " + "; ".join(sorted(violations))


def test_phase43_embodiment_fusion_manifest_contract() -> None:
    manifest = _manifest()
    layer = manifest["layer_definitions"]["embodiment_fusion"]
    assert layer["classification"] == "canonical_derived_fusion"
    assert layer["derived_only"] is True
    assert layer["non_authoritative"] is True
    assert layer["no_direct_hardware_access"] is True
    assert layer["no_direct_memory_write"] is True
    assert layer["no_action_trigger"] is True

def test_phase44_embodiment_ingress_manifest_and_import_boundaries() -> None:
    manifest = _manifest()
    layer = manifest["layer_definitions"]["embodiment_ingress"]
    assert layer["proposal_only"] is True
    assert layer["non_authoritative"] is True
    assert layer["no_direct_memory_write"] is True
    text = (ROOT / "sentientos/embodiment_ingress.py").read_text(encoding="utf-8")
    banned = [
        "import task_executor",
        "import task_admission",
        "import control_plane",
        "import memory_manager",
        "import mic_bridge",
        "import feedback",
        "import vision_tracker",
        "import multimodal_tracker",
        "import screen_awareness",
    ]
    for marker in banned:
        assert marker not in text


def test_phase44_no_new_direct_sink_mutation_in_perception_fusion_ingress() -> None:
    for rel in [
        "sentientos/embodiment_fusion.py",
        "sentientos/embodiment_ingress.py",
        "sentientos/perception_api.py",
    ]:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "append_memory(" not in text
        assert "task_executor" not in text
        assert "task_admission" not in text


def test_phase46_retention_gate_markers_visible_for_legacy_retention_modules() -> None:
    for rel in ("screen_awareness.py", "vision_tracker.py", "multimodal_tracker.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "EMBODIMENT_RETENTION_GATE_PRESENT = True" in text
        assert "EMBODIMENT_RETENTION_GATE_DEFAULT_MODE = \"compatibility_legacy\"" in text
        assert "EMBODIMENT_RETENTION_GATE_PROPOSAL_ONLY_SUPPORTED = True" in text
        assert "LEGACY_DIRECT_RETENTION_REQUIRES_EXPLICIT_MODE = True" in text


def test_phase46_known_violations_manifest_visibility_for_retention_gates() -> None:
    rows = {row["file"]: row for row in _manifest()["known_violations"]}
    for rel in ("screen_awareness.py", "vision_tracker.py", "multimodal_tracker.py"):
        assert rel in rows
        assert "retention gate mode" in rows[rel]["detail"]
        assert "proposal_only" in rows[rel]["detail"]

def test_phase47_legacy_modules_use_centralized_gate_policy() -> None:
    for rel in ("mic_bridge.py", "feedback.py", "screen_awareness.py", "vision_tracker.py", "multimodal_tracker.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "resolve_embodiment_gate_mode" in text


def test_phase47_manifest_mentions_gate_modes_for_legacy_modules() -> None:
    manifest = _manifest()
    rows = {row["file"]: row for row in manifest["known_violations"] if row["rule"] == "legacy_perception_quarantine"}
    for rel in ("mic_bridge.py", "feedback.py", "screen_awareness.py", "vision_tracker.py", "multimodal_tracker.py"):
        detail = rows[rel]["detail"]
        assert "proposal_only" in detail
        assert "compatibility_legacy" in detail

def test_phase48_embodiment_proposals_layer_declared_and_non_authoritative() -> None:
    manifest = _manifest()
    layer = manifest["layer_definitions"]["embodiment_proposals"]
    assert layer["append_only"] is True
    assert layer["non_authoritative"] is True
    assert layer["no_admission_execution"] is True


def test_phase48_embodiment_proposals_import_boundary() -> None:
    text = (ROOT / "sentientos/embodiment_proposals.py").read_text(encoding="utf-8")
    for forbidden in ("task_executor", "task_admission", "control_plane", "authority_surface", "memory_manager", "mic_bridge", "vision_tracker", "screen_awareness", "multimodal_tracker"):
        assert forbidden not in text


def test_phase48_legacy_modules_wire_proposal_recording() -> None:
    for rel in ("mic_bridge.py", "feedback.py", "screen_awareness.py", "vision_tracker.py", "multimodal_tracker.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "record_blocked_embodiment_effect" in text


def test_phase48_manifest_known_violations_include_proposal_visibility() -> None:
    manifest = _manifest()
    rows = {r["file"]: r for r in manifest["known_violations"]}
    for rel in ("mic_bridge.py", "feedback.py", "screen_awareness.py", "vision_tracker.py", "multimodal_tracker.py"):
        assert "proposal_only now records blocked-effect proposals" in rows[rel]["detail"]


def test_phase49_manifest_declares_embodiment_proposal_diagnostic_non_authoritative() -> None:
    manifest = _manifest()
    layer = manifest["layer_definitions"]["embodiment_proposal_diagnostic"]
    assert layer["read_only"] is True
    assert layer["summary_only"] is True
    assert layer["non_authoritative"] is True
    assert layer["no_proposal_mutation"] is True
    assert layer["no_admission_execution"] is True


def test_phase49_embodiment_proposal_diagnostic_forbidden_imports() -> None:
    manifest = _manifest()
    layer = manifest["layer_definitions"]["embodiment_proposal_diagnostic"]
    text = (ROOT / "sentientos/embodiment_proposal_diagnostic.py").read_text(encoding="utf-8")
    for pattern in layer["forbidden_import_patterns"]:
        assert f"import {pattern}" not in text
        assert f"from {pattern} import" not in text


def test_phase49_scoped_lifecycle_diagnostic_does_not_mutate_or_execute_proposals() -> None:
    text = (ROOT / "sentientos/scoped_lifecycle_diagnostic.py").read_text(encoding="utf-8")
    assert "build_embodied_proposal_review_summary" in text
    assert "append_embodied_proposal" not in text
    assert "record_blocked_embodiment_effect" not in text
    assert "task_executor" not in text

def test_phase50_review_module_manifest_and_invariants() -> None:
    manifest = _manifest()
    layer = manifest["layer_definitions"]["embodiment_proposal_review"]
    assert layer["append_only"] is True
    assert layer["non_authoritative"] is True
    assert layer["approval_is_not_execution"] is True


def test_phase50_review_module_forbidden_imports_and_semantics() -> None:
    path = ROOT / "sentientos/embodiment_proposal_review.py"
    imports = _imports(path)
    forbidden_tokens = [
        "task_executor",
        "task_admission",
        "control_plane",
        "sentientos.authority_surface",
        "memory_manager",
        "feedback",
        "sentientos.perception_api",
    ]
    for mod, symbol in imports:
        imp = f"{mod}.{symbol}" if symbol else mod
        for token in forbidden_tokens:
            assert not (mod == token or mod.startswith(token) or imp == token)
    text = path.read_text(encoding="utf-8")
    assert '"approval_is_not_execution": True' in text
    assert '"decision_power": "none"' in text

def test_phase51_handoff_and_bridge_import_boundaries_and_manifest_invariants() -> None:
    handoff_text = (ROOT / "sentientos/embodiment_proposal_handoff.py").read_text(encoding="utf-8")
    bridge_text = (ROOT / "sentientos/embodiment_governance_bridge.py").read_text(encoding="utf-8")
    banned = ["task_executor", "task_admission", "control_plane", "authority_surface", "screen_awareness", "mic_bridge", "vision_tracker"]
    for token in banned:
        assert token not in handoff_text
        assert token not in bridge_text

    manifest = _manifest()
    handoff = manifest["layer_definitions"]["embodiment_proposal_handoff"]
    bridge = manifest["layer_definitions"]["embodiment_governance_bridge"]
    assert "handoff_is_not_fulfillment" in handoff["invariants"]
    assert "bridge_is_not_admission" in bridge["invariants"]


def test_phase51_candidate_output_invariants() -> None:
    from sentientos.embodiment_proposal_handoff import build_embodied_handoff_candidate
    from sentientos.embodiment_governance_bridge import build_embodied_governance_bridge_candidate

    proposal = {"proposal_id": "p1", "proposal_kind": "memory_ingress_candidate", "source_module": "x"}
    review = {"proposal_id": "p1", "review_outcome": "reviewed_approved_for_next_stage", "review_receipt_id": "r1"}
    handoff = build_embodied_handoff_candidate(proposal_record=proposal, review_receipt=review)
    assert handoff["approval_is_not_execution"] is True
    assert handoff["handoff_is_not_fulfillment"] is True
    bridge = build_embodied_governance_bridge_candidate(handoff_candidate=handoff)
    assert bridge["bridge_is_not_admission"] is True

def test_phase52_fulfillment_manifest_invariants_declared() -> None:
    manifest = _manifest()
    layer = manifest["layer_definitions"]["embodiment_fulfillment"]
    assert layer["candidate_receipt_only"] is True
    assert layer["non_authoritative"] is True
    assert layer["append_only_receipts"] is True
    assert layer["fulfillment_candidate_is_not_effect"] is True
    assert layer["fulfillment_receipt_is_not_effect"] is True


def test_phase52_fulfillment_module_forbidden_imports_not_present() -> None:
    text = (ROOT / "sentientos/embodiment_fulfillment.py").read_text(encoding="utf-8")
    forbidden = [
        "task_executor",
        "task_admission",
        "control_plane",
        "sentientos.authority_surface",
        "memory_manager",
        "screen_awareness",
        "vision_tracker",
        "multimodal_tracker",
    ]
    for token in forbidden:
        assert token not in text


def test_phase52_fulfillment_candidate_and_receipt_non_effect_markers() -> None:
    from sentientos.embodiment_fulfillment import build_embodied_fulfillment_candidate, build_embodied_fulfillment_receipt

    candidate = build_embodied_fulfillment_candidate(
        governance_bridge_candidate={
            "governance_bridge_candidate_id": "g1",
            "governance_bridge_candidate_kind": "memory_governance_review_candidate",
            "bridge_posture": "eligible_for_governance_review",
            "source_handoff_candidate_ref": "handoff_candidate:h1",
        },
        created_at=1.0,
    )
    receipt = build_embodied_fulfillment_receipt(
        fulfillment_candidate=candidate,
        fulfillment_outcome="fulfilled_external_manual",
        fulfiller_kind="test_fixture",
        created_at=2.0,
    )
    assert candidate["fulfillment_candidate_is_not_effect"] is True
    assert receipt["fulfillment_receipt_is_not_effect"] is True
    assert receipt["receipt_does_not_prove_side_effect"] is True

def test_phase53_memory_ingress_manifest_invariants_declared() -> None:
    manifest = _manifest()
    layer = manifest["layer_definitions"]["embodiment_memory_ingress"]
    assert layer["validation_only"] is True
    assert layer["non_authoritative"] is True
    assert layer["validation_is_not_memory_write"] is True
    assert layer["no_direct_memory_write"] is True
    assert layer["no_admission_execution"] is True
    assert layer["no_control_plane_mutation"] is True
    assert layer["no_feedback_trigger"] is True
    assert layer["no_retention_commit"] is True


def test_phase53_memory_ingress_module_forbidden_imports_and_non_effect_flags() -> None:
    path = ROOT / "sentientos/embodiment_memory_ingress.py"
    text = path.read_text(encoding="utf-8")
    imports = _imports(path)
    for forbidden in (
        "task_executor",
        "task_admission",
        "control_plane",
        "sentientos.authority_surface",
        "memory_manager",
        "feedback",
        "screen_awareness",
        "vision_tracker",
        "multimodal_tracker",
        "sentientos.perception_api",
    ):
        assert not any(mod == forbidden or mod.startswith(f"{forbidden}.") for mod, _ in imports)

    assert '"validation_is_not_memory_write": True' in text
    assert '"does_not_write_memory": True' in text
    assert '"does_not_trigger_feedback": True' in text
    assert '"does_not_admit_work": True' in text
    assert '"does_not_execute_or_route_work": True' in text

def test_phase54_action_ingress_module_import_boundaries() -> None:
    text = (ROOT / "sentientos/embodiment_action_ingress.py").read_text(encoding="utf-8")
    assert "import task_executor" not in text
    assert "import task_admission" not in text
    assert "import control_plane" not in text
    assert "import feedback" not in text
    assert "memory_manager" not in text


def test_phase54_manifest_declares_action_ingress_invariants() -> None:
    manifest = _manifest()
    layer = manifest["layer_definitions"]["embodiment_action_ingress"]
    assert layer["validation_only"] is True
    assert layer["non_authoritative"] is True
    assert layer["no_feedback_trigger"] is True
    assert layer["no_action_execution"] is True
    assert layer["no_task_admission"] is True
    assert layer["no_execution"] is True
    assert layer["no_control_plane_mutation"] is True
    assert layer["no_memory_write"] is True
    assert layer["no_retention_commit"] is True
    assert layer["validation_is_not_action_trigger"] is True


def test_phase54_action_validation_output_non_effect_markers() -> None:
    from sentientos.embodiment_action_ingress import build_action_ingress_validation_record

    row = build_action_ingress_validation_record(feedback_action_fulfillment_candidate={
        "fulfillment_candidate_id": "efc_x",
        "fulfillment_candidate_kind": "feedback_action_fulfillment_candidate",
        "source_governance_bridge_candidate_ref": "governance_bridge_candidate:g1",
        "source_handoff_candidate_ref": "handoff_candidate:h1",
        "source_proposal_id": "p1",
        "source_review_receipt_id": "r1",
        "consent_posture": "granted",
        "risk_flags": {},
        "candidate_payload_summary": {},
    })
    assert row["validation_is_not_action_trigger"] is True
    assert row["does_not_trigger_feedback"] is True
