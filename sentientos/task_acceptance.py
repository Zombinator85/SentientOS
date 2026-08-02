from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from sentientos.behavioral_witness import digest as canonical_digest, valid_witness

SCHEMA_VERSION = "sentientos.task_acceptance:v1"
SCHEMA_VERSION_V2 = "sentientos.task_acceptance:v2"
ASSERTION_OPERATORS = {"equals", "not_equals", "is_true", "is_false", "is_nonempty", "count_equals",
                       "same_value", "different_value", "ordered_subsequence"}


def _pointer(value: object, pointer: object) -> tuple[bool, object]:
    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
        return False, None
    current = value
    if pointer == "":
        return True, current
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            return False, None
    return True, current


def _assertion(facts: object, assertion: dict[str, object]) -> bool:
    found, actual = _pointer(facts, assertion.get("path"))
    if not found:
        return False
    op = assertion.get("op")
    if op == "equals": return actual == assertion.get("value")
    if op == "not_equals": return actual != assertion.get("value")
    if op == "is_true": return actual is True
    if op == "is_false": return actual is False
    if op == "is_nonempty": return isinstance(actual, (str, list, dict)) and bool(actual)
    if op == "count_equals": return isinstance(actual, (str, list, dict)) and len(actual) == assertion.get("value")
    if op in {"same_value", "different_value"}:
        other_found, other = _pointer(facts, assertion.get("other_path"))
        return other_found and ((actual == other) if op == "same_value" else (actual != other))
    if op == "ordered_subsequence":
        expected = assertion.get("value")
        if not isinstance(actual, list) or not isinstance(expected, list): return False
        iterator = iter(actual)
        return all(any(candidate == wanted for candidate in iterator) for wanted in expected)
    return False


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verify(manifest_path: Path, provenance_path: Path, *, repo_root: Path = Path(".")) -> dict[str, Any]:
    reasons: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "task_acceptance_blocked", "reasons": [f"invalid_evidence:{exc}"]}
    required = manifest.get("required_nodes", [])
    successful = manifest.get("successful_path_nodes", [])
    classification = manifest.get("task_classification")
    schema = manifest.get("schema_version")
    if schema not in {SCHEMA_VERSION, SCHEMA_VERSION_V2} or not isinstance(required, list) or not all(isinstance(x, dict) and isinstance(x.get("node_id"), str) for x in required):
        reasons.append("malformed_manifest")
        required = []
    required_ids = [x["node_id"] for x in required]
    if not isinstance(successful, list) or not all(isinstance(x, str) for x in successful) or not set(successful).issubset(required_ids):
        reasons.append("malformed_successful_path_nodes")
        successful = []
    if classification == "behavior_adding" and not successful:
        reasons.append("behavior_adding_requires_successful_path_node")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True, capture_output=True, check=False).stdout.strip()
    expected_sha = str(manifest.get("repository_sha", ""))
    if not expected_sha or provenance.get("git_sha") != expected_sha or head != expected_sha:
        reasons.append("repository_sha_mismatch")
    if not provenance.get("reporter_ok") or provenance.get("metrics_status") != "ok":
        reasons.append("reporter_incomplete")
    selected = set(provenance.get("selected_node_ids", []))
    outcomes = {x.get("node_id"): x for x in provenance.get("node_outcomes", []) if isinstance(x, dict)}
    per_node = []
    contract_results: list[dict[str, object]] = []
    required_contract_count = 0
    passed_contract_count = 0
    witnesses = provenance.get("behavioral_witnesses", [])
    if not isinstance(witnesses, list):
        witnesses = []
    for node in required_ids:
        test_path = node.split("::", 1)[0]
        exists = bool("::" in node and (repo_root / test_path).is_file())
        item = outcomes.get(node, {})
        passed = exists and node in selected and item.get("phase") == "call" and item.get("outcome") == "passed"
        per_node.append({"node_id": node, "exists": exists, "selected": node in selected, "phase": item.get("phase"), "outcome": item.get("outcome"), "passed": passed})
        if not passed:
            reasons.append(f"required_node_not_passed:{node}")
        if schema != SCHEMA_VERSION_V2:
            continue
        contracts = required[required_ids.index(node)].get("witness_contracts", [])
        if not isinstance(contracts, list) or len(contracts) > 32:
            reasons.append(f"malformed_witness_contract:{node}:unknown")
            continue
        for contract in contracts:
            required_contract_count += 1
            contract_id = contract.get("contract_id", "unknown") if isinstance(contract, dict) else "unknown"
            summary: dict[str, object] = {"node_id": node, "contract_id": contract_id, "passed": False}
            contract_results.append(summary)
            if (not isinstance(contract, dict) or not isinstance(contract_id, str)
                    or not isinstance(contract.get("witness_kind"), str)
                    or not isinstance(contract.get("assertions"), list)
                    or len(contract["assertions"]) > 64):
                reasons.append(f"malformed_witness_contract:{node}:{contract_id}"); continue
            kind = contract["witness_kind"]
            same_contract = [w for w in witnesses if isinstance(w, dict) and w.get("node_id") == node and w.get("contract_id") == contract_id]
            matching = [w for w in same_contract if w.get("witness_kind") == kind and w.get("run_id") == provenance.get("run_id")
                        and w.get("repository_sha") == expected_sha and w.get("phase") == "call"]
            prefix = f"{node}:{contract_id}"
            if not matching:
                if any(w.get("witness_kind") != kind for w in same_contract): reason = "required_witness_wrong_kind"
                elif any(w.get("run_id") != provenance.get("run_id") for w in same_contract): reason = "required_witness_wrong_run"
                elif any(w.get("repository_sha") != expected_sha for w in same_contract): reason = "required_witness_wrong_sha"
                elif any(w.get("phase") != "call" for w in same_contract): reason = "required_witness_non_call_phase"
                else: reason = "required_witness_missing"
                reasons.append(f"{reason}:{prefix}"); continue
            if len(matching) != 1:
                unique = {str(w.get("digest")) for w in matching}
                reasons.append(f"required_witness_{'duplicate' if len(unique) == 1 else 'conflict'}:{prefix}"); continue
            witness = matching[0]
            if not valid_witness(witness):
                reasons.append(f"required_witness_digest_invalid:{prefix}"); continue
            assertion_failed = False
            for index, assertion in enumerate(contract["assertions"]):
                if not isinstance(assertion, dict) or not isinstance(assertion.get("op"), str):
                    reasons.append(f"malformed_witness_contract:{prefix}"); assertion_failed = True; break
                op = assertion["op"]
                if op not in ASSERTION_OPERATORS:
                    reasons.append(f"unknown_witness_assertion_operator:{prefix}:{op}"); assertion_failed = True; break
                if not _assertion(witness["facts"], assertion):
                    reasons.append(f"required_witness_assertion_failed:{prefix}:{index}"); assertion_failed = True; break
            if not assertion_failed:
                summary["passed"] = True
                passed_contract_count += 1
    return {
        "schema_version": "sentientos.task_acceptance_result:v1",
        "status": "task_acceptance_ready" if not reasons else "task_acceptance_blocked",
        "reasons": reasons,
        "manifest_path": str(manifest_path), "manifest_digest": _digest(manifest_path),
        "provenance_path": str(provenance_path), "provenance_digest": _digest(provenance_path),
        "repository_sha": expected_sha, "task_classification": classification,
        "required_node_ids": required_ids, "successful_path_node_ids": successful, "node_outcomes": per_node,
        "required_witness_contract_count": required_contract_count,
        "passed_witness_contract_count": passed_contract_count,
        "behavioral_witness_provenance_digest": provenance.get("behavioral_witness_digest", canonical_digest(witnesses)),
        "witness_status": "ready" if required_contract_count == passed_contract_count else "blocked",
        "witness_contract_results": contract_results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify exact task behavioral acceptance evidence without effects.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--provenance", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    result = verify(Path(args.manifest), Path(args.provenance))
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["status"] == "task_acceptance_ready" else 1
