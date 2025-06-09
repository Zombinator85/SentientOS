from __future__ import annotations

import csv
import json
import re
from pathlib import Path


def validate_json(path: Path, fix: bool = False) -> list[str]:
    issues: list[str] = []
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        if fix:
            cleaned = re.sub(r",(\s*[}\]])", r"\1", text)
            try:
                data = json.loads(cleaned)
                text = cleaned
            except Exception:
                issues.append(f"{path}: invalid JSON ({e})")
                return issues
        else:
            issues.append(f"{path}: invalid JSON ({e})")
            return issues

    stack = [data]
    snake = re.compile(r"^[a-z0-9_]+$")
    while stack:
        obj = stack.pop()
        if isinstance(obj, dict):
            for k, v in obj.items():
                if not snake.match(str(k)):
                    issues.append(f"{path}: key '{k}' not snake_case")
                stack.append(v)
        elif isinstance(obj, list):
            stack.extend(obj)
    if fix:
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return issues


def validate_csv(path: Path) -> list[str]:
    issues: list[str] = []
    with path.open(newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if header is None:
            issues.append(f"{path}: empty CSV")
            return issues
        if any(h.strip() == "" for h in header):
            issues.append(f"{path}: blank headers not allowed")
        cols = len(header)
        for line_no, row in enumerate(reader, start=2):
            if len(row) != cols:
                issues.append(f"{path}:{line_no} expected {cols} cols, found {len(row)}")
    return issues
