from sentientos.narrative import NarrativeCompressor


def test_narrative_compressor_collapses_duplicates_and_builds_motifs():
    compressor = NarrativeCompressor()
    entries = [
        {"id": "a", "text": "Echoing the dawn", "tags": ["diary"]},
        {"id": "b", "text": "Echoing the dawn!!!", "tags": ["diary"]},
        {"id": "c", "text": "Signal rises with the dawn horizon", "tags": ["motif"]},
    ]

    result = compressor.compress(entries)

    assert len(result["canonical_entries"]) == 2
    assert "b" in result["omitted"]
    anchors_for_dawn = result["anchor_index"].get("dawn", [])
    assert "a" in anchors_for_dawn and "c" in anchors_for_dawn
    motifs = {item["motif"] for item in result["motifs"]}
    assert "dawn" in motifs
