from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import hints only
    from huggingface_hub import HfApi, hf_hub_download

hf_hub_download = None
HfApi = None

from hf_intake.discovery import CandidateModel, DiscoveryError, write_source_record


class EscrowError(RuntimeError):
    """Raised when escrow invariants are violated."""


@dataclass
class EscrowedArtifact:
    model_id: str
    artifact_path: Path
    sha256: str
    size_bytes: int


SAFE_SUFFIX = ".gguf"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_model_dir_name(repo_id: str) -> str:
    return repo_id.replace("/", "__")


def escrow_artifact(
    candidate: CandidateModel, artifact_filename: str, escrow_root: Path, api: Optional["HfApi"] = None
) -> EscrowedArtifact:
    if not artifact_filename.lower().endswith(SAFE_SUFFIX):
        raise EscrowError(f"Artifact {artifact_filename} is not a GGUF file")

    client = api
    if client is None:
        from huggingface_hub import HfApi as _HfApi

        client = _HfApi()
    dest_dir = escrow_root / _safe_model_dir_name(candidate.repo_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    downloader = hf_hub_download
    if downloader is None:
        from huggingface_hub import hf_hub_download as _hf_hub_download

        downloader = _hf_hub_download

    try:
        download_path = Path(
            downloader(
                candidate.repo_id,
                filename=artifact_filename,
                revision=candidate.revision,
                repo_type="model",
                token=None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        raise EscrowError(f"Failed to download {artifact_filename} from {candidate.repo_id}@{candidate.revision}: {exc}") from exc

    sha256 = _sha256_file(download_path)
    size_bytes = download_path.stat().st_size
    escrow_name = f"{Path(artifact_filename).stem}-{sha256}{SAFE_SUFFIX}"
    escrow_path = dest_dir / escrow_name
    if escrow_path.exists():
        raise EscrowError(f"Escrow target already exists: {escrow_path}")

    shutil.copyfile(download_path, escrow_path)
    checksum_path = escrow_path.with_suffix(escrow_path.suffix + ".sha256")
    checksum_path.write_text(f"{sha256}  {escrow_path.name}\n", encoding="utf-8")

    license_path = dest_dir / "LICENSE.txt"
    if license_path.exists():
        raise EscrowError(f"License already recorded for {candidate.repo_id}")
    license_path.write_text(candidate.license_text, encoding="utf-8")

    card_path = dest_dir / "MODEL_CARD.md"
    if card_path.exists():
        raise EscrowError(f"Model card already recorded for {candidate.repo_id}")
    card_path.write_text(candidate.model_card, encoding="utf-8")

    source_path = dest_dir / "SOURCE.json"
    if source_path.exists():
        raise EscrowError(f"Source record already exists for {candidate.repo_id}")
    write_source_record(source_path, candidate, escrow_path.name)

    return EscrowedArtifact(
        model_id=_safe_model_dir_name(candidate.repo_id),
        artifact_path=escrow_path,
        sha256=sha256,
        size_bytes=size_bytes,
    )
