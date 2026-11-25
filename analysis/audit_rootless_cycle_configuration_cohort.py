"""Audit model and source comparability across completed rootless cycles.

CPU-only. Verifies sealed preregistrations against cycle results and reports
whether cycles form a same-configuration repeat cohort. This does not establish
a causal history effect or learning.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.local_model import candidate_configuration_digest_from_payload
from sentientos.local_model_authority import digest_payload
from sentientos.local_runtime_provisioning import semantic_digest as runtime_digest

MAX_INPUT_BYTES = 16 * 1024 * 1024
OBSERVATION_SCHEMA = "sentientos.active_model_configuration_observation:v1"
REPORT_SCHEMA = "sentientos.rootless_cycle_configuration_cohort_audit:v2"


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("configuration_cohort_duplicate_json_key")
        result[key] = value
    return result


def _read_object(path: Path) -> tuple[dict[str, Any], str]:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise ValueError("configuration_cohort_input_unreadable") from exc
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_size > MAX_INPUT_BYTES):
            raise ValueError("configuration_cohort_input_invalid")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(fd, min(remaining, 65536))
            if not chunk:
                raise ValueError("configuration_cohort_input_truncated")
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(fd)
        if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            raise ValueError("configuration_cohort_input_changed")
    finally:
        os.close(fd)
    raw = b"".join(chunks)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ValueError("configuration_cohort_nonstandard_json")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("configuration_cohort_json_invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("configuration_cohort_object_required")
    return value, hashlib.sha256(raw).hexdigest()


def _observation(value: Any, identity: Mapping[str, Any]
        ) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    if (not isinstance(value, Mapping)
            or set(value) != {"schema_version", "configuration_digest", "payload"}
            or value.get("schema_version") != OBSERVATION_SCHEMA
            or value.get("configuration_digest") != identity.get("configuration_digest")
            or not isinstance(value.get("payload"), Mapping)):
        raise ValueError("configuration_cohort_observation_invalid")
    payload_digest = candidate_configuration_digest_from_payload(value["payload"])
    if payload_digest != value["configuration_digest"]:
        raise ValueError("configuration_cohort_payload_digest_mismatch")
    return payload_digest, digest_payload(dict(value["payload"])), dict(value["payload"])


def _cycle_row(root: Path) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("configuration_cohort_cycle_root_invalid")
    prereg, prereg_file_sha = _read_object(root / "preregistration.json")
    result, result_file_sha = _read_object(root / "cycle-result.json")
    prereg_digest = prereg.get("preregistration_digest")
    if (not isinstance(prereg_digest, str)
            or prereg_digest != runtime_digest({k: v for k, v in prereg.items()
                if k != "preregistration_digest"})
            or result.get("run_preregistration_digest") != prereg_digest
            or result.get("status") != "completed"
            or result.get("run_id") != prereg.get("run_id")
            or root.name != prereg.get("run_id")):
        raise ValueError("configuration_cohort_cycle_binding_invalid")
    identity = prereg.get("model_identity")
    result_identity = result.get("active_model_identity")
    if (not isinstance(identity, Mapping) or not isinstance(result_identity, Mapping)
            or dict(identity) != dict(result_identity)):
        raise ValueError("configuration_cohort_identity_binding_invalid")
    config_digest = identity.get("configuration_digest")
    if (not isinstance(config_digest, str) or len(config_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in config_digest)):
        raise ValueError("configuration_cohort_configuration_digest_invalid")
    saved_observation = prereg.get("model_configuration_observation")
    result_observation = result.get("model_configuration_observation")
    if saved_observation != result_observation:
        raise ValueError("configuration_cohort_observation_replay_mismatch")
    observed_digest, payload_digest, config_payload = _observation(saved_observation, identity)
    config_core_digest = None
    ollama_seed = None
    if config_payload is not None:
        options = config_payload.get("options")
        if not isinstance(options, Mapping):
            raise ValueError("configuration_cohort_options_invalid")
        ollama_seed = options.get("seed")
        if (isinstance(ollama_seed, int) and not isinstance(ollama_seed, bool)
                and ollama_seed >= 0):
            core_payload = dict(config_payload)
            core_options = dict(options)
            del core_options["seed"]
            core_payload["options"] = core_options
            config_core_digest = "sha256:" + digest_payload({
                "schema_version": "sentientos.rootless_model_configuration_without_seed:v1",
                "payload": core_payload,
            })
        else:
            ollama_seed = None
    identity_core = dict(identity)
    identity_core.pop("configuration_digest", None)
    binding = prereg.get("history_campaign_binding")
    result_binding = result.get("history_campaign_binding")
    binding_ok = (isinstance(binding, Mapping) and isinstance(result_binding, Mapping)
        and dict(binding) == dict(result_binding))
    binding = binding if binding_ok else {}
    protocol_digest = prereg.get("external_protocol_digest")
    if result.get("external_preregistration_digest") not in (None, protocol_digest):
        raise ValueError("configuration_cohort_protocol_binding_invalid")
    provenance = result.get("source_provenance")
    worktree_digest = (provenance.get("worktree_content_digest")
        if isinstance(provenance, Mapping) else None)
    source_complete = (result.get("source_provenance_stable_for_run") is True
        and result.get("source_provenance_fingerprint_complete") is True
        and isinstance(provenance, Mapping)
        and provenance.get("worktree_content_status") == "complete"
        and isinstance(worktree_digest, str) and len(worktree_digest) == 64
        and all(ch in "0123456789abcdef" for ch in worktree_digest))
    source_digest = worktree_digest if source_complete else None
    intervention = result.get("history_intervention")
    conditions = intervention.get("conditions") if isinstance(intervention, Mapping) else None
    condition_ids = (set(row.get("condition_id") for row in conditions
        if isinstance(row, Mapping)) if isinstance(conditions, list) else set())
    condition_identity_ok = (isinstance(conditions, list) and len(conditions) == 3
        and condition_ids == {
            "history_present", "history_withheld", "history_restored"}
        and all(isinstance(row, Mapping)
            and row.get("active_model_identity") == dict(identity) for row in conditions))
    acquisition = result.get("objective_task_family_acquisition")
    family = acquisition.get("task_family_id") if isinstance(acquisition, Mapping) else None
    return {
        "cycle_id": result["run_id"],
        "preregistration_file_sha256": prereg_file_sha,
        "cycle_result_file_sha256": result_file_sha,
        "model_identity_digest": "sha256:" + digest_payload(dict(identity)),
        "model_configuration_digest": config_digest,
        "configuration_payload_present": observed_digest is not None,
        "configuration_payload_digest": (
            "sha256:" + payload_digest if payload_digest is not None else None),
        "configuration_core_digest_without_seed": config_core_digest,
        "ollama_model_seed": ollama_seed,
        "experiment_seed": prereg.get("experiment_seed"),
        "model_identity_core_digest": "sha256:" + digest_payload(identity_core),
        "external_protocol_digest": protocol_digest,
        "campaign_binding_verified": binding_ok,
        "campaign_id": binding.get("campaign_id"),
        "campaign_plan_digest": binding.get("campaign_plan_digest"),
        "campaign_cycle_index": binding.get("cycle_index"),
        "source_content_digest": source_digest,
        "source_provenance_complete": source_complete,
        "task_family_id": family,
        "condition_identity_bindings_verified": condition_identity_ok,
    }


def audit_cohort(roots: list[Path]) -> dict[str, Any]:
    if len(roots) < 2:
        raise ValueError("configuration_cohort_requires_multiple_cycles")
    rows = [_cycle_row(root) for root in roots]
    if len({row["cycle_id"] for row in rows}) != len(rows):
        raise ValueError("configuration_cohort_duplicate_cycle")
    configs = {row["model_configuration_digest"] for row in rows}
    payloads = {row["configuration_payload_digest"] for row in rows}
    identities = {row["model_identity_digest"] for row in rows}
    sources = {row["source_content_digest"] for row in rows}
    families = {row["task_family_id"] for row in rows}
    payloads_present = all(row["configuration_payload_present"] for row in rows)
    source_complete = all(row["source_provenance_complete"] for row in rows)
    parity = {
        "model_configuration_digests_equal": len(configs) == 1,
        "canonical_configuration_payloads_present": payloads_present,
        "canonical_configuration_payload_digests_equal":
            payloads_present and len(payloads) == 1,
        "model_identity_digests_equal": len(identities) == 1,
        "source_provenance_complete_for_all_cycles": source_complete,
        "source_content_digests_equal": source_complete and len(sources) == 1,
        "task_families_equal": None not in families and len(families) == 1,
        "condition_identity_bindings_verified":
            all(row["condition_identity_bindings_verified"] for row in rows),
    }
    ollama_seeds = [row["ollama_model_seed"] for row in rows]
    experiment_seeds = [row["experiment_seed"] for row in rows]
    core_digests = {row["configuration_core_digest_without_seed"] for row in rows}
    identity_core_digests = {row["model_identity_core_digest"] for row in rows}
    protocols = {row["external_protocol_digest"] for row in rows}
    campaign_ids = {row["campaign_id"] for row in rows}
    plan_digests = {row["campaign_plan_digest"] for row in rows}
    cycle_indexes = [row["campaign_cycle_index"] for row in rows]
    seed_parity = {
        "configuration_payloads_equal_except_preregistered_seed":
            payloads_present and None not in core_digests and len(core_digests) == 1,
        "model_identities_equal_except_configuration_digest": len(identity_core_digests) == 1,
        "ollama_seeds_present_and_unique": all(isinstance(s, int) and not isinstance(s, bool) for s in ollama_seeds) and len(set(ollama_seeds)) == len(rows),
        "experiment_seeds_present_and_unique": all(isinstance(s, int) and not isinstance(s, bool) for s in experiment_seeds) and len(set(experiment_seeds)) == len(rows),
        "external_protocol_digest_shared": None not in protocols and len(protocols) == 1,
        "campaign_binding_verified_for_all_cycles": all(row["campaign_binding_verified"] for row in rows),
        "campaign_id_and_plan_digest_shared": None not in campaign_ids and None not in plan_digests and len(campaign_ids) == 1 and len(plan_digests) == 1,
        "campaign_cycle_indexes_unique": all(isinstance(i, int) and not isinstance(i, bool) for i in cycle_indexes) and len(set(cycle_indexes)) == len(rows),
        "source_content_digests_equal": source_complete and len(sources) == 1,
        "task_families_equal": None not in families and len(families) == 1,
        "condition_identity_bindings_verified": all(row["condition_identity_bindings_verified"] for row in rows),
    }
    semantic = {
        "schema_version": REPORT_SCHEMA,
        "cycle_count": len(rows),
        "cycles": rows,
        "parity": parity,
        "configuration_parity_gate_passed": all(parity.values()),
        "seed_normalized_configuration_parity": seed_parity,
        "seed_normalized_configuration_parity_observed": all(seed_parity.values()),
        "seed_normalized_interpretation_limit": "Per-cycle bindings and seed-normalized configuration are checked; campaign-plan artifact is not reloaded, and this diagnostic establishes neither cohort eligibility nor an outcome or learning claim.",
        "audit_performed_inference": False,
        "learning_established": False,
        "authority": False,
    }
    return {**semantic, "audit_digest": "sha256:" + digest_payload(semantic)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle-root", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_cohort(args.cycle_root)
    rendered = json.dumps(report, sort_keys=True, indent=2,
        ensure_ascii=False, allow_nan=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, TypeError, ValueError, RecursionError) as exc:
        print("rootless_cycle_configuration_cohort_error:" + str(exc),
            file=sys.stderr)
        raise SystemExit(2)

