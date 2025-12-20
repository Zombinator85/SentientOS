from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from huggingface_hub import HfApi, hf_hub_download


ALLOWED_LICENSES = {
    "apache-2.0",
    "mit",
    "llama3",
    "llama-3",
    "llama-3.1",
    "llama-3.1-community",
    "meta-llama",
}
BLOCKED_LICENSE_TERMS = (
    "non-commercial",
    "noncommercial",
    "nc",
    "research-only",
    "research use only",
    "gated",
)


class DiscoveryError(RuntimeError):
    """Raised when a discovery or retrieval step fails."""


@dataclass
class CandidateModel:
    repo_id: str
    revision: str
    license_id: str
    gguf_files: List[str]
    license_text: str
    model_card: str

    def to_source_record(self, artifact_filename: str) -> dict:
        return {
            "repo_id": self.repo_id,
            "revision": self.revision,
            "license": self.license_id,
            "artifact": artifact_filename,
        }


def _is_permissive_license(license_id: Optional[str], allowed: Iterable[str]) -> bool:
    if not license_id:
        return False
    normalized = license_id.lower()
    if any(term in normalized for term in BLOCKED_LICENSE_TERMS):
        return False
    return normalized in {item.lower() for item in allowed}


def _load_file_text(repo_id: str, revision: str, filename: str, api: Optional[HfApi]) -> str:
    try:
        path = hf_hub_download(repo_id, filename=filename, revision=revision, repo_type="model", token=None)
    except Exception as exc:  # noqa: BLE001
        raise DiscoveryError(f"Unable to fetch {filename} for {repo_id}@{revision}: {exc}") from exc
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    if not text.strip():
        raise DiscoveryError(f"Empty {filename} for {repo_id}@{revision}")
    return text


def _resolve_license_text(repo_id: str, revision: str, api: Optional[HfApi]) -> str:
    for candidate in ("LICENSE", "LICENSE.txt", "LICENSE.md"):
        try:
            return _load_file_text(repo_id, revision, candidate, api)
        except DiscoveryError:
            continue
    raise DiscoveryError(f"Missing license file for {repo_id}@{revision}")


def _resolve_model_card(repo_id: str, revision: str, api: Optional[HfApi]) -> str:
    for candidate in ("README.md", "README.MD", "README.txt"):
        try:
            return _load_file_text(repo_id, revision, candidate, api)
        except DiscoveryError:
            continue
    raise DiscoveryError(f"Missing model card for {repo_id}@{revision}")


def discover_text_models(
    allowed_licenses: Sequence[str] = tuple(ALLOWED_LICENSES), api: Optional[HfApi] = None
) -> List[CandidateModel]:
    client = api or HfApi()
    candidates: List[CandidateModel] = []
    for info in client.list_models(filter="text-generation", full=True, sort="downloads"):
        if getattr(info, "private", False) or getattr(info, "gated", False):
            continue
        license_id = (info.cardData or {}).get("license") or info.license
        if not _is_permissive_license(license_id, allowed_licenses):
            continue
        if not info.sha:
            continue
        gguf_files = [s.rfilename for s in (info.siblings or []) if s.rfilename.lower().endswith(".gguf")]
        if not gguf_files:
            continue
        license_text = _resolve_license_text(info.modelId, info.sha, client)
        model_card = _resolve_model_card(info.modelId, info.sha, client)
        candidates.append(
            CandidateModel(
                repo_id=info.modelId,
                revision=info.sha,
                license_id=license_id or "unknown",
                gguf_files=sorted(gguf_files),
                license_text=license_text,
                model_card=model_card,
            )
        )
    if not candidates:
        raise DiscoveryError("No viable Hugging Face models discovered")
    return candidates


def write_source_record(target: Path, candidate: CandidateModel, artifact_filename: str) -> None:
    target.write_text(
        json.dumps(candidate.to_source_record(artifact_filename), indent=2, sort_keys=True),
        encoding="utf-8",
    )
