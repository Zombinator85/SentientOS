from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

SCHEMA = "sentientos.pytest_bootstrap:v1"
DEFAULT_NODE = "tests/test_pytest_bootstrap_inertness.py::test_bootstrap_call_phase_witness"
LIMIT = 12000


def _git_sha(root: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def verify(*, output: Path, node: str = DEFAULT_NODE, collect_only: bool = False,
           root: Path = Path("."), sentinel_mode: str = "fail", metrics_path: Path | None = None) -> dict[str, object]:
    root = root.resolve(); marker_dir = Path(tempfile.mkdtemp(prefix="sentientos-pytest-bootstrap-"))
    marker = marker_dir / "privilege-invoked"
    site = marker_dir / "sitecustomize.py"
    site.write_text(
        "import pathlib\nimport sentientos.privilege as p\n"
        f"MARKER=pathlib.Path({str(marker)!r})\n"
        "def denied(*a, **k):\n MARKER.write_text('invoked')\n raise RuntimeError('pytest bootstrap invoked privilege')\n"
        "p.require_admin_banner=denied\np.require_covenant_alignment=denied\n", encoding="utf-8")
    provenance = metrics_path or root / "glow/test_runs/test_run_provenance.json"
    try: provenance.unlink()
    except FileNotFoundError: pass
    command = [sys.executable, "-m", "scripts.run_tests", "-q", node]
    if collect_only: command.append("--collect-only")
    env = os.environ.copy(); env["PYTHONPATH"] = os.pathsep.join((str(marker_dir), str(root), env.get("PYTHONPATH", "")))
    if sentinel_mode == "invoke":
        command = [sys.executable, "-c", "import sentientos.privilege as p; p.require_admin_banner()"]
    completed = subprocess.run(command, cwd=root, env=env, text=True, capture_output=True, check=False)
    metrics: dict[str, object] = {}
    if provenance.is_file():
        try: metrics = json.loads(provenance.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError): metrics = {}
    reporter = bool(metrics)
    collection = bool(metrics.get("collection_completed"))
    collected_raw = metrics.get("tests_collected", 0)
    calls_raw = metrics.get("call_phase_outcome_count", 0)
    collected = collected_raw if isinstance(collected_raw, int) else 0
    calls = calls_raw if isinstance(calls_raw, int) else 0
    invoked = marker.exists()
    if invoked: status = "privilege_invoked"
    elif completed.returncode != 0 and not (collect_only and collection and collected > 0): status = "bootstrap_failed"
    elif not reporter: status = "metrics_missing"
    elif not collection: status = "collection_failed"
    elif collected == 0: status = "zero_tests_collected"
    elif not collect_only and calls == 0: status = "zero_call_phase_outcomes"
    else: status = "pytest_bootstrap_ready"
    payload: dict[str, object] = {"schema_version": SCHEMA, "repository_sha": _git_sha(root), "python_version": sys.version,
        "selected_node": node, "child_command": command, "child_return_code": completed.returncode,
        "stdout": completed.stdout[-LIMIT:], "stderr": completed.stderr[-LIMIT:], "reporter_created": reporter,
        "collection_completed": collection, "collected_count": collected, "call_phase_outcome_count": calls,
        "privilege_sentinel_status": "invoked" if invoked else "not_invoked", "status": status}
    output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--node", default=DEFAULT_NODE)
    parser.add_argument("--collect-only", action="store_true")
    args = parser.parse_args(argv)
    try: payload = verify(output=args.output, node=args.node, collect_only=args.collect_only)
    except Exception as exc:
        payload = {"schema_version": SCHEMA, "status": "verifier_error", "error": f"{type(exc).__name__}:{exc}"}
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["status"] == "pytest_bootstrap_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
