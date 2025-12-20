import json
from pathlib import Path

import pytest

from hf_intake import manifest


MANIFEST_PATH = Path("manifests/manifest-v1.json")


def test_manifest_v1_validates() -> None:
    manifest.validate_manifest(MANIFEST_PATH)


def test_manifest_v1_rejects_missing_artifact(tmp_path: Path) -> None:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    data["models"][0]["artifact"]["escrow_path"] = str(tmp_path / "missing.gguf")
    broken = tmp_path / "manifest.json"
    broken.write_text(json.dumps(data, indent=2), encoding="utf-8")
    with pytest.raises(manifest.ManifestError):
        manifest.validate_manifest(broken)


def test_manifest_v1_rejects_hf_urls(tmp_path: Path) -> None:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    data["models"][0]["artifact"]["urls"] = ["https://huggingface.co/bad/gguf"]
    broken = tmp_path / "manifest.json"
    broken.write_text(json.dumps(data, indent=2), encoding="utf-8")
    with pytest.raises(manifest.ManifestError):
        manifest.validate_manifest(broken)
