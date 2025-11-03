import json
from pathlib import Path

from scripts.migrate_embeddings import migrate_embeddings


def _write_fragments(path: Path, fragments: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for fragment in fragments:
            handle.write(json.dumps(fragment) + "\n")


def test_migrate_embeddings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    fragments_path = tmp_path / "glow" / "memory" / "fragments.jsonl"
    fragments = [{"id": 1, "text": "hello world"}, {"id": 2, "text": "another"}]
    _write_fragments(fragments_path, fragments)

    report = migrate_embeddings(dry_run=True, batch_size=1)
    assert report["pending"] == 2
    data = fragments_path.read_text(encoding="utf-8")
    assert "embedding" not in data

    report = migrate_embeddings(dry_run=False, batch_size=2)
    assert report["migrated"] == 2
    rows = [json.loads(line) for line in fragments_path.read_text(encoding="utf-8").splitlines() if line]
    assert all("embedding" in row for row in rows)
