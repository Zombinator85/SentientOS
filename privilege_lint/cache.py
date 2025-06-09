from __future__ import annotations

import json
import hashlib
from pathlib import Path
from dataclasses import asdict

from privilege_lint.config import LintConfig

CACHE_NAME = ".privilege_lint.cache"


def _cfg_hash(cfg: LintConfig) -> str:
    return hashlib.sha1(json.dumps(asdict(cfg), sort_keys=True).encode()).hexdigest()


class LintCache:
    def __init__(self, root: Path, cfg: LintConfig, enabled: bool = True) -> None:
        self.root = root
        self.enabled = enabled
        self.cfg_hash = _cfg_hash(cfg)
        self.path = root / CACHE_NAME
        self.data: dict[str, dict] = {}
        if enabled and self.path.exists():
            try:
                self.data = json.loads(self.path.read_text())
            except Exception:
                self.data = {}

    def is_valid(self, path: Path) -> bool:
        if not self.enabled:
            return False
        info = self.data.get(str(path))
        if not info or info.get("cfg") != self.cfg_hash:
            return False
        stat = path.stat()
        return info.get("mtime") == stat.st_mtime and info.get("size") == stat.st_size

    def update(self, path: Path) -> None:
        if not self.enabled:
            return
        stat = path.stat()
        self.data[str(path)] = {"mtime": stat.st_mtime, "size": stat.st_size, "cfg": self.cfg_hash}

    def save(self) -> None:
        if self.enabled:
            self.path.write_text(json.dumps(self.data, indent=2))
