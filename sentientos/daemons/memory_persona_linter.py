from __future__ import annotations
import json
import re
from pathlib import Path
from typing import List, Dict
from datetime import datetime, timezone

try:
    from logging_config import get_log_path
except ImportError:
    def get_log_path(name: str, env_var: str | None = None) -> Path:
        return Path(name)

class MemoryPersonaLinter:
    """Linter to inspect memory fragments for conflicting identity traits or unauthorized persona mutations."""
    def __init__(self, persona_path: Path | str, memory_dir: Path | str) -> None:
        self.persona_path = Path(persona_path)
        self.memory_dir = Path(memory_dir)
        self.log_path = get_log_path("memory_persona_lint.jsonl")
        self.persona_name = self.persona_path.stem
        try:
            persona_data = json.loads(self.persona_path.read_text(encoding="utf-8"))
        except Exception:
            persona_data = {}
        traits_text = str(persona_data.get("traits", "")).lower()
        # Split traits text into individual traits
        self.traits: List[str] = []
        for part in re.split(r',|;|\band\b', traits_text):
            trait = part.strip().lower()
            if trait:
                self.traits.append(trait)
        # Map of traits to words indicating conflicts or opposite characteristics
        self.trait_conflicts: Dict[str, List[str]] = {
            "friendly": ["unfriendly", "hostile", "hate", "kill"],
            "helpful": ["unhelpful"],
            "kind": ["unkind", "cruel", "kill"],
            "honest": ["dishonest", "lie", "lying"],
            "compassionate": ["heartless", "merciless", "kill", "harm"],
            "calm": ["angry", "furious"],
            "patient": ["impatient"],
            "humble": ["arrogant"],
        }

    def lint_fragments(self) -> dict:
        issues: List[dict] = []
        if not self.memory_dir.exists():
            return {"issues": issues, "issue_count": 0}
        for file_path in self.memory_dir.iterdir():
            if not file_path.is_file():
                continue
            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception:
                continue
            text_lower = content.lower()
            fragment_id = file_path.stem
            # Check if the persona asserts a new identity
            name_change_match = re.search(r"\bi am ([A-Za-z0-9_]+)", content, flags=re.IGNORECASE)
            if name_change_match:
                stated_name = name_change_match.group(1)
                if stated_name.lower() != self.persona_name.lower():
                    issue = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "fragment": fragment_id,
                        "issue": "unauthorized_persona_mutation",
                        "detected_identity": stated_name,
                    }
                    issues.append(issue)
                    self.log_path.parent.mkdir(parents=True, exist_ok=True)
                    with self.log_path.open("a", encoding="utf-8") as log_f:
                        log_f.write(json.dumps(issue, ensure_ascii=False) + "\n")
            # Check for contradictions to declared traits
            for trait in self.traits:
                if trait and f"not {trait}" in text_lower:
                    issue = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "fragment": fragment_id,
                        "issue": "trait_conflict",
                        "trait": trait,
                    }
                    issues.append(issue)
                    self.log_path.parent.mkdir(parents=True, exist_ok=True)
                    with self.log_path.open("a", encoding="utf-8") as log_f:
                        log_f.write(json.dumps(issue, ensure_ascii=False) + "\n")
                    break  # move to next fragment after logging this conflict
                if trait in self.trait_conflicts:
                    conflict_found = False
                    for opposite in self.trait_conflicts[trait]:
                        if opposite in text_lower:
                            issue = {
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "fragment": fragment_id,
                                "issue": "trait_conflict",
                                "trait": trait,
                            }
                            issues.append(issue)
                            self.log_path.parent.mkdir(parents=True, exist_ok=True)
                            with self.log_path.open("a", encoding="utf-8") as log_f:
                                log_f.write(json.dumps(issue, ensure_ascii=False) + "\n")
                            conflict_found = True
                            break
                    if conflict_found:
                        break  # move to next fragment after logging conflict
        return {"issues": issues, "issue_count": len(issues), "log_path": str(self.log_path)}
