import json
from hashlib import sha256
from pathlib import Path

import pytest

from hf_intake import classifier, discovery, escrow, manifest


class DummyApi:
    def __init__(self, download_path: Path) -> None:
        self.download_path = download_path

    def list_models(self, **_: dict):  # pragma: no cover - not used in tests
        raise NotImplementedError


def test_escrow_artifact_hash_anchored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    download_path = tmp_path / "download.gguf"
    payload = b"deterministic gguf payload"
    download_path.write_bytes(payload)

    monkeypatch.setattr(escrow, "hf_hub_download", lambda *_, **__: str(download_path))

    candidate = discovery.CandidateModel(
        repo_id="meta-llama/Llama-3-8B-Instruct",
        revision="abc123",
        license_id="meta-llama",
        gguf_files=["model-q4.gguf"],
        license_text="license",
        model_card="# card",
    )

    result = escrow.escrow_artifact(candidate, "model-q4.gguf", tmp_path / "escrow")
    assert result.artifact_path.name.startswith("model-q4-"), "filename must be hash anchored"
    checksum_path = result.artifact_path.with_suffix(result.artifact_path.suffix + ".sha256")
    assert checksum_path.exists()
    recorded = checksum_path.read_text(encoding="utf-8").split()[0]
    assert recorded == sha256(payload).hexdigest()


def test_manifest_generation_and_validation(tmp_path: Path) -> None:
    escrow_root = tmp_path / "escrow" / "sample"
    escrow_root.mkdir(parents=True)
    content = b"sample gguf"
    checksum = sha256(content).hexdigest()
    artifact_name = f"demo-q4-{checksum}.gguf"
    artifact_path = escrow_root / artifact_name
    artifact_path.write_bytes(content)
    (artifact_path.with_suffix(artifact_path.suffix + ".sha256")).write_text(
        f"{checksum}  {artifact_name}\n", encoding="utf-8"
    )
    (escrow_root / "LICENSE.txt").write_text("apache-2.0", encoding="utf-8")
    (escrow_root / "MODEL_CARD.md").write_text("# card", encoding="utf-8")
    source = {
        "repo_id": "demo/model",
        "revision": "1234",
        "license": "apache-2.0",
        "artifact": artifact_name,
        "priority": 2,
        "base_url": "https://models.sentientos.org",
        "id": "demo-q4",
    }
    (escrow_root / "SOURCE.json").write_text(json.dumps(source, indent=2), encoding="utf-8")

    manifest_path = tmp_path / "manifests" / "manifest-2025-01-01.json"
    data = manifest.generate_manifest(tmp_path / "escrow", manifest_path, manifest_version="2025-01-01")
    assert data["manifest_version"] == "2025-01-01"
    manifest.validate_manifest(manifest_path)

    with manifest_path.open(encoding="utf-8") as handle:
        stored = json.load(handle)
    assert stored["models"][0]["artifact"]["sha256"] == checksum
    assert stored["models"][0]["artifact"]["escrow_path"] == str(artifact_path)


def test_classifier_rejects_ambiguous_quantization(tmp_path: Path) -> None:
    artifact = tmp_path / "model-unknown.gguf"
    artifact.write_bytes(b"noop")
    with pytest.raises(classifier.ClassificationError):
        classifier.classify(artifact, artifact.stat().st_size)
