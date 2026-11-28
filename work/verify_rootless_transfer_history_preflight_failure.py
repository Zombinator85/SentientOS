"""Verify bounded transfer-history pre-inference failure diagnostics."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.windows_handle_custody import (  # noqa: E402
    WindowsHandleCustodyError,
    read_explicit_file,
)

FAILURE_SCHEMA = "sentientos.rootless_ollama_embodied_cognition_failure:v9"
DIAGNOSTIC_SCHEMA = (
    "sentientos.objective_task_family_transfer_history_preflight_diagnostic:v2")
MAX_FAILURE_BYTES = 8_388_608
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)


def _read_failure(path: Path) -> dict[str, Any]:
    try:
        if (os.name == "nt" and str(path.anchor).startswith("\\\\")
                and not path.is_symlink()):
            # The handle-custody reader intentionally rejects WSL UNC roots;
            # accept an explicitly named WSL share with a strict byte ceiling.
            with path.open("rb") as stream:
                raw = stream.read(MAX_FAILURE_BYTES + 1)
            if len(raw) > MAX_FAILURE_BYTES:
                raise ValueError("transfer_preflight_failure_artifact_too_large")
        else:
            raw = read_explicit_file(path, max_bytes=MAX_FAILURE_BYTES)
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError,
            WindowsHandleCustodyError) as exc:
        raise ValueError("transfer_preflight_failure_artifact_invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("transfer_preflight_failure_artifact_invalid")
    return value


def _paired_ids_and_digests(value: Mapping[str, Any], *, ids_key: str,
        digests_key: str, allow_empty: bool) -> tuple[list[str], list[str]]:
    ids = value.get(ids_key)
    digests = value.get(digests_key)
    if (not isinstance(ids, list) or not isinstance(digests, list)
            or len(ids) != len(digests)
            or (not allow_empty and not ids)
            or any(not isinstance(item, str) or not item for item in ids)
            or len(set(ids)) != len(ids)
            or any(not isinstance(item, str) or _SHA256.fullmatch(item) is None
                for item in digests)):
        raise ValueError("transfer_preflight_failure_record_binding_invalid")
    return ids, digests


def verify_failure(*, failure_path: Path) -> dict[str, Any]:
    """Check bounded diagnostic consistency; this does not attest artifact origin."""
    failure = _read_failure(failure_path)
    if (failure.get("schema_version") != FAILURE_SCHEMA
            or failure.get("status") != "incomplete"
            or not isinstance(failure.get("run_id"), str)):
        raise ValueError("transfer_preflight_failure_schema_invalid")
    diagnostic = failure.get("failure_diagnostic")
    if diagnostic is None:
        if failure.get("failure_code") != (
                "objective_family_transfer_history_not_retrieved"):
            raise ValueError("transfer_preflight_failure_diagnostic_missing")
        return {
            "status": "legacy_diagnostic_unavailable",
            "run_id": failure["run_id"],
            "failure_code": failure["failure_code"],
            "verification_scope": "legacy_failure_has_no_preflight_diagnostic",
            "inference_or_learning_claimed": False,
            "artifact_origin_attested": False,
        }
    if (not isinstance(diagnostic, Mapping)
            or diagnostic.get("schema_version") != DIAGNOSTIC_SCHEMA
            or failure.get("failure_code") != (
                "objective_family_transfer_history_not_retrievable_preinference")
            or diagnostic.get("failure_kind") != (
                "required_history_selection_not_retrievable_or_restorable")):
        raise ValueError("transfer_preflight_failure_diagnostic_schema_invalid")

    required_ids, required_digests = _paired_ids_and_digests(diagnostic,
        ids_key="required_history_record_ids",
        digests_key="required_history_record_digests", allow_empty=False)
    selected_ids, _ = _paired_ids_and_digests(diagnostic,
        ids_key="selected_history_record_ids",
        digests_key="selected_history_record_digests", allow_empty=True)
    restored_ids, _ = _paired_ids_and_digests(diagnostic,
        ids_key="restored_history_record_ids",
        digests_key="restored_history_record_digests", allow_empty=True)
    required_digest_by_id = dict(zip(required_ids, required_digests))
    expected_missing_present = [item for item in required_ids
        if item not in selected_ids]
    expected_missing_restored = [item for item in required_ids
        if item not in restored_ids]
    expected_missing_union = [item for item in required_ids
        if item in expected_missing_present or item in expected_missing_restored]
    for label, expected in (("missing_present", expected_missing_present),
            ("missing_restored", expected_missing_restored),
            ("missing_required", expected_missing_union)):
        ids = diagnostic.get(label + "_history_record_ids")
        digests = diagnostic.get(label + "_history_record_digests")
        expected_digests = [required_digest_by_id[item] for item in expected]
        # Historical v2 diagnostics omitted the digest companion only for the
        # union field. Its exact digests remain derivable from the required
        # record bindings; validate the companion whenever present.
        legacy_union_without_digests = (
            label == "missing_required" and digests is None)
        if (ids != expected
                or (not legacy_union_without_digests
                    and digests != expected_digests)):
            raise ValueError("transfer_preflight_failure_missing_set_mismatch")

    prompt_limit = diagnostic.get("prompt_limit_chars")
    if type(prompt_limit) is not int or not 1024 <= prompt_limit <= 48_000:
        raise ValueError("transfer_preflight_failure_prompt_limit_invalid")
    prompt_sizes: dict[str, int] = {}
    for condition in ("present", "restored"):
        chars = diagnostic.get(f"history_{condition}_prompt_chars")
        utf8_bytes = diagnostic.get(f"history_{condition}_prompt_utf8_bytes")
        over_limit = diagnostic.get(
            f"history_{condition}_prompt_over_limit_chars")
        if (type(chars) is not int or chars <= 0
                or type(utf8_bytes) is not int or utf8_bytes < chars
                or type(over_limit) is not int
                or over_limit != max(0, chars - prompt_limit)):
            raise ValueError("transfer_preflight_failure_prompt_size_invalid")
        prompt_digest = diagnostic.get(f"history_{condition}_prompt_digest")
        if not isinstance(prompt_digest, str) or _SHA256.fullmatch(prompt_digest) is None:
            raise ValueError("transfer_preflight_failure_prompt_digest_invalid")
        prompt_sizes[condition] = chars
    if (diagnostic.get("history_present_prompt_digest")
            != diagnostic.get("history_restored_prompt_digest")
            or prompt_sizes["present"] != prompt_sizes["restored"]):
        raise ValueError("transfer_preflight_failure_prompt_restore_mismatch")
    if (diagnostic.get("history_selection_binding_verified") is not False
            or diagnostic.get("inference_performed") is not False
            or diagnostic.get("learning_established") is not False
            or diagnostic.get("authority") is not False):
        raise ValueError("transfer_preflight_failure_claim_scope_invalid")

    return {
        "status": "verified",
        "run_id": failure["run_id"],
        "failure_code": failure["failure_code"],
        "required_record_count": len(required_ids),
        "missing_present_count": len(expected_missing_present),
        "missing_restored_count": len(expected_missing_restored),
        "missing_either_count": len(expected_missing_union),
        "missing_required_digests_derived_from_required_bindings": (
            diagnostic.get("missing_required_history_record_digests") is None),
        "prompt_limit_chars": prompt_limit,
        "present_prompt_chars": prompt_sizes["present"],
        "restored_prompt_chars": prompt_sizes["restored"],
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
        "verification_scope": "diagnostic_internal_consistency_only",
        "artifact_origin_attested": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--failure", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify_failure(failure_path=args.failure), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
