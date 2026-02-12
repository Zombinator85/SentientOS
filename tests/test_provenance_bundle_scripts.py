from __future__ import annotations

import json
import tarfile
from pathlib import Path

from scripts.export_test_provenance_bundle import main as export_main
from scripts.provenance_hash_chain import HASH_ALGO, compute_provenance_hash
from scripts.verify_test_provenance_bundle import main as verify_main


def _write_snapshot(path: Path, timestamp: str, prev_hash: str | None, intent: str = "normal") -> str:
    payload = {
        "timestamp": timestamp,
        "run_intent": intent,
        "tests_executed": 10,
        "tests_passed": 10,
        "skip_rate": 0.0,
        "xfail_rate": 0.0,
        "hash_algo": HASH_ALGO,
        "prev_provenance_hash": prev_hash,
    }
    payload["provenance_hash"] = compute_provenance_hash(payload, prev_hash)
    path.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")
    return str(payload["provenance_hash"])


def test_export_and_verify_bundle_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    provenance_dir = tmp_path / "glow" / "test_runs" / "provenance"
    bundles_dir = tmp_path / "glow" / "test_runs" / "bundles"
    provenance_dir.mkdir(parents=True)

    prev = "GENESIS"
    prev = _write_snapshot(provenance_dir / "a.json", "2026-01-01T00:00:00+00:00", prev)
    prev = _write_snapshot(provenance_dir / "b.json", "2026-01-01T00:00:01+00:00", prev)
    _write_snapshot(provenance_dir / "c.json", "2026-01-01T00:00:02+00:00", prev)

    assert export_main(["--dir", str(provenance_dir), "--out", str(bundles_dir), "--last", "2"]) == 0
    bundles = sorted(bundles_dir.glob("*.tar.gz"))
    assert len(bundles) == 1

    verification_out = tmp_path / "bundle_verification.json"
    assert verify_main([str(bundles[0]), "--output", str(verification_out)]) == 0

    report = json.loads(verification_out.read_text(encoding="utf-8"))
    assert report["verified"] is True
    assert report["chain_ok"] is True


def test_verify_bundle_detects_tamper(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    provenance_dir = tmp_path / "glow" / "test_runs" / "provenance"
    bundles_dir = tmp_path / "glow" / "test_runs" / "bundles"
    provenance_dir.mkdir(parents=True)

    prev = "GENESIS"
    prev = _write_snapshot(provenance_dir / "a.json", "2026-01-01T00:00:00+00:00", prev)
    _write_snapshot(provenance_dir / "b.json", "2026-01-01T00:00:01+00:00", prev)

    assert export_main(["--dir", str(provenance_dir), "--out", str(bundles_dir), "--last", "2"]) == 0
    bundle_path = sorted(bundles_dir.glob("*.tar.gz"))[0]

    tamper_dir = tmp_path / "tamper"
    tamper_dir.mkdir(parents=True)
    with tarfile.open(bundle_path, mode="r:gz") as archive:
        archive.extractall(tamper_dir)

    snapshot_path = tamper_dir / "provenance" / "b.json"
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    payload["tests_passed"] = 0
    snapshot_path.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")

    tampered_bundle = tmp_path / "tampered.tar.gz"
    with tarfile.open(tampered_bundle, mode="w:gz") as archive:
        for file_path in sorted(path for path in tamper_dir.rglob("*") if path.is_file()):
            archive.add(file_path, arcname=file_path.relative_to(tamper_dir))

    verification_out = tmp_path / "tampered_bundle_verification.json"
    assert verify_main([str(tampered_bundle), "--output", str(verification_out)]) == 1

    report = json.loads(verification_out.read_text(encoding="utf-8"))
    assert report["verified"] is False
    assert any("payload hash mismatch" in issue for issue in report["errors"])
