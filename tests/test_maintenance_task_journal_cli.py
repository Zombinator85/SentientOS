from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from sentientos import maintenance_task_journal as mtj

pytestmark = pytest.mark.no_legacy_skip

ROOT = Path(__file__).resolve().parents[1]
BASE = "5c601d398281009d4a46ce55d6ea499a9beb2711"


def task() -> str:
    return mtj.derive_task_id(candidate_ref="candidate", base_sha=BASE, objective="objective", admitted_scope_digest="sha256:scope")


def run_cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "scripts/maintenance_task_journal.py", "--state-root", str(root), "--repo-root", str(ROOT), *args], cwd=ROOT, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def test_cli_append_inspect_verify_and_materialize_round_trip(tmp_path: Path) -> None:
    root = tmp_path / "state"; root.mkdir(); t = task()
    created = run_cli(root, "append", "--task-id", t, "--event-type", "task_created", "--payload-json", json.dumps({"candidate_ref": "candidate", "base_sha": BASE, "admitted_scope_digest": "sha256:scope"}), "--recorded-at", "2026-08-04T00:00:00+00:00")
    assert created.returncode == 0, created.stdout + created.stderr
    lease = run_cli(root, "append", "--task-id", t, "--event-type", "authority_lease_bound", "--payload-json", '{"lease_id":"l1","scope_digest":"sha256:scope"}', "--recorded-at", "2026-08-04T00:00:01+00:00")
    assert lease.returncode == 0
    inspect = run_cli(root, "inspect", "--task-id", t)
    assert json.loads(inspect.stdout)["last_valid_sequence"] == 2
    verify = run_cli(root, "verify", "--task-id", t)
    assert verify.returncode == 0
    out = root / "snapshot.json"
    materialize = run_cli(root, "materialize", "--task-id", t, "--output", str(out))
    assert materialize.returncode == 0
    assert json.loads(out.read_text())["task_id"] == t


def test_cli_integrity_failure_returns_nonzero(tmp_path: Path) -> None:
    root = tmp_path / "state"; root.mkdir(); t = task()
    assert run_cli(root, "append", "--task-id", t, "--event-type", "task_created", "--payload-json", json.dumps({"candidate_ref": "candidate", "base_sha": BASE}), "--recorded-at", "2026-08-04T00:00:00+00:00").returncode == 0
    path = mtj.journal_path_for(root, t, repo_root=ROOT)
    row = json.loads(path.read_text())
    row["payload"]["candidate_ref"] = "mutated"
    path.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    verify = run_cli(root, "verify", "--task-id", t)
    assert verify.returncode != 0
    assert json.loads(verify.stdout)["integrity_status"] == "journal_digest_mismatch"
