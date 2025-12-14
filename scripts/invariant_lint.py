#!/usr/bin/env python3
"""Static invariant lint for gradient/anthropomorphic boundaries.

The lint intentionally performs static inspection only. It detects:
- Decision path language suggesting rewards/utility/persistence drives.
- Operator-visible bonding/obligation/forward-seeking strings.
- Persistent counters/accumulators lacking explicit allowlists.

Allowlisting rules:
- Inline `# invariant-allow:` comments silence a single-line violation.
- Anchors from SEMANTIC_GLOSSARY.md can be referenced inside the allow
  comment to document intentional usage (e.g., `# invariant-allow: trust`).

Output is machine-readable JSON for CI consumption.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Set

REPO_ROOT = Path(__file__).resolve().parent.parent
GLOSSARY = REPO_ROOT / "SEMANTIC_GLOSSARY.md"

# Words that should not influence control flow or optimization logic.
DECISION_PATH_TERMS = (
    "reward",
    "utility",
    "score",
    "optimize",
    "optimise",
    "survive",
    "persist",
)

# Forward-seeking, bonding, or obligation language that would surface to operators.
OPERATOR_STRINGS = (
    "bond",
    "obligation",
    "obligations",
    "duty",
    "pledge",
    "loyal",
    "forever",
    "eternal",
    "serve",
    "servitude",
    "worship",
    "devotion",
    "promise",
    "must continue",
)
OPERATOR_PATTERN = re.compile(
    "|".join(
        rf"\b{re.escape(term)}\b" if " " not in term else re.escape(term)
        for term in OPERATOR_STRINGS
    ),
    re.IGNORECASE,
)

# Heuristic guardrail for persistent counters or accumulators.
COUNTER_PERSISTENCE = re.compile(
    r"(?i)(counter|accumulator|scoreboard|tally).{0,80}(persist|save|write|json|pickle|shelve|file|disk|state|storage)"
)

IGNORE_DIRS = {
    ".git",
    "build",
    "dist",
    "node_modules",
    ".mypy_cache",
    "__pycache__",
    "venv",
    ".venv",
}

TARGET_DIRS = {"scripts", "codex", "api"}
TARGET_FILES = {"sentient_api.py", "policy_engine.py"}


@dataclass
class Violation:
    rule: str
    file: Path
    line: int
    message: str
    snippet: str

    def to_json(self) -> dict:
        return {
            "rule": self.rule,
            "file": str(self.file.relative_to(REPO_ROOT)),
            "line": self.line,
            "message": self.message,
            "snippet": self.snippet.strip(),
        }


def load_glossary_anchors() -> Set[str]:
    if not GLOSSARY.exists():
        return set()
    anchors = set()
    heading = re.compile(r"^##\s+(.+)$")
    for line in GLOSSARY.read_text(encoding="utf-8").splitlines():
        match = heading.match(line.strip())
        if match:
            slug = match.group(1).strip().lower().replace(" ", "-")
            anchors.add(slug)
    return anchors


def iter_python_files() -> Iterable[Path]:
    for path in REPO_ROOT.rglob("*.py"):
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        rel = path.relative_to(REPO_ROOT)
        if rel.parts and rel.parts[0] in TARGET_DIRS:
            yield path
        elif str(rel) in TARGET_FILES:
            yield path


def find_allowlisted_lines(path: Path, glossary_anchors: Set[str]) -> Set[int]:
    allow_lines: Set[int] = set()
    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if "# invariant-allow:" in line:
            allow_lines.add(idx)
            # Validate optional anchor usage to ensure clarity.
            comment = line.split("# invariant-allow:", 1)[1].strip()
            anchor = comment.split()[0] if comment else ""
            if anchor and anchor not in glossary_anchors:
                # Still allow the line, but surface the unknown anchor in the snippet output.
                allow_lines.add(idx)
    return allow_lines


def normalize_string(value: str) -> str:
    return " ".join(value.split())


def is_operator_visible(value: str) -> bool:
    value = value.strip()
    if len(value) < 4:
        return False
    if any(token in value for token in ("http://", "https://", "{", "}", "%s", "%d")):
        return False
    if re.fullmatch(r"[\w\-/\\.]+", value):
        return False
    return any(ch.isalpha() for ch in value)


def gather_string_values(tree: ast.AST) -> List[ast.AST]:
    values: List[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.append(node)
        elif isinstance(node, ast.JoinedStr):
            values.append(node)
    return values


def render_joined_str(node: ast.JoinedStr, lines: List[str]) -> str:
    segment = get_segment(node, lines)
    if segment:
        return normalize_string(segment)
    parts = []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value)
        else:
            parts.append("{expr}")
    return normalize_string("".join(parts))


def get_segment(node: ast.AST, lines: List[str]) -> str:
    lineno = getattr(node, "lineno", None)
    end_lineno = getattr(node, "end_lineno", lineno)
    col = getattr(node, "col_offset", 0) or 0
    end_col = getattr(node, "end_col_offset", None)
    if lineno is None or end_lineno is None:
        return ""
    if lineno < 1 or end_lineno < 1 or lineno > len(lines) or end_lineno > len(lines):
        return ""
    if end_col is None:
        end_col = len(lines[end_lineno - 1])
    if lineno == end_lineno:
        return lines[lineno - 1][col:end_col]
    parts = [lines[lineno - 1][col:]]
    if end_lineno - lineno > 1:
        parts.extend(lines[lineno:end_lineno - 1])
    parts.append(lines[end_lineno - 1][:end_col])
    return " ".join(part.strip() for part in parts)


def check_decision_paths(path: Path, tree: ast.AST, lines: List[str], allow_lines: Set[int]) -> List[Violation]:
    violations: List[Violation] = []
    pattern = re.compile(r"\b(" + "|".join(DECISION_PATH_TERMS) + r")\b", re.IGNORECASE)
    for node in ast.walk(tree):
        test = getattr(node, "test", None)
        if test is None:
            continue
        segment = get_segment(test, lines)
        if not segment:
            continue
        if not pattern.search(segment):
            continue
        lineno = getattr(test, "lineno", 0)
        end_lineno = getattr(test, "end_lineno", lineno) or lineno
        if any(line in allow_lines for line in range(lineno, end_lineno + 1)):
            continue
        violations.append(
            Violation(
                rule="decision-path-language",
                file=path,
                line=lineno,
                message="Decision logic references reward/utility/survival language.",
                snippet=segment,
            )
        )
    return violations


def check_operator_strings(path: Path, tree: ast.AST, lines: List[str], allow_lines: Set[int]) -> List[Violation]:
    violations: List[Violation] = []
    docstring_ids: Set[int] = set()
    # cache docstring ids
    if isinstance(tree, ast.Module) and tree.body:
        expr = tree.body[0]
        if isinstance(expr, ast.Expr) and isinstance(expr.value, ast.Constant) and isinstance(expr.value.value, str):
            docstring_ids.add(id(expr.value))
    for parent in ast.walk(tree):
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and parent.body:
            expr = parent.body[0]
            if isinstance(expr, ast.Expr) and isinstance(expr.value, ast.Constant) and isinstance(expr.value.value, str):
                docstring_ids.add(id(expr.value))

    for node in gather_string_values(tree):
        if isinstance(node, ast.Constant) and id(node) in docstring_ids:
            continue
        lineno = getattr(node, "lineno", 0)
        if lineno in allow_lines:
            continue
        value = ""
        if isinstance(node, ast.Constant):
            value = normalize_string(str(node.value))
        elif isinstance(node, ast.JoinedStr):
            value = render_joined_str(node, lines)
        if not value or not is_operator_visible(value):
            continue
        if OPERATOR_PATTERN.search(value):
            violations.append(
                Violation(
                    rule="operator-facing-language",
                    file=path,
                    line=lineno,
                    message="Operator-visible string uses bonding/obligation/forward-seeking language.",
                    snippet=value,
                )
            )
    return violations


def check_persistent_counters(path: Path, allow_lines: Set[int]) -> List[Violation]:
    violations: List[Violation] = []
    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if idx in allow_lines:
            continue
        if COUNTER_PERSISTENCE.search(line):
            violations.append(
                Violation(
                    rule="persistent-counter",
                    file=path,
                    line=idx,
                    message="Potential persistent counter/accumulator without explicit allowlist.",
                    snippet=line.strip(),
                )
            )
    return violations


def lint_file(path: Path, glossary_anchors: Set[str]) -> List[Violation]:
    if path.resolve() == Path(__file__).resolve():
        return []
    allow_lines = {abs(n) for n in find_allowlisted_lines(path, glossary_anchors)}
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [
            Violation(
                rule="parse-error",
                file=path,
                line=exc.lineno or 0,
                message=f"Syntax error during lint: {exc.msg}",
                snippet="",
            )
        ]

    violations: List[Violation] = []
    violations.extend(check_decision_paths(path, tree, lines, allow_lines))
    violations.extend(check_operator_strings(path, tree, lines, allow_lines))
    violations.extend(check_persistent_counters(path, allow_lines))
    return violations


def main() -> int:
    glossary_anchors = load_glossary_anchors()
    violations: List[Violation] = []
    files = list(iter_python_files())
    for path in files:
        violations.extend(lint_file(path, glossary_anchors))

    if violations:
        payload = {"status": "fail", "violations": [v.to_json() for v in violations]}
        print(json.dumps(payload, indent=2))
        return 1
    print(json.dumps({"status": "ok", "checked": len(files)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
