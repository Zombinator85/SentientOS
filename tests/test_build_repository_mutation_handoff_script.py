from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.build_repository_mutation_handoff import main


def test_cli_exit_codes_and_deterministic_outputs(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    proposal = tmp_path / "proposal.json"
    proposal.write_text(json.dumps({"proposal_id":"p|1", "status":"approved", "ledger_entry":"l", "approved_paths":["a.txt"], "approved_path_digests":{"a.txt": hashlib.sha256(b"x").hexdigest()}, "approved_source_revision":"abc", "summary":"line\nbreak"}), encoding="utf-8")
    out = tmp_path / "handoff.json"
    md = tmp_path / "handoff.md"
    assert main(["--proposal-json", str(proposal), "--repo-root", str(tmp_path), "--output", str(out), "--markdown-output", str(md), "--source-revision", "abc", "--summary"]) == 0
    first = out.read_text(encoding="utf-8")
    assert main(["--proposal-json", str(proposal), "--repo-root", str(tmp_path), "--output", str(out), "--markdown-output", str(md), "--source-revision", "abc", "--summary"]) == 0
    assert out.read_text(encoding="utf-8") == first
    assert "\\|" in md.read_text(encoding="utf-8") or "<br>" in md.read_text(encoding="utf-8")


def test_cli_returns_one_for_blocked_and_two_for_bad_input(tmp_path: Path) -> None:
    proposal = tmp_path / "proposal.json"
    proposal.write_text(json.dumps({"proposal_id":"p", "status":"pending", "ledger_entry":"l", "approved_paths":["missing.txt"], "approved_path_digests":{"missing.txt": hashlib.sha256(b"").hexdigest()}, "approved_source_revision":"abc"}), encoding="utf-8")
    assert main(["--proposal-json", str(proposal), "--repo-root", str(tmp_path), "--output", str(tmp_path / "out.json"), "--source-revision", "abc"]) == 1
    assert main(["--proposal-json", str(tmp_path / "nope.json"), "--repo-root", str(tmp_path), "--output", str(tmp_path / "out.json")]) == 2


def test_cli_emitted_digest_verifies_and_covers_revision_warning(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    proposal = tmp_path / "proposal.json"
    proposal.write_text(json.dumps({"proposal_id":"p", "status":"approved", "ledger_entry":"l", "approved_paths":["a.txt"], "approved_path_digests":{"a.txt": hashlib.sha256(b"x").hexdigest()}, "approved_source_revision":"abc"}), encoding="utf-8")
    out = tmp_path / "handoff.json"
    calls = []
    def fake_run(cmd, **kwargs):
        calls.append(tuple(cmd))
        class R:
            returncode = 1
            stdout = ""
        return R()
    monkeypatch.setattr("sentientos.repository_mutation_handoff.subprocess.run", fake_run)
    assert main(["--proposal-json", str(proposal), "--repo-root", str(tmp_path), "--output", str(out)]) == 1
    assert calls == [("git", "rev-parse", "HEAD")]
    payload = json.loads(out.read_text(encoding="utf-8"))
    from sentientos.repository_mutation_handoff import verify_repository_mutation_handoff_digest
    assert "observed_source_revision_unknown" in payload["warning_codes"]
    assert verify_repository_mutation_handoff_digest(payload)
    payload["warning_codes"].append("late")
    assert not verify_repository_mutation_handoff_digest(payload)
