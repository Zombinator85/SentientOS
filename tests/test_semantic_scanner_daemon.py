from sentientos.ethics import SemanticScannerDaemon


def test_semantic_scanner_flags_repeated_toxic_motifs(tmp_path):
    daemon = SemanticScannerDaemon(
        ["poison", "betrayal"],
        escalation_threshold=0.1,
        repeat_threshold=2,
        alert_log=tmp_path / "alerts.jsonl",
    )
    report = daemon.scan([
        "calm reflective entry",
        "a whisper of poison slipping in",
        "poison motif repeats and betrayal echoes",
    ])

    assert report["covenant_alert"] is True
    assert "poison" in report["cascade_alerts"]
    alert_log = (tmp_path / "alerts.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert alert_log
