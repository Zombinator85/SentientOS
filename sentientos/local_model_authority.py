from __future__ import annotations

import hashlib, json, os, tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .config import ModelCandidate, ModelConfig, load_model_config
from .local_model import LocalModel
from .storage import get_data_root

SUPPORTED_ENGINES = {"llama_cpp", "transformers", "echo", "null", "auto"}
PROVIDER_ENGINES = {"openai", "huggingface", "hf_inference", "anthropic", "ollama_remote", "http", "https", "api"}
PRODUCTION_ENGINES = {"llama_cpp", "transformers"}
SIMULATION_ENGINES = {"echo", "null"}
MAX_CANDIDATES = 32
MAX_METADATA_BYTES = 128 * 1024
AUTHORITY_SCHEMA_VERSION = "local_model_authority_map.v1"


def _canon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest_payload(obj: Any) -> str:
    return hashlib.sha256(_canon(obj)).hexdigest()


def stream_sha256(path: Path) -> tuple[str, int]:
    h = hashlib.sha256(); size = 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            size += len(chunk); h.update(chunk)
    return h.hexdigest(), size


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        Path(tmp).replace(path)
    finally:
        try: Path(tmp).unlink()
        except FileNotFoundError: pass


@dataclass(frozen=True)
class LocalModelAuthorityRecord:
    model_id: str
    engine: str
    name: str
    semantic_artifact_identity: str
    model_content_sha256: str | None
    artifact_size_bytes: int | None
    sidecar_metadata_digest: str | None
    configuration_digest: str
    max_context_tokens: int
    generation_ceilings: Mapping[str, Any]
    local_files_only: bool
    custom_model_code_posture: str
    custom_model_code_opt_in: bool
    allowed_invocation_purposes: tuple[str, ...]
    provider_network_posture: str
    tool_posture: str
    memory_posture: str
    action_posture: str
    runtime_eligibility_status: str
    reason_codes: tuple[str, ...]
    disposition: str
    proof_references: tuple[str, ...]
    observed_metadata: Mapping[str, Any] = field(default_factory=dict)

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "name": self.name,
            "semantic_artifact_identity": self.semantic_artifact_identity,
            "model_content_sha256": self.model_content_sha256,
            "artifact_size_bytes": self.artifact_size_bytes,
            "sidecar_metadata_digest": self.sidecar_metadata_digest,
            "configuration_digest": self.configuration_digest,
            "max_context_tokens": self.max_context_tokens,
            "generation_ceilings": dict(self.generation_ceilings),
            "local_files_only": self.local_files_only,
            "custom_model_code_posture": self.custom_model_code_posture,
            "custom_model_code_opt_in": self.custom_model_code_opt_in,
            "allowed_invocation_purposes": list(self.allowed_invocation_purposes),
            "provider_network_posture": self.provider_network_posture,
            "tool_posture": self.tool_posture,
            "memory_posture": self.memory_posture,
            "action_posture": self.action_posture,
            "runtime_eligibility_status": self.runtime_eligibility_status,
            "reason_codes": list(self.reason_codes),
            "disposition": self.disposition,
            "proof_references": list(self.proof_references),
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self.semantic_payload()
        payload["model_id"] = self.model_id
        payload["observed_metadata"] = dict(self.observed_metadata)
        return payload


@dataclass(frozen=True)
class LocalModelAuthorityMap:
    records: tuple[LocalModelAuthorityRecord, ...]
    map_id: str
    map_digest: str
    generated_at: str
    summary: Mapping[str, Any]

    def semantic_payload(self) -> dict[str, Any]:
        return {"schema_version": AUTHORITY_SCHEMA_VERSION, "records": [r.to_dict() for r in self.records]}

    def to_dict(self) -> dict[str, Any]:
        p = self.semantic_payload(); p.update({"map_id": self.map_id, "map_digest": self.map_digest, "generated_at": self.generated_at, "summary": dict(self.summary)})
        return p

    def eligible_record(self, purpose: str) -> LocalModelAuthorityRecord | None:
        for rec in self.records:
            if rec.runtime_eligibility_status == "eligible" and purpose in rec.allowed_invocation_purposes:
                return rec
        return None


