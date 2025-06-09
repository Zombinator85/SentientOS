from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


_VAR_RE = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")


def parse_context(lines: Iterable[str]) -> list[str]:
    for line in lines:
        if line.startswith('# context:'):
            vars = line.split(':', 1)[1]
            return [v.strip() for v in vars.split(',') if v.strip()]
    return []


def validate_template(path: Path, context: list[str]) -> list[str]:
    """Validate a Jinja2/Handlebars template."""
    text = path.read_text(encoding="utf-8")
    issues: list[str] = []
    if text.count('{%') != text.count('%}'):
        issues.append(f"{path}: unbalanced block tags")

    used = set(_VAR_RE.findall(text))
    for v in context:
        if v not in used:
            issues.append(f"{path}: variable '{v}' unused")
    for v in used:
        if v not in context:
            issues.append(f"{path}: variable '{v}' missing in context")
    if '{{{' in text or '|safe' in text:
        issues.append(f"{path}: possible unescaped HTML")
    return issues
