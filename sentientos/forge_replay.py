"""Deterministic-ish replay from Forge provenance bundles."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from sentientos.cathedral_forge import CathedralForge
from sentientos.forge_env import bootstrap_env
from sentientos.forge_model import CommandSpec
from sentientos.forge_provenance import PROVENANCE_DIR, ProvenanceStep, load_bundle


@dataclass(slots=True)
class ReplayStepResult:
    step_id: str
    kind: str
    executed: bool
    matched_stdout: bool | None
    matched_stderr: bool | None
    exit_code: int | None
    notes: str


@dataclass(slots=True)
class ReplayReport:
    source_run_id: str
    replayed_at: str
    dry_run: bool
    env_cache_key_expected: str
    env_cache_key_actual: str
    matched_env_cache_key: bool
    steps: list[ReplayStepResult]


def replay_provenance(target: str, *, repo_root: Path, dry_run: bool = False) -> Path:
    root = repo_root.resolve()
    bundle = load_bundle(root, target)
    forge = CathedralForge(repo_root=root)
    session = forge._create_session(_iso_now())
    forge_env = bootstrap_env(Path(session.root_path))

    old_root = _first_step_cwd(bundle.steps)
    report_steps: list[ReplayStepResult] = []

    for step in bundle.steps:
        if step.kind not in {"preflight", "apply", "tests"}:
            continue
        command_argv = _command_argv(step)
        if not command_argv:
            report_steps.append(ReplayStepResult(step_id=step.step_id, kind=step.kind, executed=False, matched_stdout=None, matched_stderr=None, exit_code=None, notes="missing argv"))
            continue
        cwd = _map_cwd(step.cwd, old_root, Path(session.root_path))
        if dry_run:
            report_steps.append(ReplayStepResult(step_id=step.step_id, kind=step.kind, executed=False, matched_stdout=None, matched_stderr=None, exit_code=None, notes=f"dry-run: {' '.join(command_argv)} @ {cwd}"))
            continue
        result = forge._run_step(
            command=CommandSpec(step=step.step_id, argv=command_argv, timeout_seconds=600),
            cwd=cwd,
        )
        report_steps.append(
            ReplayStepResult(
                step_id=step.step_id,
                kind=step.kind,
                executed=True,
                matched_stdout=_digest(result.stdout) == step.stdout_digest,
                matched_stderr=_digest(result.stderr) == step.stderr_digest,
                exit_code=result.returncode,
                notes="",
            )
        )

    report = ReplayReport(
        source_run_id=bundle.header.run_id,
        replayed_at=_iso_now(),
        dry_run=dry_run,
        env_cache_key_expected=bundle.env_cache_key,
        env_cache_key_actual=forge_env.cache_key,
        matched_env_cache_key=forge_env.cache_key == bundle.env_cache_key,
        steps=report_steps,
    )
    stamp = _safe(_iso_now())
    out = root / PROVENANCE_DIR / f"replay_{bundle.header.run_id}_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def _command_argv(step: ProvenanceStep) -> list[str]:
    argv = step.command.get("argv")
    if isinstance(argv, list):
        return [str(item) for item in argv]
    return []


def _first_step_cwd(steps: list[ProvenanceStep]) -> Path | None:
    for step in steps:
        if step.kind in {"preflight", "apply", "tests"}:
            return Path(step.cwd)
    return None


def _map_cwd(recorded: str, old_root: Path | None, new_root: Path) -> Path:
    rec = Path(recorded)
    if old_root is None:
        return new_root
    try:
        rel = rec.relative_to(old_root)
        return new_root / rel
    except ValueError:
        return new_root


def _digest(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe(value: str) -> str:
    return value.replace(":", "-")
