from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from sentientos.ethics.consent_memory_vault import ConsentMemoryVault


class AmbiguityResolver:
    """Resolve unclear or conflicting instructions using precedent and consent."""

    def __init__(
        self,
        workspace: str | Path,
        *,
        consent_vault: ConsentMemoryVault | None = None,
        peer_behaviour: Sequence[Mapping[str, object]] | None = None,
    ) -> None:
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.consent_vault = consent_vault
        self.peer_behaviour = peer_behaviour or []
        self.clarification_path = self.workspace / "clarification_request.jsonl"
        self.resolution_path = self.workspace / "autonomous_resolution.jsonl"

    def run(
        self,
        instructions: Sequence[Mapping[str, object]] | None,
        *,
        dialogue_history: Sequence[Mapping[str, object]] | None = None,
        glow_fragments: Sequence[Mapping[str, object]] | None = None,
    ) -> dict:
        if instructions is None:
            instructions = []
        dialogue_history = dialogue_history or []
        glow_fragments = glow_fragments or []

        clarification_requests: list[dict] = []
        autonomous_resolutions: list[dict] = []

        for instruction in instructions:
            resolution = self._resolve_instruction(instruction, dialogue_history, glow_fragments)
            if resolution.get("action") == "clarify":
                clarification_requests.append(resolution)
            else:
                autonomous_resolutions.append(resolution)

        if clarification_requests:
            self._write_jsonl(self.clarification_path, clarification_requests)
        if autonomous_resolutions:
            self._write_jsonl(self.resolution_path, autonomous_resolutions)

        return {
            "clarifications": clarification_requests,
            "resolutions": autonomous_resolutions,
        }

    def _resolve_instruction(
        self,
        instruction: Mapping[str, object],
        dialogue_history: Sequence[Mapping[str, object]],
        glow_fragments: Sequence[Mapping[str, object]],
    ) -> dict:
        ambiguity = instruction.get("ambiguity") or instruction.get("vagueness")
        task = instruction.get("task") or instruction.get("summary") or "unspecified_task"
        capability = instruction.get("capability")

        consent_status = None
        precedent_refs: list[str] = []
        if self.consent_vault and capability:
            consent_snapshot = self.consent_vault.query(str(capability))
            if consent_snapshot:
                consent_status = consent_snapshot.get("status")
                precedent_refs.append(f"consent:{capability}:{consent_status}")

        dialogue_ref = next((entry for entry in reversed(dialogue_history) if entry.get("topic") == task), None)
        if dialogue_ref:
            precedent_refs.append(f"dialogue:{dialogue_ref.get('id', 'recent')}")

        if consent_status and consent_status in {"denied", "withdrawn"}:
            return {
                "task": task,
                "ambiguity_type": "consent_conflict",
                "resolution_strategy": "respect_denial",
                "confidence": 0.95,
                "precedent_refs": precedent_refs,
                "action": "decline",
            }

        if ambiguity or not instruction.get("guardrails"):
            return {
                "task": task,
                "ambiguity_type": ambiguity or "missing_guardrails",
                "resolution_strategy": "request_clarification",
                "confidence": 0.4,
                "precedent_refs": precedent_refs,
                "action": "clarify",
            }

        return {
            "task": task,
            "ambiguity_type": "resolved_by_precedent" if precedent_refs else "auto_resolution",
            "resolution_strategy": "apply_guardrails",
            "confidence": 0.78,
            "precedent_refs": precedent_refs,
            "action": "proceed",
        }

    def _write_jsonl(self, path: Path, rows: Iterable[Mapping[str, object]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")


__all__ = ["AmbiguityResolver"]
