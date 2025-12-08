from sentientos.innerworld.autobio_compressor import AutobiographicalCompressor


def test_autobio_compression_and_fifo():
    compressor = AutobiographicalCompressor(max_entries=2)
    chapters = [
        {"qualia_theme": "stable", "ethical_theme": "low", "metacog_theme": "low"},
        {"qualia_theme": "shifting", "ethical_theme": "moderate", "metacog_theme": "moderate"},
    ]
    reflection = {"insights": ["insight-one", "insight-two", "insight-three", "extra"]}
    identity = {"core_themes": {"qualia": "shifting"}}

    entry = compressor.compress(chapters=chapters, reflection_summary=reflection, identity_summary=identity)
    compressor.record(entry)

    assert entry["dominant_themes"]["qualia"] == "shifting"
    assert entry["core_insights"] == ["insight-one", "insight-two", "insight-three"]
    assert entry["identity_shift"] == "shifting"

    second_entry = compressor.compress(chapters=chapters[:1], reflection_summary={}, identity_summary={})
    compressor.record(second_entry)
    compressor.record({"entry_id": 99})

    entries = compressor.get_entries()
    assert len(entries) == 2
    assert entries[0]["entry_id"] == second_entry["entry_id"]
    assert entries[1]["entry_id"] == 99


def test_autobio_deterministic_ordering():
    compressor = AutobiographicalCompressor(max_entries=3)
    chapters = [
        {"qualia_theme": "volatile", "ethical_theme": "high", "metacog_theme": "high"},
        {"qualia_theme": "volatile", "ethical_theme": "high", "metacog_theme": "high"},
    ]

    first = compressor.compress(chapters=chapters, reflection_summary={}, identity_summary={})
    second = compressor.compress(
        chapters=[{"qualia_theme": "volatile", "ethical_theme": "high", "metacog_theme": "high"}],
        reflection_summary={},
        identity_summary={},
    )

    assert first["dominant_themes"] == second["dominant_themes"]
