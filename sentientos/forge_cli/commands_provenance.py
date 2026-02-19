from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from sentientos.github_checks import PRChecks, fetch_pr_checks, wait_for_pr_checks
from sentientos.forge_replay import replay_provenance

from .context import ForgeContext
from .types import load_json_dict, print_json, truncate_large_fields


@dataclass(frozen=True)
class TargetArgs:
    target: str


@dataclass(frozen=True)
class ReplayArgs:
    target: str
    dry_run: bool


@dataclass(frozen=True)
class WaitArgs:
    target: str
    timeout: int


def _resolve_artifact_path(context: ForgeContext, target: str, *, kind: str) -> Path:
    if target.endswith('.json'):
        path = Path(target)
    else:
        suffix = target.replace(':', '-')
        prefix = 'report' if kind == 'report' else ('docket' if kind == 'docket' else 'quarantine')
        path = context.forge.forge_dir / f"{prefix}_{suffix}.json"
    if not path.is_absolute():
        path = context.forge.repo_root / path
    return path


def handle_show_artifact(context: ForgeContext, args: TargetArgs, *, kind: str) -> int:
    path = _resolve_artifact_path(context, args.target, kind=kind)
    payload = load_json_dict(path)
    if not payload:
        print_json({"error": f"unreadable {kind}", "path": str(path)})
        return 0
    print_json(truncate_large_fields(payload), indent=2)
    return 0


def handle_replay(context: ForgeContext, args: ReplayArgs) -> int:
    replay_path = replay_provenance(args.target, repo_root=context.forge.repo_root, dry_run=args.dry_run)
    print_json({"command": "replay", "target": args.target, "dry_run": args.dry_run, "report_path": str(replay_path)})
    return 0


def _checks_for_target(target: str) -> PRChecks:
    if target.isdigit():
        return fetch_pr_checks(pr_number=int(target))
    return fetch_pr_checks(pr_url=target)


def handle_pr_checks(_context: ForgeContext, args: TargetArgs) -> int:
    checks = _checks_for_target(args.target)
    print_json({"command": "pr-checks", "pr": asdict(checks.pr), "overall": checks.overall, "checks": [asdict(item) for item in checks.checks]}, indent=2)
    return 0


def handle_wait_checks(_context: ForgeContext, args: WaitArgs) -> int:
    checks = _checks_for_target(args.target)
    final, timing = wait_for_pr_checks(checks.pr, timeout_seconds=max(1, args.timeout), poll_interval_seconds=20)
    print_json({"command": "wait-checks", "pr": asdict(final.pr), "overall": final.overall, "timing": timing, "checks": [asdict(item) for item in final.checks]}, indent=2)
    return 0 if final.overall == "success" else 1