def _safe_under(path: Path, roots: Sequence[Path]) -> tuple[bool, Path | None]:
    try: resolved = path.resolve(strict=False)
    except OSError: return False, None
    for root in roots:
        try:
            rr = root.resolve(strict=True)
        except OSError:
            continue
        try:
            resolved.relative_to(rr)
            return True, resolved
        except ValueError:
            continue
    return False, resolved


def _metadata(candidate: ModelCandidate) -> tuple[dict[str, Any], str | None, list[str]]:
    if candidate.path is None: return {}, None, []
    meta = LocalModel._candidate_meta_path(candidate.path)
    if not meta.exists(): return {}, None, []
    try:
        if meta.stat().st_size > MAX_METADATA_BYTES: return {}, None, ["metadata_oversized"]
        raw = meta.read_bytes(); return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest(), []
    except Exception:
        return {}, None, ["metadata_malformed"]


def build_local_model_authority_map(config: ModelConfig | None = None, *, allowed_roots: Sequence[Path] | None = None) -> LocalModelAuthorityMap:
    config = config or load_model_config()
    roots = tuple(Path(r) for r in (allowed_roots or [get_data_root(), *(c.path.parent for c in config.candidates if c.path is not None and c.path.is_absolute())]))
    records: list[LocalModelAuthorityRecord] = []
    seen: dict[str, str] = {}
    if len(config.candidates) > MAX_CANDIDATES:
        candidates = config.candidates[:MAX_CANDIDATES]
        excess = True
    else:
        candidates = config.candidates; excess = False
    for idx, candidate in enumerate(candidates):
        reasons: list[str] = []
        engine = candidate.engine or config.default_engine
        if engine == "auto":
            engine = LocalModel._guess_engine(candidate)
        engine_l = engine.lower()
        metadata, sidecar_digest, meta_reasons = _metadata(candidate); reasons.extend(meta_reasons)
        if engine_l in PROVIDER_ENGINES: reasons.append("provider_engine_blocked")
        if engine_l not in SUPPORTED_ENGINES: reasons.append("unsupported_engine")
        content_digest = None; artifact_size = None; semantic_artifact = "pathless_model"
        if candidate.path is None:
            if engine_l not in {"null", "echo", "transformers"}: reasons.append("artifact_path_missing")
        else:
            if ".." in candidate.path.parts: reasons.append("path_traversal_blocked")
            ok, resolved = _safe_under(candidate.path, roots)
            if not ok: reasons.append("artifact_root_escape")
            if resolved is not None and resolved.is_symlink(): reasons.append("symlink_escape_blocked")
            if not candidate.path.exists(): reasons.append("artifact_missing")
            elif candidate.path.is_file():
                try:
                    content_digest, artifact_size = stream_sha256(candidate.path)
                    expected = candidate.options.get("sha256") or metadata.get("sha256")
                    if expected and str(expected).lower() != content_digest: reasons.append("content_digest_mismatch")
                except OSError:
                    reasons.append("artifact_unreadable")
            elif candidate.path.is_dir():
                # Directory transformers models use metadata/config digest, not recursive heavy hashing.
                artifact_size = 0
                content_digest = digest_payload({"directory_model": metadata, "name": candidate.display_name()})
            semantic_artifact = f"sha256:{content_digest}" if content_digest else f"unverified:{candidate.display_name()}"
        custom = bool(candidate.options.get("allow_model_code_execution") or metadata.get("allow_model_code_execution"))
        cfg_payload = {"engine": engine_l, "options": {k: v for k, v in sorted(candidate.options.items()) if k != "path"}, "max_context_tokens": config.max_context_tokens, "generation": config.generation.as_kwargs()}
        cfg_digest = digest_payload(cfg_payload)
        if excess: reasons.append("candidate_count_exceeded")
        disposition = "simulation" if engine_l in SIMULATION_ENGINES else "production_candidate"
        eligible = not reasons and engine_l in PRODUCTION_ENGINES
        if engine_l in SIMULATION_ENGINES and not reasons:
            reasons.append("simulation_backend_not_production_intelligence")
        purposes = ("local_user_chat",) if engine_l in SIMULATION_ENGINES else ("local_user_chat", "genesis_proposal_advice")
        record_seed = {"engine": engine_l, "semantic_artifact_identity": semantic_artifact, "configuration_digest": cfg_digest, "sidecar_metadata_digest": sidecar_digest}
        model_id = "lma-" + digest_payload(record_seed)[:24]
        if semantic_artifact in seen and seen[semantic_artifact] != cfg_digest: reasons.append("conflicting_duplicate_semantic_model")
        seen[semantic_artifact] = cfg_digest
        status = "eligible" if eligible else "blocked" if any(r for r in reasons if r not in {"simulation_backend_not_production_intelligence"}) else "degraded"
        rec = LocalModelAuthorityRecord(model_id=model_id, engine=engine_l, name=str(candidate.name or metadata.get("name") or candidate.display_name()), semantic_artifact_identity=semantic_artifact, model_content_sha256=content_digest, artifact_size_bytes=artifact_size, sidecar_metadata_digest=sidecar_digest, configuration_digest=cfg_digest, max_context_tokens=config.max_context_tokens, generation_ceilings=config.generation.as_kwargs(), local_files_only=True, custom_model_code_posture="explicit_opt_in" if custom else "disabled", custom_model_code_opt_in=custom, allowed_invocation_purposes=purposes, provider_network_posture="blocked_local_files_only", tool_posture="blocked", memory_posture="blocked", action_posture="blocked", runtime_eligibility_status=status, reason_codes=tuple(reasons or ["eligible_local_model"]), disposition=disposition, proof_references=("sentientos/local_model.py", "sentientos/local_model_authority.py"), observed_metadata={"candidate_index": idx, "path_observed": str(candidate.path) if candidate.path else None, "observed_at": datetime.now(timezone.utc).isoformat()})
        records.append(rec)
    semantic = {"schema_version": AUTHORITY_SCHEMA_VERSION, "records": [r.to_dict() for r in records]}
    md = digest_payload(semantic); mid = "lmam-" + md[:24]
    summary = {"eligible_count": sum(r.runtime_eligibility_status == "eligible" for r in records), "blocked_count": sum(r.runtime_eligibility_status == "blocked" for r in records), "degraded_count": sum(r.runtime_eligibility_status == "degraded" for r in records), "provider_network_posture": "blocked"}
    return LocalModelAuthorityMap(records=tuple(records), map_id=mid, map_digest=md, generated_at=datetime.now(timezone.utc).isoformat(), summary=summary)


