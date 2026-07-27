from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "sentientos.task_acceptance:v1"


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
    if manifest.get("schema_version") != SCHEMA_VERSION or not isinstance(required, list) or not all(isinstance(x, dict) and isinstance(x.get("node_id"), str) for x in required):
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
    for node in required_ids:
        test_path = node.split("::", 1)[0]
        exists = bool("::" in node and (repo_root / test_path).is_file())
        item = outcomes.get(node, {})
        passed = exists and node in selected and item.get("phase") == "call" and item.get("outcome") == "passed"
        per_node.append({"node_id": node, "exists": exists, "selected": node in selected, "phase": item.get("phase"), "outcome": item.get("outcome"), "passed": passed})
        if not passed:
            reasons.append(f"required_node_not_passed:{node}")
    return {
        "schema_version": "sentientos.task_acceptance_result:v1",
        "status": "task_acceptance_ready" if not reasons else "task_acceptance_blocked",
        "reasons": reasons,
        "manifest_path": str(manifest_path), "manifest_digest": _digest(manifest_path),
        "provenance_path": str(provenance_path), "provenance_digest": _digest(provenance_path),
        "repository_sha": expected_sha, "task_classification": classification,
        "required_node_ids": required_ids, "successful_path_node_ids": successful, "node_outcomes": per_node,
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

