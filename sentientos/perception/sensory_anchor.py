from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass
class Anchor:
    event_id: str
    fragment_path: str
    score: float

    def to_dict(self) -> Dict[str, object]:
        return {"event_id": self.event_id, "fragment_path": self.fragment_path, "score": round(self.score, 3)}


def _tokenize(text: str) -> List[str]:
    return [token for token in text.lower().split() if token]


def _overlap(a: Iterable[str], b: Iterable[str]) -> float:
    set_a = set(a)
    set_b = set(b)
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def load_fragments(fragments_dir: Path) -> List[Tuple[str, Dict[str, object]]]:
    fragments: List[Tuple[str, Dict[str, object]]] = []
    for fragment_file in sorted(fragments_dir.glob("*.jsonl")):
        with fragment_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                fragments.append((str(fragment_file), payload))
    return fragments


def anchor_events(
    perception_events: List[Dict[str, object]],
    fragments_dir: Path,
    anchors_path: Path,
) -> List[Anchor]:
    fragments = load_fragments(fragments_dir)
    anchors: List[Anchor] = []
    anchors_path.parent.mkdir(parents=True, exist_ok=True)

    with anchors_path.open("w", encoding="utf-8") as anchor_file:
        for event in perception_events:
            description = str(event.get("description", ""))
            event_tokens = _tokenize(description)
            best: Optional[Anchor] = None
            for fragment_path, payload in fragments:
                fragment_tokens = _tokenize(str(payload.get("content", "")))
                score = _overlap(event_tokens, fragment_tokens)
                if best is None or score > best.score:
                    best = Anchor(event_id=str(event.get("id")), fragment_path=fragment_path, score=score)
            if best is None:
                continue
            anchors.append(best)
            event["anchored_to"] = best.fragment_path
            anchor_record = best.to_dict()
            anchor_record["event"] = event
            anchor_file.write(json.dumps(anchor_record) + "\n")
    return anchors
