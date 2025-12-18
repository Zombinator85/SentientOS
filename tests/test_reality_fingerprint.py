from pathlib import Path

from sentientos.perception.reality_fingerprint import RealityFingerprinter


def test_reality_fingerprint_and_divergence(tmp_path: Path) -> None:
    fingerprinter = RealityFingerprinter(tmp_path)
    perceptions = [
        {"keywords": ["beacon", "pulse"], "timestamp": "2025-08-01T00:00:00Z", "identity": "alpha"},
        {"keywords": ["beacon", "trust"], "identity": "alpha"},
    ]

    fingerprint = fingerprinter.fingerprint_batch(perceptions)
    assert fingerprint["hash"]
    assert fingerprinter.fingerprint_path.exists()

    peer_fingerprint = {
        "summary": {"keywords": ["beacon", "signal"], "timestamp": "2025-08-01T00:00:00Z", "identity": ["alpha"]},
        "hash": "different",
    }

    divergence = fingerprinter.compare_fingerprints(fingerprint, peer_fingerprint, margin=0.2)
    assert divergence["triggered"] is True
    assert fingerprinter.divergence_path.exists()

    identical = fingerprinter.compare_fingerprints(fingerprint, fingerprint, margin=0.2)
    assert identical["triggered"] is False
