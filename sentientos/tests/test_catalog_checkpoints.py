from __future__ import annotations

from pathlib import Path

from sentientos.signed_rollups import maybe_sign_catalog_checkpoint


def test_catalog_checkpoint_signing(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_SIGN_CATALOG_CHECKPOINT", "1")
    monkeypatch.setenv("SENTIENTOS_ROLLUP_SIGNING", "hmac-test")
    (tmp_path / "pulse").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pulse/artifact_catalog.jsonl").write_text('{"id":"x"}\n', encoding="utf-8")

    payload = maybe_sign_catalog_checkpoint(tmp_path)

    assert payload is not None
    assert payload["catalog_path"] == "pulse/artifact_catalog.jsonl"
    assert (tmp_path / "glow/forge/catalog_checkpoints/checkpoints_index.jsonl").exists()
