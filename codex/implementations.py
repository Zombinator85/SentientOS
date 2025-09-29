"""Codex Implementor for drafting first-pass implementations."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Protocol

import json
import re


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


def _slugify(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", value.strip())
    text = re.sub(r"_+", "_", text)
    return text.strip("_").lower() or "implementation"


class SupportsSpecProposal(Protocol):  # pragma: no cover - typing helper
    spec_id: str
    title: str
    directives: Iterable[str]
    testing_requirements: Iterable[str]


@dataclass
class ImplementationBlock:
    """Serialized draft block for a generated implementation."""

    block_id: str
    component: str
    target_path: str
    function_name: str
    directive: str
    confidence: str
    rollback_path: str
    draft: str
    status: str = "pending_review"
    created_at: str = ""
    history: List[Dict[str, Any]] = field(default_factory=list)
    pattern_key: str = ""

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "block_id": self.block_id,
            "component": self.component,
            "target_path": self.target_path,
            "function_name": self.function_name,
            "directive": self.directive,
            "confidence": self.confidence,
            "rollback_path": self.rollback_path,
            "draft": self.draft,
            "status": self.status,
            "created_at": self.created_at,
            "pattern_key": self.pattern_key,
        }
        if self.history:
            payload["history"] = list(self.history)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ImplementationBlock":
        history = list(payload.get("history") or [])
        return cls(
            block_id=str(payload["block_id"]),
            component=str(payload["component"]),
            target_path=str(payload["target_path"]),
            function_name=str(payload["function_name"]),
            directive=str(payload.get("directive", "")),
            confidence=str(payload.get("confidence", "low")),
            rollback_path=str(payload.get("rollback_path", "")),
            draft=str(payload.get("draft", "")),
            status=str(payload.get("status", "pending_review")),
            created_at=str(payload.get("created_at", "")),
            history=history,
            pattern_key=str(payload.get("pattern_key", "")),
        )


@dataclass
class ImplementationRecord:
    """Serialized metadata for pending implementation drafts."""

    spec_id: str
    title: str
    status: str
    generated_at: str
    blocks: List[ImplementationBlock]
    ledger_entry: str | None = None
    approved_at: str | None = None
    approved_by: str | None = None
    history: List[Dict[str, Any]] | None = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "spec_id": self.spec_id,
            "title": self.title,
            "status": self.status,
            "generated_at": self.generated_at,
            "blocks": [block.to_dict() for block in self.blocks],
            "ledger_entry": self.ledger_entry,
            "approved_at": self.approved_at,
            "approved_by": self.approved_by,
        }
        if self.history:
            payload["history"] = list(self.history)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ImplementationRecord":
        blocks_payload = list(payload.get("blocks") or [])
        blocks = [ImplementationBlock.from_dict(item) for item in blocks_payload]
        history = list(payload.get("history") or [])
        return cls(
            spec_id=str(payload["spec_id"]),
            title=str(payload.get("title", "")),
            status=str(payload.get("status", "pending_review")),
            generated_at=str(payload.get("generated_at", "")),
            blocks=blocks,
            ledger_entry=payload.get("ledger_entry"),
            approved_at=payload.get("approved_at"),
            approved_by=payload.get("approved_by"),
            history=history,
        )


class Implementor:
    """Draft first-pass implementations for Codex scaffolds."""

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
        self._implementations_root = self._integration_root / "implementations"
        self._rejected_root = self._integration_root / "rejected_impls"
        self._log_path = self._integration_root / "implementation_log.jsonl"
        self._patterns_path = self._implementations_root / "patterns.json"

        for directory in (
            self._integration_root,
            self._implementations_root,
            self._rejected_root,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        self._pattern_stats: Dict[str, Dict[str, int]] = {}
        self._load_patterns()

    # ------------------------------------------------------------------
    # Draft lifecycle
    def draft_from_scaffold(
        self,
        proposal: SupportsSpecProposal,
        record: Mapping[str, Any],
    ) -> ImplementationRecord:
        """Generate implementation drafts for the provided scaffold record."""

        timestamp = self._now().isoformat()
        spec_id = proposal.spec_id
        slug = _slugify(spec_id)

        try:
            existing = self._load_metadata(spec_id)
            history = list(existing.history or [])
        except FileNotFoundError:
            history = []

        blocks: List[ImplementationBlock] = []
        directives = list(proposal.directives) or ["Codex directive"]
        for component, path_key in (
            ("daemon", "daemon"),
            ("test", "test"),
            ("dashboard", "dashboard"),
        ):
            target_path = str(record.get("paths", {}).get(path_key, ""))
            for index, directive in enumerate(directives, start=1):
                pattern_key = self._pattern_key(component, directive)
                confidence = self._confidence_for(pattern_key)
                function_name = self._function_name(component, slug, index)
                rollback_path = self._relpath(self._metadata_path(spec_id))
                draft_code = self._function_template(
                    spec_id,
                    proposal.title,
                    component,
                    function_name,
                    directive,
                    confidence,
                    rollback_path,
                    target_path,
                )
                block_id = f"{component}-{index}"
                block = ImplementationBlock(
                    block_id=block_id,
                    component=component,
                    target_path=target_path,
                    function_name=function_name,
                    directive=directive,
                    confidence=confidence,
                    rollback_path=rollback_path,
                    draft=draft_code,
                    status="pending_review",
                    created_at=timestamp,
                    history=[],
                    pattern_key=pattern_key,
                )
                blocks.append(block)

        new_history_entry = {
            "timestamp": timestamp,
            "action": "drafted",
            "block_count": len(blocks),
        }
        history.append(new_history_entry)

        implementation_record = ImplementationRecord(
            spec_id=spec_id,
            title=getattr(proposal, "title", spec_id),
            status="pending_review",
            generated_at=timestamp,
            blocks=blocks,
            ledger_entry=None,
            history=history,
        )

        self._save_metadata(self._metadata_path(spec_id), implementation_record)
        self._append_log(
            "drafted",
            spec_id,
            metadata={
                "confidence_levels": [block.confidence for block in blocks],
                "components": sorted({block.component for block in blocks}),
            },
        )
        return implementation_record

    def commit_ledger_entry(self, spec_id: str, ledger_entry: str) -> ImplementationRecord:
        """Attach a ledger entry to a draft without approving it."""

        record = self._load_metadata(spec_id)
        record.ledger_entry = ledger_entry
        timestamp = self._now().isoformat()
        history_entry = {
            "timestamp": timestamp,
            "action": "ledger_committed",
            "ledger_entry": ledger_entry,
        }
        record.history = list(record.history or []) + [history_entry]
        self._save_metadata(self._metadata_path(spec_id), record)
        self._append_log(
            "ledger_committed",
            spec_id,
            metadata={"ledger_entry": ledger_entry},
        )
        return record

    def approve(
        self,
        spec_id: str,
        *,
        operator: str,
        ledger_entry: str | None = None,
    ) -> ImplementationRecord:
        """Mark all blocks as approved once dashboard sign-off occurs."""

        record = self._load_metadata(spec_id)
        if ledger_entry:
            record.ledger_entry = ledger_entry
        if not record.ledger_entry:
            raise ValueError("Ledger entry required before approval")

        timestamp = self._now().isoformat()
        record.status = "approved"
        record.approved_at = timestamp
        record.approved_by = operator
        for block in record.blocks:
            block.status = "approved"
            block.history = list(block.history) + [
                {
                    "timestamp": timestamp,
                    "operator": operator,
                    "action": "approved",
                    "confidence": block.confidence,
                }
            ]
            self._register_pattern_acceptance(block.pattern_key)

        history_entry = {
            "timestamp": timestamp,
            "operator": operator,
            "action": "approved",
            "ledger_entry": record.ledger_entry,
        }
        record.history = list(record.history or []) + [history_entry]
        self._save_metadata(self._metadata_path(spec_id), record)
        self._append_log(
            "approved",
            spec_id,
            operator=operator,
            metadata={"ledger_entry": record.ledger_entry},
        )
        self._save_patterns()
        return record

    def reject(
        self,
        spec_id: str,
        *,
        operator: str,
        reason: str | None = None,
    ) -> ImplementationRecord:
        """Archive draft blocks that were rejected by operators."""

        record = self._load_metadata(spec_id)
        timestamp = self._now().isoformat()
        record.status = "rejected"
        archive_payload = {
            "timestamp": timestamp,
            "operator": operator,
            "action": "rejected",
            "reason": reason,
        }
        record.history = list(record.history or []) + [archive_payload]
        for block in record.blocks:
            block.status = "rejected"
            block.history = list(block.history) + [archive_payload]
            archive_path = self._rejected_root / f"{spec_id}_{block.block_id}.py"
            archive_path.write_text(block.draft, encoding="utf-8")

        self._save_metadata(self._metadata_path(spec_id), record)
        self._append_log(
            "rejected",
            spec_id,
            operator=operator,
            metadata={"reason": reason},
        )
        return record

    def record_feedback(
        self,
        spec_id: str,
        *,
        operator: str,
        notes: Mapping[str, Any] | None = None,
    ) -> ImplementationRecord:
        """Log operator feedback for adaptive refinement."""

        record = self._load_metadata(spec_id)
        timestamp = self._now().isoformat()
        entry = {
            "timestamp": timestamp,
            "operator": operator,
            "action": "feedback",
            "notes": dict(notes or {}),
        }
        record.history = list(record.history or []) + [entry]
        self._save_metadata(self._metadata_path(spec_id), record)
        self._append_log(
            "feedback",
            spec_id,
            operator=operator,
            metadata=dict(notes or {}),
        )
        return record

    def assert_ready(self, spec_id: str) -> None:
        """Ensure implementations remain gated until approval and ledger commit."""

        record = self._load_metadata(spec_id)
        if record.status != "approved" or not record.ledger_entry:
            raise RuntimeError(
                "Implementation pending dashboard approval and ledger commitment."
            )

    # ------------------------------------------------------------------
    # Dashboard helpers
    def list_records(self) -> List[Dict[str, Any]]:
        """Return serialized records for dashboard consumption."""

        records: List[Dict[str, Any]] = []
        for path in sorted(self._implementations_root.glob("*.json")):
            if path == self._patterns_path:
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
        return self._implementations_root / f"{spec_id}.json"

    def _function_name(self, component: str, slug: str, index: int) -> str:
        return f"codex_{component}_{slug}_{index}"

    def _pattern_key(self, component: str, directive: str) -> str:
        directive_slug = _slugify(directive)[:64]
        return f"{component}:{directive_slug}"

    def _confidence_for(self, pattern_key: str) -> str:
        stats = self._pattern_stats.get(pattern_key, {})
        accepted = int(stats.get("accepted", 0))
        if accepted >= 5:
            return "high"
        if accepted >= 1:
            return "medium"
        return "low"

    def _register_pattern_acceptance(self, pattern_key: str) -> None:
        if not pattern_key:
            return
        stats = self._pattern_stats.setdefault(pattern_key, {"accepted": 0})
        stats["accepted"] = int(stats.get("accepted", 0)) + 1

    def _function_template(
        self,
        spec_id: str,
        title: str,
        component: str,
        function_name: str,
        directive: str,
        confidence: str,
        rollback_path: str,
        target_path: str,
    ) -> str:
        spec_link = self._spec_link(spec_id)
        sanitized_directive = directive.strip()
        doc_lines = [
            f"Draft implementation for {component} generated from spec {spec_id}.",
            "",
            f"Spec Link: {spec_link}",
            f"Confidence: {confidence}",
            f"Rollback: {rollback_path}",
            "Status: pending_review",
        ]
        header = "\n    ".join(doc_lines)
        return "\n".join(
            [
                "from typing import Any, Mapping\n\n",
                f"def {function_name}(context: Mapping[str, Any], ledger_state: Mapping[str, Any]) -> dict[str, Any]:\n",
                f"    \"\"\"{header}\"\"\"\n",
                "    if not ledger_state.get('approved'):\n",
                "        raise RuntimeError('Implementation pending dashboard approval and ledger entry.')\n",
                "    # CODEX_IMPLEMENTATION START\n",
                "    result: dict[str, Any] = {\n",
                f"        'spec_id': '{spec_id}',\n",
                f"        'title': '{title}',\n",
                f"        'component': '{component}',\n",
                f"        'directive': {json.dumps(sanitized_directive)},\n",
                "        'context_snapshot': dict(context),\n",
                f"        'rollback_path': '{rollback_path}',\n",
                f"        'target_path': '{target_path}',\n",
                "    }\n",
                "    result['confidence'] = ledger_state.get('confidence', '{confidence}')\n",
                "    result['notes'] = 'Draft generated by Codex Implementor for operator review.'\n",
                "    return result\n",
                "    # CODEX_IMPLEMENTATION END\n",
            ]
        )

    def _save_metadata(self, path: Path, record: ImplementationRecord) -> None:
        payload = record.to_dict()
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _load_metadata(self, spec_id: str) -> ImplementationRecord:
        path = self._metadata_path(spec_id)
        if not path.exists():
            raise FileNotFoundError(f"Unknown implementation for spec {spec_id}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ImplementationRecord.from_dict(payload)

    def _relpath(self, path: Path) -> str:
        try:
            return path.relative_to(self._repo_root).as_posix()
        except ValueError:
            return path.as_posix()

    def _spec_link(self, spec_id: str) -> str:
        spec_path = self._integration_root / "specs" / "proposals" / f"{spec_id}.json"
        if spec_path.exists():
            return self._relpath(spec_path)
        return f"spec://{spec_id}"

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

    def _load_patterns(self) -> None:
        if not self._patterns_path.exists():
            return
        try:
            payload = json.loads(self._patterns_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        if isinstance(payload, MutableMapping):
            for key, value in payload.items():
                if isinstance(value, MutableMapping):
                    self._pattern_stats[key] = {"accepted": int(value.get("accepted", 0))}

    def _save_patterns(self) -> None:
        self._patterns_path.write_text(
            json.dumps(self._pattern_stats, indent=2, sort_keys=True),
            encoding="utf-8",
        )


__all__ = [
    "Implementor",
    "ImplementationBlock",
    "ImplementationRecord",
]

