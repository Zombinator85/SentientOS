from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict


class MetricsCollector:
    def __init__(self) -> None:
        self.start = time.time()
        self.rule_counts: Dict[str, int] = {}
        self.files = 0
        self.cache_hits = 0

    def file_scanned(self) -> None:
        self.files += 1

    def cache_hit(self) -> None:
        self.cache_hits += 1

    def record(self, rule: str, count: int) -> None:
        if count:
            self.rule_counts[rule] = self.rule_counts.get(rule, 0) + count

    def finish(self) -> None:
        self.runtime = time.time() - self.start

    def to_dict(self) -> Dict[str, object]:
        return {
            "files": self.files,
            "cache_hits": self.cache_hits,
            "runtime": round(getattr(self, "runtime", 0), 3),
            "rules": self.rule_counts,
        }

    def write_json(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2))
