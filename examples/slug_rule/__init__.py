from __future__ import annotations
from pathlib import Path
from privilege_lint.config import LintConfig

def validate(file_path: Path, config: LintConfig) -> list[str]:
    if 'slug' in file_path.read_text(encoding='utf-8'):
        return [f"{file_path}: slug word found"]
    return []
