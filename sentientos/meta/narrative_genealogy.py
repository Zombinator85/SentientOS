from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping


class NarrativeGenealogy:
    """Trace lineage for narrative artifacts and decisions."""

    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.genealogy_path = self.workspace / "genealogy_chain.jsonl"

    def trace_artifact(
        self,
        artifact: str | Path,
        *,
        origin_chain: Iterable[Mapping[str, object]] | None = None,
        daemon: str | Mapping[str, object] | None = None,
        reflex: str | Mapping[str, object] | None = None,
        precedent: str | Mapping[str, object] | None = None,
        perception: str | Mapping[str, object] | None = None,
        user_input: str | Mapping[str, object] | None = None,
    ) -> dict:
        chain = list(origin_chain or [])
        chain.extend(
            filter(
                None,
                [
                    self._normalize("daemon", daemon),
                    self._normalize("reflex", reflex),
                    self._normalize("precedent", precedent),
                    self._normalize("perception", perception),
                    self._normalize("request", user_input),
                ],
            )
        )

        record = {"artifact": str(artifact), "origin_chain": chain}
        self._append_jsonl(self.genealogy_path, record)
        return record

    def load_genealogy(self) -> list[dict]:
        entries: list[dict] = []
        if not self.genealogy_path.exists():
            return entries
        with self.genealogy_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, Mapping):
                    entries.append(dict(parsed))
        return entries

    def _normalize(self, default_type: str, value: str | Mapping[str, object] | None) -> dict | None:
        if value is None:
            return None
        if isinstance(value, Mapping):
            source = value.get("source") or value.get("id") or value.get("name")
            if not source:
                return None
            result = {"source": source, "type": value.get("type", default_type)}
            extra = {k: v for k, v in value.items() if k not in {"source", "type"}}
            result.update(extra)
            return result
        return {"source": str(value), "type": default_type}

    def _append_jsonl(self, path: Path, row: Mapping[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


__all__ = ["NarrativeGenealogy"]
