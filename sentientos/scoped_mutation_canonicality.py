from __future__ import annotations

from pathlib import Path
from typing import Any


def build_scoped_canonicality_map() -> list[dict[str, str]]:
    return [
        {
            "action_id": "sentientos.manifest.generate",
            "entrypoint": "scripts.generate_immutable_manifest.main/execute_manifest_generation_action",
            "handler": "scripts.generate_immutable_manifest.generate_manifest",
            "direct_internal_helpers": "scripts.generate_immutable_manifest.generate_manifest",
            "status": "canonical_through_router",
        },
        {
            "action_id": "sentientos.quarantine.clear",
            "entrypoint": "scripts.quarantine_clear.main",
            "handler": "sentientos.integrity_quarantine.clear",
            "direct_internal_helpers": "sentientos.integrity_quarantine.clear",
            "status": "canonical_through_router",
        },
        {
            "action_id": "sentientos.genesis.lineage_integrate",
            "entrypoint": "sentientos.genesis_forge.GenesisForge.expand",
            "handler": "sentientos.genesis_forge.SpecBinder.integrate",
            "direct_internal_helpers": "SpecBinder.integrate",
            "status": "canonical_through_router",
        },
        {
            "action_id": "sentientos.genesis.proposal_adopt",
            "entrypoint": "sentientos.genesis_forge.GenesisForge.expand",
            "handler": "sentientos.genesis_forge.AdoptionRite.promote",
            "direct_internal_helpers": "AdoptionRite.promote",
            "status": "canonical_through_router",
        },
        {
            "action_id": "sentientos.codexhealer.repair",
            "entrypoint": "sentientos.codex_healer.CodexHealer.auto_repair",
            "handler": "sentientos.codex_healer.RepairSynthesizer.apply",
            "direct_internal_helpers": "RepairSynthesizer.apply",
            "status": "canonical_through_router",
        },
        {
            "action_id": "sentientos.merge_train.hold",
            "entrypoint": "sentientos.forge_merge_train.ForgeMergeTrain.hold",
            "handler": "sentientos.forge_merge_train.ForgeMergeTrain._apply_hold_transition",
            "direct_internal_helpers": "_apply_hold_transition (guarded non-canonical)",
            "status": "canonical_through_router",
        },
        {
            "action_id": "sentientos.merge_train.release",
            "entrypoint": "sentientos.forge_merge_train.ForgeMergeTrain.release",
            "handler": "sentientos.forge_merge_train.ForgeMergeTrain._apply_release_transition",
            "direct_internal_helpers": "_apply_release_transition (guarded non-canonical)",
            "status": "canonical_through_router",
        },
    ]


def evaluate_scoped_slice_non_canonical_paths(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    checks: list[dict[str, Any]] = []

    def _read(rel: str) -> str:
        path = root / rel
        return path.read_text(encoding="utf-8") if path.exists() else ""

    manifest_script = _read("scripts/generate_immutable_manifest.py")
    checks.append(
        {
            "check": "manifest_writer_requires_router_provenance",
            "status": "ok"
            if "non_canonical_mutation_path:sentientos.manifest.generate" in manifest_script
            else "violation",
            "surface": "scripts/generate_immutable_manifest.py",
        }
    )

    for surface in ("sentientos/node_operations.py", "sentientos/vow_artifacts.py"):
        code = _read(surface)
        checks.append(
            {
                "check": f"{surface}:no_direct_manifest_generate",
                "status": "violation" if "generate_manifest(output=" in code else "ok",
                "surface": surface,
            }
        )
        checks.append(
            {
                "check": f"{surface}:routes_manifest_via_typed_action",
                "status": "ok" if "execute_manifest_generation_action(" in code else "violation",
                "surface": surface,
            }
        )

    merge_train = _read("sentientos/forge_merge_train.py")
    checks.append(
        {
            "check": "merge_train_transitions_guarded_from_direct_calls",
            "status": "ok"
            if "non_canonical_mutation_path:sentientos.merge_train.hold" in merge_train
            and "non_canonical_mutation_path:sentientos.merge_train.release" in merge_train
            else "violation",
            "surface": "sentientos/forge_merge_train.py",
        }
    )

    registry_payload = _read("glow/contracts/constitutional_execution_fabric_scoped_slice.json")
    for action_id in (
        "sentientos.manifest.generate",
        "sentientos.quarantine.clear",
        "sentientos.genesis.lineage_integrate",
        "sentientos.genesis.proposal_adopt",
        "sentientos.codexhealer.repair",
        "sentientos.merge_train.hold",
        "sentientos.merge_train.release",
    ):
        checks.append(
            {
                "check": f"registry_entry_present:{action_id}",
                "status": "ok" if action_id in registry_payload else "violation",
                "surface": "glow/contracts/constitutional_execution_fabric_scoped_slice.json",
            }
        )

    violations = [row for row in checks if row["status"] != "ok"]
    return {
        "scope": "constitutional_execution_fabric_scoped_slice",
        "status": "ok" if not violations else "violation",
        "checks": checks,
        "violations": violations,
    }
