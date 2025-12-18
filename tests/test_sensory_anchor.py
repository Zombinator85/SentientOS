import json
from pathlib import Path

from sentientos.perception.sensory_anchor import anchor_events, load_fragments


def test_sensory_anchors_written(tmp_path: Path) -> None:
    fragments_dir = tmp_path / "glow" / "fragments"
    fragments_dir.mkdir(parents=True)
    fragment_file = fragments_dir / "001.jsonl"
    fragments = [
        {"id": "m1", "content": "crystal lattice glows"},
        {"id": "m2", "content": "horizon signal expands"},
    ]
    fragment_file.write_text("\n".join(json.dumps(f) for f in fragments), encoding="utf-8")

    perception_events = [
        {"id": "evt-1", "description": "glow from the crystal horizon"},
    ]
    anchors_path = tmp_path / "integration" / "anchors.jsonl"

    anchors = anchor_events(perception_events, fragments_dir, anchors_path)

    assert len(anchors) == 1
    assert anchors[0].fragment_path == str(fragment_file)
    assert perception_events[0]["anchored_to"] == str(fragment_file)

    written = anchors_path.read_text(encoding="utf-8").strip().splitlines()
    assert written
    payload = json.loads(written[0])
    assert payload["event"]["id"] == "evt-1"
    assert payload["fragment_path"].endswith("001.jsonl")

    loaded_fragments = load_fragments(fragments_dir)
    assert len(loaded_fragments) == 2
