# mypy: disable-error-code="no-untyped-def,no-untyped-call,var-annotated,dict-item"
"""Bounded source manifest adapters for the world-state board."""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from sentientos.world_state_board import WorldStateBoardBuilder, WorldStateSourceKind, digest

@dataclass(frozen=True)
class SourceDeclaration:
    source_id:str; source_kind:str; path:Path|None=None; record:Mapping[str,Any]|None=None; required:bool=False; digest:str|None=None

class WorldStateSourceManifestError(ValueError): pass

def _inside(path:Path, roots:Sequence[Path])->bool:
    resolved=path.resolve()
    return any(resolved == r.resolve() or r.resolve() in resolved.parents for r in roots)

def load_manifest(declarations:Sequence[SourceDeclaration], *, allowed_roots:Sequence[Path], max_source_count:int=64, max_artifact_size:int=1048576)->list[dict[str,Any]]:
    if len(declarations)>max_source_count: raise WorldStateSourceManifestError("maximum source count exceeded")
    seen:dict[tuple[str,str],dict[str,Any]]={}; out=[]
    allowed=tuple(Path(r).resolve() for r in allowed_roots)
    for d in declarations:
        if d.source_kind not in {k.value for k in WorldStateSourceKind}: raise WorldStateSourceManifestError(f"unsupported source kind: {d.source_kind}")
        if d.path is not None:
            p=Path(d.path)
            if ".." in p.parts: raise WorldStateSourceManifestError("traversal rejected")
            if not _inside(p, allowed): raise WorldStateSourceManifestError("symlink or path escape rejected")
            if not p.exists():
                if d.required: raise WorldStateSourceManifestError("required source missing")
                continue
            if p.stat().st_size>max_artifact_size: raise WorldStateSourceManifestError("source oversized")
            try: raw=p.read_bytes(); rec=json.loads(raw.decode())
            except Exception as exc: raise WorldStateSourceManifestError(f"malformed source: {exc}") from exc
            actual=digest(rec)
        elif d.record is not None:
            rec=dict(d.record); actual=digest(rec)
        else:
            if d.required: raise WorldStateSourceManifestError("required source missing")
            continue
        if d.digest and d.digest!=actual: rec=dict(rec); rec["digest"]=d.digest
        rec.setdefault("source_id",d.source_id); rec.setdefault("source_kind",d.source_kind); rec.setdefault("required",d.required)
        key=(d.source_id, actual)
        if key in seen: continue
        seen[key]=rec; out.append(rec)
    return out

def build_snapshot_from_manifest(declarations:Sequence[SourceDeclaration], *, allowed_roots:Sequence[Path], **kwargs:Any):
    records=load_manifest(declarations, allowed_roots=allowed_roots, max_source_count=kwargs.get("max_source_count",64), max_artifact_size=kwargs.get("max_artifact_size",1048576))
    return WorldStateBoardBuilder(allowed_roots=allowed_roots, max_source_count=kwargs.get("max_source_count",64), max_artifact_size=kwargs.get("max_artifact_size",1048576), clock=kwargs.get("clock")).build(records)
