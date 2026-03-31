from __future__ import annotations

"""Bounded terminology check for public-facing SentientOS surfaces.

This check intentionally scans only engineering front-door docs and does not
police internal doctrine/culture documents.
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.public_language_map import PUBLIC_LANGUAGE_MAP

PUBLIC_DOC_PATHS = (
    Path("README.md"),
    Path("docs/USAGE.md"),
    Path("docs/ARCHITECTURE.md"),
    Path("docs/REVIEWER_QUICKSTART.md"),
    Path("docs/START_A_FEDERATION_NODE.md"),
)

ALLOWED_MARKERS = (
    "internal codename",
    "historical",
)
README_FRONTDOOR_MAX_LINE = 140


def _must_dual_label(term: str) -> bool:
    mapping = PUBLIC_LANGUAGE_MAP.get(term)
    if mapping is None:
        return False
    return mapping.classification == "replace"


def _line_is_exempt(line: str) -> bool:
    lowered = line.lower()
    return any(marker in lowered for marker in ALLOWED_MARKERS)


def _check_file(path: Path) -> list[str]:
    issues: list[str] = []
    abs_path = REPO_ROOT / path
    lines = abs_path.read_text(encoding="utf-8").splitlines()
    in_code_block = False
    for line_no, line in enumerate(lines, start=1):
        if path == Path("README.md") and line_no > README_FRONTDOOR_MAX_LINE:
            break
        lowered = line.lower()
        stripped = lowered.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block or stripped.startswith("|"):
            continue
        if _line_is_exempt(line):
            continue
        for term, mapping in PUBLIC_LANGUAGE_MAP.items():
            if not _must_dual_label(term):
                continue
            if re.search(rf"\b{re.escape(term)}\b", lowered) and mapping.public_term.lower() not in lowered:
                issues.append(
                    f"{path}:{line_no}: '{term}' should be dual-labeled with '{mapping.public_term}' on public docs"
                )
    return issues


def main() -> int:
    all_issues: list[str] = []
    for rel_path in PUBLIC_DOC_PATHS:
        abs_path = REPO_ROOT / rel_path
        if not abs_path.exists():
            all_issues.append(f"missing required public doc for terminology checks: {rel_path}")
            continue
        all_issues.extend(_check_file(rel_path))

    if all_issues:
        print("Public terminology check failed:")
        for issue in all_issues:
            print(f" - {issue}")
        return 1

    print("Public terminology check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
