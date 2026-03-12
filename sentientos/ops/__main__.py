from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Sequence

from scripts.cli_common import emit_payload, exit_code
from sentientos.attestation import read_json
from sentientos.node_operations import build_incident_bundle, node_health, run_bootstrap
from sentientos.system_constitution import (
    SYSTEM_CONSTITUTION_REL,
    compose_system_constitution,
    verify_constitution,
    write_constitution_artifacts,
)


def _status_from_payload(payload: dict[str, object]) -> str:
    for key in ("health_state", "constitution_state", "status"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    ok = payload.get("ok")
    if isinstance(ok, bool):
        return "passed" if ok else "failed"
    return "unknown"


def _decorate_payload(payload: dict[str, object], *, domain: str, action: str) -> dict[str, object]:
    decorated = dict(payload)
    decorated.setdefault("surface", "sentientos.ops")
    decorated.setdefault("command", f"{domain}.{action}")
    decorated.setdefault("status", _status_from_payload(payload))
    decorated.setdefault("exit_code", exit_code(payload))
    return decorated


def _resolve_repo_root(repo_root: str | None) -> Path:
    if repo_root is None:
        return Path.cwd().resolve()
    return Path(repo_root).resolve()


def _latest_constitution(root: Path) -> dict[str, object]:
    payload = read_json(root / SYSTEM_CONSTITUTION_REL)
    return payload if payload else compose_system_constitution(root)


def _with_repo_flag(argv: list[str], repo_root: Path | None) -> list[str]:
    if repo_root is None:
        return argv
    return argv + ["--repo-root", str(repo_root)]


def _normalize_passthrough(values: list[str]) -> list[str]:
    return [value for value in values if value != "--"]


def build_parser(*, prog: str = "python -m sentientos.ops") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Unified SentientOS operations command surface",
        epilog=(
            "Workflow examples:\n"
            "  python -m sentientos.ops node health --json\n"
            "  python -m sentientos.ops constitution verify --json\n"
            "  python -m sentientos.ops audit verify -- --strict\n"
            "  python -m sentientos.ops verify formal --json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--repo-root", help="repository root (defaults to current working directory)")

    domains = parser.add_subparsers(dest="domain", required=True)

    node = domains.add_parser("node", help="node lifecycle operations")
    node_sub = node.add_subparsers(dest="action", required=True)

    node_bootstrap = node_sub.add_parser("bootstrap", help="bootstrap local node and emit cockpit artifacts")
    node_bootstrap.add_argument("--reason", default="operator_node_bootstrap")
    node_bootstrap.add_argument("--seed-minimal", action="store_true")
    node_bootstrap.add_argument("--no-restore", action="store_true")
    node_bootstrap.add_argument("--json", action="store_true")

    node_health_p = node_sub.add_parser("health", help="evaluate node health posture")
    node_health_p.add_argument("--json", action="store_true")

    node_restore = node_sub.add_parser("restore", help="bootstrap trust restoration artifacts")
    node_restore.add_argument("--reason", default="operator_bootstrap_trust_restore")
    node_restore.add_argument("--no-checkpoint", action="store_true")
    node_restore.add_argument("--json", action="store_true")

    constitution = domains.add_parser("constitution", help="system constitution operations")
    constitution_sub = constitution.add_subparsers(dest="action", required=True)
    constitution_latest = constitution_sub.add_parser("latest", help="read latest constitution summary")
    constitution_latest.add_argument("--json", action="store_true", help="render canonical JSON payload")
    constitution_json = constitution_sub.add_parser("json", help="compose and write constitution artifacts")
    constitution_json.add_argument("--json", action="store_true", help="render canonical JSON payload")
    constitution_verify = constitution_sub.add_parser("verify", help="verify constitution state and return constitutional exit code")
    constitution_verify.add_argument("--json", action="store_true", help="render canonical JSON payload")

    forge = domains.add_parser("forge", help="forge integrity operations")
    forge_sub = forge.add_subparsers(dest="action", required=True)
    forge_status = forge_sub.add_parser("status", help="forge integrity status")
    forge_status.add_argument("--latest", action="store_true")
    forge_status.add_argument("--json", action="store_true")
    forge_replay = forge_sub.add_parser("replay", help="forge replay verification")
    forge_replay.add_argument("--verify", action="store_true")
    forge_replay.add_argument("--last-n", type=int)
    forge_replay.add_argument("--emit-snapshot", choices=["0", "1"])

    incident = domains.add_parser("incident", help="incident triage operations")
    incident_sub = incident.add_subparsers(dest="action", required=True)
    incident_bundle = incident_sub.add_parser("bundle", help="generate bounded incident bundle")
    incident_bundle.add_argument("--reason", default="operator_incident_bundle")
    incident_bundle.add_argument("--window", type=int, default=50)
    incident_bundle.add_argument("--json", action="store_true")

    audit = domains.add_parser("audit", help="audit verification operations")
    audit_sub = audit.add_subparsers(dest="action", required=True)
    audit_verify = audit_sub.add_parser("verify", help="verify audit ledgers")
    audit_verify.add_argument("--json", action="store_true", help="render canonical JSON payload")
    audit_verify.add_argument("args", nargs=argparse.REMAINDER)
    audit_immutability = audit_sub.add_parser("immutability", help="verify immutable manifest file hashes")
    audit_immutability.add_argument("--manifest", help="override immutable manifest path")
    audit_immutability.add_argument("--allow-missing-manifest", action="store_true")
    audit_immutability.add_argument("args", nargs=argparse.REMAINDER)

    simulate = domains.add_parser("simulate", help="deterministic simulation operations")
    simulate_sub = simulate.add_subparsers(dest="action", required=True)
    simulate_federation = simulate_sub.add_parser("federation", help="run bounded local federation simulation scenarios")
    simulate_federation.add_argument("--scenario", default="healthy_3node")
    simulate_federation.add_argument("--seed", type=int, default=7)
    simulate_federation.add_argument("--nodes", type=int)
    simulate_federation.add_argument("--emit-bundle", action="store_true")
    simulate_federation.add_argument("--list-scenarios", action="store_true")
    simulate_federation.add_argument("--baseline", action="store_true")
    simulate_federation.add_argument("--json", action="store_true")

    verify = domains.add_parser("verify", help="verification wings")
    verify_sub = verify.add_subparsers(dest="action", required=True)
    verify_formal = verify_sub.add_parser("formal", help="run bounded formal model checks")
    verify_formal.add_argument("--json", action="store_true", help="render canonical JSON payload")
    verify_formal.add_argument("--spec", action="append", default=[], help="specific spec id (repeatable)")

    return parser


def main(argv: Sequence[str] | None = None, *, prog: str = "python -m sentientos.ops") -> int:
    parser = build_parser(prog=prog)
    args, unknown = parser.parse_known_args(list(argv) if argv is not None else None)
    repo_root = _resolve_repo_root(getattr(args, "repo_root", None))

    if args.domain == "node" and args.action == "bootstrap":
        payload = run_bootstrap(repo_root, reason=str(args.reason), seed_minimal=bool(args.seed_minimal), allow_restore=not bool(args.no_restore))
        payload = _decorate_payload(payload, domain=args.domain, action=args.action)
        emit_payload(payload, as_json=bool(args.json), text_renderer=lambda row: f"health_state={row.get('health_state')} constitution_state={row.get('constitution_state')} report_path={row.get('report_path')}")
        return exit_code(payload)

    if args.domain == "node" and args.action == "health":
        payload = node_health(repo_root)
        payload = _decorate_payload(payload, domain=args.domain, action=args.action)
        emit_payload(payload, as_json=bool(args.json), text_renderer=lambda row: f"health_state={row.get('health_state')} constitution_state={row.get('constitution_state')} integrity={row.get('integrity_overall')}")
        return exit_code(payload)

    if args.domain == "node" and args.action == "restore":
        from scripts.bootstrap_trust_restore import run_bootstrap as run_restore

        previous = os.environ.get("SENTIENTOS_REPO_ROOT")
        os.environ["SENTIENTOS_REPO_ROOT"] = str(repo_root)
        try:
            payload = run_restore(repo_root, reason=str(args.reason), create_checkpoint=not bool(args.no_checkpoint))
        finally:
            if previous is None:
                os.environ.pop("SENTIENTOS_REPO_ROOT", None)
            else:
                os.environ["SENTIENTOS_REPO_ROOT"] = previous
        payload = _decorate_payload(payload, domain=args.domain, action=args.action)
        emit_payload(payload, as_json=bool(args.json), text_renderer=lambda row: f"status={row.get('status')} checkpoint={row.get('checkpoint', {}).get('status')}")
        return exit_code(payload)

    if args.domain == "constitution" and args.action == "latest":
        payload = _latest_constitution(repo_root)
        payload = _decorate_payload(payload, domain=args.domain, action=args.action)
        if bool(args.json):
            emit_payload(payload, as_json=True, text_renderer=lambda row: f"constitution_state={row.get('constitution_state')} identity={row.get('constitution_identity')}")
            return exit_code(payload)
        print(f"constitution_state={payload.get('constitution_state')} identity={payload.get('constitution_identity')}")
        return exit_code(payload)

    if args.domain == "constitution" and args.action == "json":
        payload = compose_system_constitution(repo_root)
        write_constitution_artifacts(repo_root, payload=payload)
        payload = _decorate_payload(payload, domain=args.domain, action=args.action)
        emit_payload(payload, as_json=bool(args.json), text_renderer=lambda row: f"constitution_state={row.get('constitution_state')} identity={row.get('constitution_identity')}")
        return exit_code(payload)

    if args.domain == "constitution" and args.action == "verify":
        payload, rc = verify_constitution(repo_root)
        payload = _decorate_payload(payload, domain=args.domain, action=args.action)
        if bool(args.json):
            emit_payload(payload, as_json=True, text_renderer=lambda row: f"constitution_state={row.get('constitution_state')} identity={row.get('constitution_identity')}")
            return exit_code(payload)
        print(f"constitution_state={payload.get('constitution_state')} identity={payload.get('constitution_identity')} missing_required={len(payload.get('missing_required_artifacts', []))}")
        return int(rc)

    if args.domain == "incident" and args.action == "bundle":
        payload = build_incident_bundle(repo_root, reason=str(args.reason), window=max(1, int(args.window)))
        payload = _decorate_payload(payload, domain=args.domain, action=args.action)
        emit_payload(payload, as_json=bool(args.json), text_renderer=lambda row: f"bundle_path={row.get('bundle_path')} manifest_sha256={row.get('manifest_sha256')} included_count={row.get('included_count')}")
        return exit_code(payload)

    if args.domain == "forge" and args.action == "status":
        from scripts.forge_status import main as forge_status_main

        forwarded: list[str] = []
        if not args.latest and not args.json:
            forwarded.append("--latest")
        if args.latest:
            forwarded.append("--latest")
        if args.json:
            forwarded.append("--json")
        return int(forge_status_main(_with_repo_flag(forwarded, repo_root)))

    if args.domain == "forge" and args.action == "replay":
        from scripts.forge_replay import main as forge_replay_main

        forwarded = []
        if args.verify:
            forwarded.append("--verify")
        if args.last_n is not None:
            forwarded.extend(["--last-n", str(args.last_n)])
        if args.emit_snapshot is not None:
            forwarded.extend(["--emit-snapshot", str(args.emit_snapshot)])
        return int(forge_replay_main(_with_repo_flag(forwarded, repo_root)))

    if args.domain == "audit" and args.action == "verify":
        from sentientos.audit_tools import verify_audits_main

        forwarded = []
        if bool(args.json):
            forwarded.append("--json")
        forwarded.extend(_normalize_passthrough([*list(args.args or []), *unknown]))
        return int(verify_audits_main(_with_repo_flag(forwarded, repo_root)))

    if args.domain == "audit" and args.action == "immutability":
        from scripts.audit_immutability_verifier import main as immutability_main

        forwarded = []
        if args.manifest:
            forwarded.extend(["--manifest", str(args.manifest)])
        if bool(args.allow_missing_manifest):
            forwarded.append("--allow-missing-manifest")
        forwarded.extend(_normalize_passthrough([*list(args.args or []), *unknown]))
        previous = Path.cwd()
        os.chdir(repo_root)
        try:
            return int(immutability_main(forwarded))
        finally:
            os.chdir(previous)

    if args.domain == "simulate" and args.action == "federation":
        from sentientos.simulation import list_federation_scenarios, run_federation_baseline_suite, run_federation_simulation

        if bool(args.list_scenarios):
            payload = {
                "schema_version": 1,
                "scenarios": list_federation_scenarios(),
                "status": "passed",
                "exit_code": 0,
            }
            payload = _decorate_payload(payload, domain=args.domain, action=args.action)
            emit_payload(payload, as_json=bool(args.json), text_renderer=lambda row: f"scenario_count={len(row.get('scenarios', []))}")
            return 0
        if bool(args.baseline):
            payload = run_federation_baseline_suite(repo_root, emit_bundle=True)
        else:
            payload = run_federation_simulation(
                repo_root,
                scenario_name=str(args.scenario),
                seed=int(args.seed),
                node_count=int(args.nodes) if args.nodes is not None else None,
                emit_bundle=bool(args.emit_bundle),
            )
        payload = _decorate_payload(payload, domain=args.domain, action=args.action)
        emit_payload(
            payload,
            as_json=bool(args.json),
            text_renderer=lambda row: (
                f"scenario={row.get('scenario') or row.get('suite')} "
                f"status={row.get('status')} "
                f"quorum_admit={((row.get('quorum') if isinstance(row.get('quorum'), dict) else {}).get('admit'))} "
                f"report_path={row.get('report_path') or ((row.get('artifact_paths') if isinstance(row.get('artifact_paths'), dict) else {}).get('report_path'))}"
            ),
        )
        return exit_code(payload)

    if args.domain == "verify" and args.action == "formal":
        from sentientos.formal_verification import run_formal_verification

        payload = run_formal_verification(repo_root, selected_specs=list(args.spec or []))
        payload = _decorate_payload(payload, domain=args.domain, action=args.action)
        emit_payload(
            payload,
            as_json=bool(args.json),
            text_renderer=lambda row: (
                f"status={row.get('status')} "
                f"spec_count={row.get('spec_count')} "
                f"summary={((row.get('artifact_paths') if isinstance(row.get('artifact_paths'), dict) else {}).get('summary'))}"
            ),
        )
        return exit_code(payload)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
