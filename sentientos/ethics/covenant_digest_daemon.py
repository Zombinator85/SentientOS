from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping


class CovenantDigestDaemon:
    """Summarize doctrine-related events into weekly covenant digests."""

    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.digest_path = self.workspace / "covenant_digest.md"
        self.snapshot_path = self.workspace / "covenant_snapshot.json"

    def generate_digest(
        self,
        events: Iterable[Mapping[str, object]],
        *,
        doctrine_hash: str,
        changed_terms: Iterable[str] | None = None,
    ) -> dict:
        events_list = list(events)
        grouped = self._group_events(events_list)
        digest_content = self._render_digest(grouped, doctrine_hash, changed_terms)
        self.digest_path.write_text(digest_content, encoding="utf-8")

        snapshot = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "doctrine_hash": doctrine_hash,
            "changed_terms": list(changed_terms or []),
            "event_counts": {k: len(v) for k, v in grouped.items()},
        }
        self.snapshot_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        return {"digest_path": str(self.digest_path), "snapshot_path": str(self.snapshot_path), "summary": snapshot}

    def _group_events(self, events: Iterable[Mapping[str, object]]) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = {
            "violations": [],
            "proposals": [],
            "consent_deltas": [],
            "drift_audits": [],
        }
        for event in events:
            entry = dict(event)
            category = str(entry.get("category") or entry.get("type") or "misc")
            if "violation" in category:
                grouped["violations"].append(entry)
            elif "proposal" in category:
                grouped["proposals"].append(entry)
            elif "consent" in category:
                grouped["consent_deltas"].append(entry)
            elif "drift" in category:
                grouped["drift_audits"].append(entry)
            else:
                grouped.setdefault("misc", []).append(entry)
        return grouped

    def _render_digest(self, grouped: Mapping[str, list[dict]], doctrine_hash: str, changed_terms: Iterable[str] | None) -> str:
        lines = ["# Covenant Digest", "", f"Doctrine hash: {doctrine_hash}", ""]
        lines.append("## Violations caught")
        lines.extend(self._render_section(grouped.get("violations", [])))

        lines.append("\n## Proposals merged")
        lines.extend(self._render_section(grouped.get("proposals", [])))

        lines.append("\n## Consent deltas")
        lines.extend(self._render_section(grouped.get("consent_deltas", [])))

        lines.append("\n## Drift audits")
        lines.extend(self._render_section(grouped.get("drift_audits", [])))

        terms = list(changed_terms or [])
        lines.append("\n## Covenant snapshot")
        lines.append(f"Changed terms: {', '.join(terms) if terms else 'none'}")
        return "\n".join(lines).strip() + "\n"

    def _render_section(self, entries: list[Mapping[str, object]]) -> list[str]:
        if not entries:
            return ["- None recorded"]
        rendered: list[str] = []
        for entry in entries:
            summary = entry.get("summary") or entry.get("description") or str(entry)
            marker = entry.get("id") or entry.get("ref")
            if marker:
                rendered.append(f"- {summary} ({marker})")
            else:
                rendered.append(f"- {summary}")
        return rendered


__all__ = ["CovenantDigestDaemon"]
