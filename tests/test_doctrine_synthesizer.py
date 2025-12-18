from sentientos.cathedral import DoctrineSynthesizer


def test_doctrine_synthesizer_highlights_divergence(tmp_path):
    synthesizer = DoctrineSynthesizer(candidate_log=tmp_path / "candidates.jsonl")
    peer_doctrines = [
        {"safety": "strict", "sharing": "open"},
        {"safety": "strict", "sharing": "open"},
        {"safety": "balanced", "sharing": "closed"},
    ]

    candidate = synthesizer.synthesize(peer_doctrines)

    assert candidate["canonical"]["safety"] == "strict"
    assert candidate["peer_count"] == 3
    assert candidate["divergences"]
    log_lines = (tmp_path / "candidates.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert log_lines
