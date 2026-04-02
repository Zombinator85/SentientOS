from __future__ import annotations

import fnmatch
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

CORRIDOR_SCOPE_ID = "protected_mutation_proof:v1:covered_corridor"
CORRIDOR_VERSION = "2026-04-02.1"


@dataclass(frozen=True)
class CorridorDomain:
    name: str
    description: str
    path_globs: tuple[str, ...]
    artifact_classes: tuple[str, ...]
    action_kinds: tuple[str, ...]


CORRIDOR_DOMAINS: tuple[CorridorDomain, ...] = (
    CorridorDomain(
        name="genesisforge_lineage_proposal_adoption",
        description="GenesisForge lineage integration and proposal adoption protected mutation linkage.",
        path_globs=(
            "lineage/lineage.jsonl",
            "glow/control_plane/kernel_decisions.jsonl",
            "sentientos/**/genesis*forge*.py",
            "sentientos/**/forge*.py",
        ),
        artifact_classes=("lineage_entry", "kernel_decision"),
        action_kinds=("lineage_integrate", "proposal_adopt"),
    ),
    CorridorDomain(
        name="immutable_manifest_identity_writes",
        description="Immutable manifest generation and identity-affecting write linkage.",
        path_globs=(
            "vow/immutable_manifest.json",
            "glow/control_plane/kernel_decisions.jsonl",
            "scripts/generate_immutable_manifest.py",
            "scripts/emit_contract_status.py",
        ),
        artifact_classes=("immutable_manifest", "kernel_decision"),
        action_kinds=("generate_immutable_manifest",),
    ),
    CorridorDomain(
        name="quarantine_clear_privileged_operator_action",
        description="Quarantine clear privileged operator action linkage.",
        path_globs=(
            "pulse/forge_events.jsonl",
            "glow/control_plane/kernel_decisions.jsonl",
            "sentientos/**/quarantine*.py",
            "sentientos/**/operator*.py",
        ),
        artifact_classes=("forge_event_integrity_recovered", "forge_event_kernel_admission_denied", "kernel_decision"),
        action_kinds=("quarantine_clear",),
    ),
    CorridorDomain(
        name="codexhealer_repair_regenesis_linkage",
        description="CodexHealer repair/regenesis ledger linkage where integrated.",
        path_globs=(
            "glow/forge/recovery_ledger.jsonl",
            "glow/control_plane/kernel_decisions.jsonl",
            "sentientos/**/codex*healer*.py",
            "sentientos/**/repair*.py",
            "sentientos/**/regenesis*.py",
        ),
        artifact_classes=("recovery_ledger_kernel_admission", "kernel_decision"),
        action_kinds=(),
    ),
)


def corridor_definition() -> dict[str, Any]:
    return {
        "scope_id": CORRIDOR_SCOPE_ID,
        "corridor_version": CORRIDOR_VERSION,
        "domains": [
            {
                "name": domain.name,
                "description": domain.description,
                "path_globs": list(domain.path_globs),
                "artifact_classes": list(domain.artifact_classes),
                "action_kinds": list(domain.action_kinds),
            }
            for domain in CORRIDOR_DOMAINS
        ],
        "scope_note": "Narrow covered protected-mutation corridor only; explicit mapping, no whole-repo change-impact inference.",
    }


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def classify_touched_paths(paths: Sequence[str]) -> dict[str, Any]:
    normalized = [normalize_path(item) for item in paths if normalize_path(item)]
    implicated: dict[str, list[str]] = {}
    for item in normalized:
        for domain in CORRIDOR_DOMAINS:
            if any(fnmatch.fnmatch(item, pattern) for pattern in domain.path_globs):
                implicated.setdefault(domain.name, []).append(item)
    implicated_names = sorted(implicated)
    return {
        "touched_paths": sorted(set(normalized)),
        "intersects_corridor": bool(implicated_names),
        "implicated_domains": implicated_names,
        "matched_paths_by_domain": {name: sorted(set(matches)) for name, matches in sorted(implicated.items())},
    }


def is_corridor_path(path: str) -> bool:
    return bool(classify_touched_paths([path])["intersects_corridor"])


def is_corridor_artifact_class(artifact_class: str) -> bool:
    known = {item for domain in CORRIDOR_DOMAINS for item in domain.artifact_classes}
    return artifact_class in known


def _run_git_diff(repo_root: Path, cmd: list[str]) -> list[str]:
    proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return []
    return [normalize_path(line.strip()) for line in proc.stdout.splitlines() if line.strip()]


def discover_touched_paths(*, repo_root: Path, diff_base: str | None = None, explicit_paths: Sequence[str] | None = None) -> dict[str, Any]:
    if explicit_paths:
        return {
            "source": "explicit",
            "paths": sorted(set(normalize_path(item) for item in explicit_paths if normalize_path(item))),
        }

    if diff_base:
        paths = _run_git_diff(repo_root, ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", f"{diff_base}...HEAD"])
        return {"source": "git_diff_base", "diff_base": diff_base, "paths": sorted(set(paths))}

    working = _run_git_diff(repo_root, ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB"])
    if working:
        return {"source": "git_diff_working_tree", "paths": sorted(set(working))}

    cached = _run_git_diff(repo_root, ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMRTUXB"])
    return {"source": "git_diff_cached", "paths": sorted(set(cached))}
