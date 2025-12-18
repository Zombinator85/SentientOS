"""Glossary linter enforcing canonical vocabulary across the repository."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
GLOSSARY_PATH = ROOT / "config" / "canonical_glossary.json"
REPORT_PATH = ROOT / "lint" / "semantic_violations.jsonl"
TARGET_EXTENSIONS = {".py", ".md", ".json"}
DISABLE_TOKEN = "lint: disable-glossary"


class GlossaryViolation(Tuple[str, int, str, str, str]):
    """Typed tuple for storing violation details."""

    file_path: str
    line_number: int
    matched_term: str
    canonical_term: str
    severity: str


def load_glossary(path: Path) -> Dict[str, List[str]]:
    with path.open(encoding="utf-8") as glossary_file:
        return json.load(glossary_file)


def build_patterns(glossary: Dict[str, Iterable[str]]) -> List[Tuple[re.Pattern[str], str, str]]:
    patterns: List[Tuple[re.Pattern[str], str, str]] = []
    for canonical, synonyms in glossary.items():
        for synonym in synonyms:
            pattern = re.compile(rf"\b{re.escape(synonym)}\b", flags=re.IGNORECASE)
            patterns.append((pattern, canonical, synonym))
    return patterns


def should_skip_dir(dirname: str) -> bool:
    return dirname in {".git", "__pycache__"}


def scan_file(path: Path, patterns: List[Tuple[re.Pattern[str], str, str]]) -> List[GlossaryViolation]:
    violations: List[GlossaryViolation] = []
    disabled = False
    try:
        with path.open(encoding="utf-8", errors="ignore") as file_handle:
            for idx, line in enumerate(file_handle, start=1):
                if DISABLE_TOKEN in line:
                    disabled = True
                if disabled:
                    continue
                for pattern, canonical, synonym in patterns:
                    match = pattern.search(line)
                    if match:
                        matched_text = match.group(0)
                        violation: GlossaryViolation = (
                            str(path.relative_to(ROOT)),
                            idx,
                            matched_text,
                            canonical,
                            "soft",
                        )
                        violations.append(violation)
    except (UnicodeDecodeError, OSError):
        return violations
    return violations


def write_report(violations: List[GlossaryViolation]) -> None:
    REPORT_PATH.parent.mkdir(exist_ok=True)
    with REPORT_PATH.open("w", encoding="utf-8") as report_file:
        for violation in violations:
            record = {
                "file": violation[0],
                "line": violation[1],
                "matched_term": violation[2],
                "canonical_term": violation[3],
                "severity": violation[4],
            }
            json.dump(record, report_file)
            report_file.write("\n")


def lint_repository() -> int:
    glossary = load_glossary(GLOSSARY_PATH)
    patterns = build_patterns(glossary)
    violations: List[GlossaryViolation] = []

    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if not should_skip_dir(d)]
        for file_name in files:
            path = Path(root) / file_name
            if path == REPORT_PATH or path == GLOSSARY_PATH:
                continue
            if path.suffix.lower() not in TARGET_EXTENSIONS:
                continue
            violations.extend(scan_file(path, patterns))

    write_report(violations)
    return len(violations)


def main() -> int:
    violation_count = lint_repository()
    print(f"Glossary violations found: {violation_count}")
    if violation_count:
        print(f"Report written to: {REPORT_PATH}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
