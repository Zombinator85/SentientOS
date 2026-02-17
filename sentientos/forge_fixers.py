"""Deterministic fix candidate generation and application."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from sentientos.forge_failures import FailureCluster


@dataclass(slots=True)
class FixCandidate:
    id: str
    description: str
    files_touched: list[str]
    command_plan: list[str]
    confidence: float
    risk: str


@dataclass(slots=True)
class FixResult:
    candidate_id: str
    applied: bool
    notes: str
    files_changed: list[str]


@dataclass(slots=True)
class _EditPlan:
    path: Path
    content: str


def generate_fix_candidates(clusters: list[FailureCluster], repo_root: Path) -> list[FixCandidate]:
    candidates: list[FixCandidate] = []
    for cluster in clusters:
        sig = cluster.signature
        if not sig.file:
            continue
        path = repo_root / sig.file
        if not path.exists() or path.suffix != ".py":
            continue
        text = path.read_text(encoding="utf-8")
        message = (cluster.examples[0] if cluster.examples else "").lower()
        error_type = sig.error_type.lower()

        if "fixture" in message and "not found" in message:
            candidates.append(
                FixCandidate(
                    id=f"fix_fixture_{sig.message_digest}",
                    description=f"Add minimal fixture for {sig.test_name}",
                    files_touched=[sig.file],
                    command_plan=["inject fixture alias in test module"],
                    confidence=0.55,
                    risk="low",
                )
            )
        if "moduleNotFound".lower() in error_type or "modulenotfound" in message:
            candidates.append(
                FixCandidate(
                    id=f"fix_import_{sig.message_digest}",
                    description=f"Normalize moved import in {sig.file}",
                    files_touched=[sig.file],
                    command_plan=["rewrite stale import path"],
                    confidence=0.7,
                    risk="low",
                )
            )
        if "assert" in error_type and "\\" in message and "/" in message:
            candidates.append(
                FixCandidate(
                    id=f"fix_pathsep_{sig.message_digest}",
                    description=f"Use pathlib/as_posix tolerant assertion in {sig.file}",
                    files_touched=[sig.file],
                    command_plan=["normalize path separators in assertion"],
                    confidence=0.65,
                    risk="low",
                )
            )
        if "random" in message or "flaky" in message:
            candidates.append(
                FixCandidate(
                    id=f"fix_random_seed_{sig.message_digest}",
                    description="Seed random for deterministic test behavior",
                    files_touched=[sig.file],
                    command_plan=["insert random.seed(0) in failing test"],
                    confidence=0.6,
                    risk="low",
                )
            )
        if "datetime" in message or "timestamp" in message or "time" in message:
            candidates.append(
                FixCandidate(
                    id=f"fix_time_{sig.message_digest}",
                    description="Stabilize time-dependent assertion with fixed timestamp",
                    files_touched=[sig.file],
                    command_plan=["replace dynamic now()/time() in assertion with fixed constant"],
                    confidence=0.5,
                    risk="medium",
                )
            )
        if "cwd" in message or "working directory" in message or "no such file or directory" in message:
            candidates.append(
                FixCandidate(
                    id=f"fix_cwd_{sig.message_digest}",
                    description="Swap cwd-dependent path usage to tmp_path",
                    files_touched=[sig.file],
                    command_plan=["replace Path.cwd() usage in test with tmp_path"],
                    confidence=0.55,
                    risk="medium",
                )
            )
        if "snapshot" in message and "update" in message:
            candidates.append(
                FixCandidate(
                    id=f"fix_snapshot_flag_{sig.message_digest}",
                    description="Respect explicit snapshot update flags without auto-accept",
                    files_touched=[sig.file],
                    command_plan=["wire update flag usage in test helper"],
                    confidence=0.45,
                    risk="medium",
                )
            )
        if "fixture" in message and "mismatch" in message:
            candidates.append(
                FixCandidate(
                    id=f"fix_fixture_name_{sig.message_digest}",
                    description="Correct fixture name mismatch in parametrized test",
                    files_touched=[sig.file],
                    command_plan=["rename fixture usage to available fixture"],
                    confidence=0.5,
                    risk="medium",
                )
            )

        if "tmp_path" not in text and "Path.cwd()" in text:
            candidates.append(
                FixCandidate(
                    id=f"fix_tmp_path_{sig.message_digest}",
                    description="Introduce tmp_path based isolation for file operations",
                    files_touched=[sig.file],
                    command_plan=["use tmp_path fixture for local file creation"],
                    confidence=0.4,
                    risk="medium",
                )
            )
    return sorted(candidates, key=lambda c: (c.risk != "low", -c.confidence))


def apply_fix_candidate(candidate: FixCandidate, repo_root: Path) -> FixResult:
    changed: list[str] = []
    notes = "no-op"
    for rel_path in candidate.files_touched:
        file_path = repo_root / rel_path
        if not file_path.exists() or file_path.suffix != ".py":
            continue
        original = file_path.read_text(encoding="utf-8")
        edited = _apply_heuristic_rewrite(original, candidate)
        if edited != original:
            file_path.write_text(edited, encoding="utf-8")
            changed.append(rel_path)
    if changed:
        notes = "applied textual rewrite"
    return FixResult(candidate_id=candidate.id, applied=bool(changed), notes=notes, files_changed=changed)


def _apply_heuristic_rewrite(content: str, candidate: FixCandidate) -> str:
    updated = content
    if candidate.id.startswith("fix_pathsep_"):
        updated = updated.replace("\\\\", "/")
    if candidate.id.startswith("fix_random_seed_") and "random.seed(" not in updated:
        if "import random" in updated:
            updated = updated.replace("import random", "import random\nrandom.seed(0)", 1)
        else:
            updated = "import random\nrandom.seed(0)\n" + updated
    if candidate.id.startswith("fix_tmp_path_") and "Path.cwd()" in updated:
        updated = updated.replace("Path.cwd()", "tmp_path")
    if candidate.id.startswith("fix_cwd_") and "cwd=" in updated:
        updated = re.sub(r"cwd\s*=\s*Path\.cwd\(\)", "cwd=tmp_path", updated)
    if candidate.id.startswith("fix_import_"):
        updated = updated.replace("from sentientos import ", "from sentientos.core import ")
    if candidate.id.startswith("fix_time_"):
        updated = updated.replace("datetime.now()", "datetime(2024, 1, 1)")
    return updated