def validate_authority_map(payload: Mapping[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if payload.get("schema_version") != AUTHORITY_SCHEMA_VERSION: reasons.append("schema_version_invalid")
    records = payload.get("records")
    if not isinstance(records, list): reasons.append("records_missing")
    semantic = {"schema_version": payload.get("schema_version"), "records": records if isinstance(records, list) else []}
    expected = digest_payload(semantic)
    if payload.get("map_digest") != expected: reasons.append("map_digest_mismatch")
    if payload.get("map_id") != "lmam-" + expected[:24]: reasons.append("map_id_mismatch")
    for rec in records if isinstance(records, list) else []:
        seed = {"engine": rec.get("engine"), "semantic_artifact_identity": rec.get("semantic_artifact_identity"), "configuration_digest": rec.get("configuration_digest"), "sidecar_metadata_digest": rec.get("sidecar_metadata_digest")}
        if rec.get("model_id") != "lma-" + digest_payload(seed)[:24]: reasons.append("model_id_mismatch")
    return not reasons, reasons


def render_authority_map_markdown(authority_map: LocalModelAuthorityMap) -> str:
    lines = ["# Local Model Authority Map", "", f"Map ID: `{authority_map.map_id}`", f"Digest: `{authority_map.map_digest}`", "", "| Model | Engine | Status | Purposes | Posture |", "| --- | --- | --- | --- | --- |"]
    for r in authority_map.records:
        lines.append(f"| `{r.model_id}` | {r.engine} | {r.runtime_eligibility_status} | {', '.join(r.allowed_invocation_purposes)} | {r.provider_network_posture}; tools={r.tool_posture}; memory={r.memory_posture}; action={r.action_posture} |")
    return "\n".join(lines) + "\n"
