from pathlib import Path

from sentientos.narrative.narrative_sentinel import NarrativeSentinel


def test_digest_health_flags(tmp_path: Path) -> None:
    digests_dir = tmp_path / "digests"
    digests_dir.mkdir()
    digest_path = digests_dir / "2025-12-16.md"

    content = " ".join(["echo" for _ in range(60)]) + " symbol Starforge horizon " + "signal " * 70
    digest_path.write_text(content, encoding="utf-8")

    sentinel = NarrativeSentinel(digests_dir, vetted_symbols={"echo", "signal", "horizon"}, verbosity_thresholds=(20, 80))
    reports = sentinel.scan()
    assert len(reports) == 1
    report = reports[0]

    assert report.digest == "2025-12-16.md"
    assert report.symbol_creep is True
    assert report.verbosity == "high"
    assert report.motif_density > 0.5

    actions = sentinel.escalate(reports)
    assert actions == [
        {"digest": "2025-12-16.md", "action": "notify_governance_council", "reason": "severe narrative drift"}
    ]
