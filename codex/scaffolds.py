"""Codex scaffold generation and lifecycle management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping

import json
import re

try:  # pragma: no cover - optional import for type checking only
    from typing import Protocol
except ImportError:  # pragma: no cover - Python <3.8 fallback
    Protocol = object  # type: ignore[misc,assignment]


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


def _slugify(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", value.strip())
    text = re.sub(r"_+", "_", text)
    return text.strip("_").lower() or "scaffold"


class SupportsSpecProposal(Protocol):  # pragma: no cover - typing helper
    spec_id: str
    title: str


@dataclass
class ScaffoldRecord:
    """Serialized metadata for a generated scaffold."""

    spec_id: str
    title: str
    status: str
    generated_at: str
    paths: Dict[str, str]
    ledger_entry: str | None = None
    activated_at: str | None = None
    history: List[Dict[str, Any]] | None = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "spec_id": self.spec_id,
            "title": self.title,
            "status": self.status,
            "generated_at": self.generated_at,
            "paths": dict(self.paths),
            "ledger_entry": self.ledger_entry,
        }
        if self.activated_at:
            payload["activated_at"] = self.activated_at
        if self.history:
            payload["history"] = list(self.history)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScaffoldRecord":
        return cls(
            spec_id=str(payload["spec_id"]),
            title=str(payload["title"]),
            status=str(payload.get("status", "inactive")),
            generated_at=str(payload.get("generated_at", "")),
            paths=dict(payload.get("paths") or {}),
            ledger_entry=payload.get("ledger_entry"),
            activated_at=payload.get("activated_at"),
            history=list(payload.get("history") or []),
        )


class ScaffoldEngine:
    """Generate daemon/test/dashboard scaffolds for approved specs."""

    def __init__(
        self,
        *,
        repo_root: Path | str = Path("."),
        integration_root: Path | str | None = None,
        now: Callable[[], datetime] = _default_now,
    ) -> None:
        self._repo_root = Path(repo_root)
        self._integration_root = (
            Path(integration_root)
            if integration_root is not None
            else self._repo_root / "integration"
        )
        self._now = now
        self._daemon_root = self._repo_root / "daemons"
        self._tests_root = self._repo_root / "tests"
        self._tests_scaffold_root = self._tests_root / "scaffolds"
        self._dashboard_path = self._repo_root / "scaffolds_dashboard.py"
        self._registry_root = self._integration_root / "scaffolds"
        self._log_path = self._integration_root / "scaffold_log.jsonl"
        self._style_path = self._registry_root / "style.json"
        self._style: Dict[str, Any] = {
            "boilerplate_hint": "Replace this scaffold with live logic once ledger approval is recorded.",
            "edit_count": 0,
        }

        for directory in (
            self._daemon_root,
            self._tests_root,
            self._tests_scaffold_root,
            self._registry_root,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        self._load_style()
        self._ensure_dashboard_stub()

    # ------------------------------------------------------------------
    # Public API
    def generate(
        self,
        proposal: SupportsSpecProposal,
        *,
        overwrite: bool = False,
    ) -> ScaffoldRecord:
        """Generate scaffold artifacts for the supplied proposal."""

        slug = _slugify(proposal.spec_id)
        timestamp = self._now().isoformat()
        metadata_path = self._metadata_path(proposal.spec_id)

        daemon_path = self._daemon_root / f"{slug}_daemon.py"
        test_path = self._tests_scaffold_root / f"test_{slug}.py"
        dashboard_path = self._dashboard_path

        daemon_body = self._header_block(proposal) + "\n" + self._daemon_template(proposal, slug)
        test_body = self._header_block(proposal) + "\n" + self._test_template(proposal, slug)

        self._write_file(daemon_path, daemon_body, overwrite=overwrite)
        self._write_file(test_path, test_body, overwrite=overwrite)

        record = ScaffoldRecord(
            spec_id=proposal.spec_id,
            title=getattr(proposal, "title", proposal.spec_id),
            status="inactive",
            generated_at=timestamp,
            paths={
                "daemon": self._relpath(daemon_path),
                "test": self._relpath(test_path),
                "dashboard": self._relpath(dashboard_path),
            },
            ledger_entry=None,
            history=[],
        )
        self._save_metadata(metadata_path, record)
        self._append_log("generated", proposal.spec_id, metadata=record.to_dict())
        return record

    def enable(
        self,
        spec_id: str,
        *,
        operator: str,
        ledger_entry: str | None,
    ) -> ScaffoldRecord:
        """Mark a scaffold as enabled once ledger approval is recorded."""

        if not ledger_entry:
            raise ValueError("Ledger entry is required before enabling scaffolds")

        record = self._load_metadata(spec_id)
        record.status = "enabled"
        record.ledger_entry = ledger_entry
        record.activated_at = self._now().isoformat()
        history_entry = {
            "timestamp": record.activated_at,
            "operator": operator,
            "action": "enabled",
            "ledger_entry": ledger_entry,
        }
        record.history = list(record.history or []) + [history_entry]
        self._save_metadata(self._metadata_path(spec_id), record)
        self._append_log(
            "enabled",
            spec_id,
            operator=operator,
            metadata={"ledger_entry": ledger_entry},
        )
        return record

    def record_edit(
        self,
        spec_id: str,
        *,
        operator: str,
        notes: Mapping[str, Any] | None = None,
    ) -> ScaffoldRecord:
        """Log operator edits to a scaffold and adapt templates accordingly."""

        record = self._load_metadata(spec_id)
        timestamp = self._now().isoformat()
        entry = {
            "timestamp": timestamp,
            "operator": operator,
            "action": "edited",
        }
        if notes:
            entry["notes"] = dict(notes)
        record.history = list(record.history or []) + [entry]
        self._save_metadata(self._metadata_path(spec_id), record)
        self._append_log("edited", spec_id, operator=operator, metadata=dict(notes or {}))
        self._style["edit_count"] = int(self._style.get("edit_count", 0)) + 1
        if self._style["edit_count"] >= 3:
            self._style["boilerplate_hint"] = (
                "Operators frequently customize scaffolds; include explicit TODO markers and ledger notes."
            )
        self._save_style()
        return record

    def reject(
        self,
        spec_id: str,
        *,
        operator: str,
        reason: str | None = None,
    ) -> ScaffoldRecord:
        record = self._load_metadata(spec_id)
        record.status = "archived"
        timestamp = self._now().isoformat()
        history_entry = {
            "timestamp": timestamp,
            "operator": operator,
            "action": "rejected",
        }
        if reason:
            history_entry["reason"] = reason
        record.history = list(record.history or []) + [history_entry]
        self._save_metadata(self._metadata_path(spec_id), record)
        self._append_log("rejected", spec_id, operator=operator, metadata={"reason": reason})
        return record

    def reroll(
        self,
        proposal: SupportsSpecProposal,
        *,
        operator: str,
    ) -> ScaffoldRecord:
        try:
            previous = self._load_metadata(proposal.spec_id)
            history: List[Dict[str, Any]] = list(previous.history or [])
        except FileNotFoundError:
            history = []
        record = self.generate(proposal, overwrite=True)
        timestamp = self._now().isoformat()
        history_entry = {
            "timestamp": timestamp,
            "operator": operator,
            "action": "rerolled",
        }
        record.history = history + [history_entry]
        self._save_metadata(self._metadata_path(proposal.spec_id), record)
        self._append_log("rerolled", proposal.spec_id, operator=operator)
        return record

    def list_scaffolds(self) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        for path in sorted(self._registry_root.glob("*.json")):
            if path == self._style_path:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            payload["registry_path"] = self._relpath(path)
            records.append(payload)
        records.sort(key=lambda item: item.get("generated_at", ""))
        return records

    # ------------------------------------------------------------------
    # Internal helpers
    def _metadata_path(self, spec_id: str) -> Path:
        return self._registry_root / f"{spec_id}.json"

    def _header_block(self, proposal: SupportsSpecProposal) -> str:
        rollback = self._relpath(self._metadata_path(proposal.spec_id))
        return (
            "\n".join(
                [
                    "\"\"\"Codex Scaffold Stub",
                    f"Spec ID: {proposal.spec_id}",
                    f"Rollback: {rollback}",
                    "Status: INACTIVE (ledger gated)",
                    "\"\"\"",
                ]
            )
            + "\n"
        )

    def _daemon_template(self, proposal: SupportsSpecProposal, slug: str) -> str:
        class_name = "".join(part.capitalize() for part in slug.split("_")) or "ScaffoldDaemon"
        hint = str(self._style.get("boilerplate_hint", "Implement scaffold logic."))
        return (
            "from __future__ import annotations\n\n"
            "LEDGER_STATUS = \"inactive\"\n"
            "LEDGER_ENTRY: str | None = None\n\n"
            f"class {class_name}Daemon:\n"
            f"    \"\"\"Auto-generated daemon scaffold for {getattr(proposal, 'title', proposal.spec_id)}.\"\"\"\n\n"
            "    active: bool = False\n\n"
            "    def activate(self, ledger_entry: str) -> None:\n"
            f"        \"\"\"Enable the scaffold once approved. {hint}\"\"\"\n"
            "        raise NotImplementedError('Operator must supply implementation.')\n"
        )

    def _test_template(self, proposal: SupportsSpecProposal, slug: str) -> str:
        hint = str(self._style.get("boilerplate_hint", "Implement scaffold logic."))
        return (
            "import pytest\n\n"
            f"def test_{slug}_remains_inactive_without_ledger() -> None:\n"
            f"    \"\"\"Ensure {getattr(proposal, 'title', proposal.spec_id)} stays gated.\"\"\"\n"
            "    pytest.skip(\"Activation requires ledger entry and operator approval.\")\n\n"
            "def test_{slug}_activation_placeholder() -> None:\n"
            f"    \"\"\"Placeholder to validate activation workflow. {hint}\"\"\"\n"
            "    pytest.skip(\"Operator-defined tests pending scaffold enablement.\")\n"
        )

    def _write_file(self, path: Path, content: str, *, overwrite: bool) -> None:
        if path.exists() and not overwrite:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _save_metadata(self, path: Path, record: ScaffoldRecord) -> None:
        payload = record.to_dict()
        path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")

    def _load_metadata(self, spec_id: str) -> ScaffoldRecord:
        path = self._metadata_path(spec_id)
        if not path.exists():
            raise FileNotFoundError(f"Unknown scaffold for spec {spec_id}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ScaffoldRecord.from_dict(payload)

    def _relpath(self, path: Path) -> str:
        try:
            return path.relative_to(self._repo_root).as_posix()
        except ValueError:
            return path.as_posix()

    def _append_log(
        self,
        action: str,
        spec_id: str,
        *,
        operator: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "timestamp": self._now().isoformat(),
            "spec_id": spec_id,
            "action": action,
        }
        if operator:
            payload["operator"] = operator
        if metadata:
            payload["metadata"] = dict(metadata)
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def _load_style(self) -> None:
        if not self._style_path.exists():
            return
        try:
            payload = json.loads(self._style_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        if isinstance(payload, MutableMapping):
            for key, value in payload.items():
                self._style[key] = value

    def _save_style(self) -> None:
        self._style_path.write_text(
            json.dumps(self._style, sort_keys=True, indent=2),
            encoding="utf-8",
        )

    def _ensure_dashboard_stub(self) -> None:
        if self._dashboard_path.exists():
            return
        header = (
            "\"\"\"Codex Scaffold Dashboard Panel\n"
            "Auto-generated placeholder for the Scaffolds panel.\n"
            "\"\"\"\n"
        )
        body = (
            "from __future__ import annotations\n\n"
            "from typing import Any, Mapping\n\n"
            "from codex.scaffolds import ScaffoldEngine\n\n"
            "PANEL_TITLE = \"Scaffolds\"\n\n"
            "def scaffolds_panel_state(\n"
            "    engine: ScaffoldEngine | None = None,\n"
            "    *,\n"
            "    include_history: bool = False,\n"
            ") -> Mapping[str, Any]:\n"
            "    \"\"\"Return dashboard data summarizing generated scaffolds.\"\"\"\n"
            "    eng = engine or ScaffoldEngine()\n"
            "    records = eng.list_scaffolds()\n"
            "    items: list[dict[str, Any]] = []\n"
            "    for record in records:\n"
            "        item = {k: record.get(k) for k in (\"spec_id\", \"title\", \"status\", \"paths\", \"generated_at\", \"ledger_entry\")}\n"
            "        if include_history:\n"
            "            item[\"history\"] = record.get(\"history\", [])\n"
            "        items.append(item)\n"
            "    return {\n"
            "        \"panel\": PANEL_TITLE,\n"
            "        \"scaffolds\": items,\n"
            "        \"inactive\": [item for item in items if item.get(\"status\") == \"inactive\"],\n"
            "        \"enabled\": [item for item in items if item.get(\"status\") == \"enabled\"],\n"
            "        \"archived\": [item for item in items if item.get(\"status\") == \"archived\"],\n"
            "    }\n"
        )
        self._dashboard_path.write_text(header + body, encoding="utf-8")


__all__ = ["ScaffoldEngine", "ScaffoldRecord"]

