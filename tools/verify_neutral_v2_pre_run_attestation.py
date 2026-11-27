#!/usr/bin/env python3
"""Verify a digest-only pre-run attestation against private campaign files.

This checks custody and launch state. It does not validate scientific claims,
independent authorship, or the frozen experiment implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=repo)


def verify(args: argparse.Namespace) -> dict[str, Any]:
    repo = args.repo_root.resolve()
    attestation_path = args.attestation.resolve()
    plan = read_json(args.plan)
    protocol_bytes = args.protocol.read_bytes()
    protocol = json.loads(protocol_bytes.decode("utf-8"))
    protocol_digest = sha256(
        protocol_bytes.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    )
    card_bytes = args.run_card.read_bytes()
    card = json.loads(card_bytes)
    attestation = read_json(attestation_path)
    campaign_plan_digest = plan.get("plan_digest")
    campaign_id = plan.get("campaign_id")
    cycles = plan.get("ordered_cycle_ids", [])
    card_cycles = card.get("cycles")
    card_cycle_ids = ([cycle.get("cycle_id") for cycle in card_cycles
        if isinstance(cycle, dict)] if isinstance(card_cycles, list) else [])
    cycle_inventory_matches = (
        isinstance(cycles, list) and len(cycles) > 0
        and len(card_cycles or []) == len(cycles)
        and card_cycle_ids == cycles)
    cycle_dirs_absent = (
        isinstance(cycles, list) and len(cycles) > 0
        and all(not (args.cycle_data_root / cycle).exists() for cycle in cycles)
    )

    try:
        relative_attestation = attestation_path.relative_to(repo).as_posix()
    except ValueError as exc:
        raise ValueError("attestation_file_outside_repo") from exc
    commit_blob = git(
        repo, "show", f"{args.attestation_commit}:{relative_attestation}"
    )
    commit_time = git(
        repo, "show", "-s", "--format=%cI", args.attestation_commit
    ).decode("utf-8").strip()
    reachable = subprocess.run(
        ["git", "merge-base", "--is-ancestor",
            args.attestation_commit, args.remote_ref],
        cwd=repo, check=False, capture_output=True,
    ).returncode == 0

    checks = {
        "attestation_commit_reachable_from_remote_ref": reachable,
        "attestation_commit_contains_exact_file_bytes": (
            commit_blob == attestation_path.read_bytes()
        ),
        "campaign_id_matches_plan_and_card": (
            attestation.get("campaign_id") == campaign_id
            and card.get("campaign_id") == campaign_id
        ),
        "run_card_paths_match_inputs": (
            Path(card.get("campaign_plan_path", "")).resolve() == args.plan.resolve()
            and Path(card.get("owner_feedback_protocol_path", "")).resolve()
                == args.protocol.resolve()
        ),
        "protocol_id_matches_card": (
            card.get("owner_feedback_protocol_id") == protocol.get("protocol_id")
        ),
        "cycle_inventory_matches_plan": cycle_inventory_matches,
        "plan_digest_matches_attestation_and_card": (
            attestation.get("digests", {}).get("campaign_plan_sha256")
                == campaign_plan_digest
            and card.get("campaign_plan_digest") == campaign_plan_digest
        ),
        "protocol_digest_matches_attestation_and_card": (
            attestation.get("digests", {}).get("owner_feedback_protocol_sha256")
                == protocol_digest
            and card.get("owner_feedback_protocol_digest") == protocol_digest
        ),
        "private_run_card_digest_matches_attestation": (
            attestation.get("digests", {}).get("private_run_card_file_sha256")
                == sha256(card_bytes)
        ),
        "run_card_is_private_mode_0600": (
            args.run_card.stat().st_mode & 0o777 == 0o600
        ),
        "preregistration_limitations_preserved": (
            plan.get("preregistration_timing_independently_attested") is False
            and card.get("preregistration_timing_independently_attested") is False
            and attestation.get("preregistration_timing_independently_attested")
                is False
        ),
        "campaign_still_prepared_without_inference_or_authority": (
            card.get("status") == "prepared_not_started"
            and card.get("inference_performed") is False
            and card.get("authority") is False
            and attestation.get("observed_launch_state", {}).get(
                "inference_performed") is False
            and attestation.get("observed_launch_state", {}).get("authority")
                is False
        ),
        "planned_cycle_roots_remain_absent": (
            attestation.get("observed_launch_state", {}).get(
                "planned_cycle_storage_roots_exist") is False
            and cycle_dirs_absent
        ),
        "per_cycle_gpu_confirmation_remains_required": (
            cycle_inventory_matches
            and attestation.get("observed_launch_state", {}).get(
                "gpu_confirmation_required_per_cycle") is True
            and all(cycle.get("gpu_confirmation_required_at_launch") is True
                for cycle in card_cycles)
        ),
        "attestation_excludes_private_payloads": (
            attestation.get("raw_campaign_plan_included") is False
            and attestation.get("raw_run_card_included") is False
            and attestation.get("model_identity_included") is False
            and attestation.get("task_generation_seeds_included") is False
        ),
    }
    return {
        "schema_version": "sentientos.neutral_v2_prerun_attestation_verification:v1",
        "campaign_id": campaign_id,
        "attestation_file_sha256": sha256(attestation_path.read_bytes()),
        "attestation_commit_sha": args.attestation_commit,
        "attestation_commit_timestamp": commit_time,
        "remote_ref": args.remote_ref,
        "campaign_plan_digest": campaign_plan_digest,
        "protocol_sha256": protocol_digest,
        "private_run_card_sha256": sha256(card_bytes),
        "checks": checks,
        "all_checks_pass": all(checks.values()),
        "claims": {
            "independent_authorship": False,
            "independent_review": False,
            "learning": False,
            "authority": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path,
        default=Path(__file__).resolve().parents[1])
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--attestation-commit", required=True)
    parser.add_argument("--remote-ref", required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--run-card", type=Path, required=True)
    parser.add_argument("--cycle-data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify(args)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
        print(f"report_written={args.output}")
    print(json.dumps({
        "all_checks_pass": report["all_checks_pass"],
        "checks": report["checks"],
        "commit": report["attestation_commit_sha"],
        "timestamp": report["attestation_commit_timestamp"],
    }, sort_keys=True))
    return 0 if report["all_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
