from __future__ import annotations

"""Terminology enforcement for public-facing SentientOS surfaces.

This checker intentionally targets user-facing docs and selected CLI/help text
sources. It does not enforce terminology in internal archives or low-level
runtime internals.
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
    Path("CONTRIBUTING.md"),
    Path("INSTALL.md"),
    Path("docs/USAGE.md"),
    Path("docs/ARCHITECTURE.md"),
    Path("docs/PUBLIC_LANGUAGE_BRIDGE.md"),
    Path("docs/GLOSSARY.md"),
    Path("docs/REVIEWER_QUICKSTART.md"),
    Path("docs/START_A_FEDERATION_NODE.md"),
    Path("docs/ONBOARDING_WALKTHROUGH.md"),
    Path("docs/FIRST_WOUND_ONBOARDING.md"),
    Path("docs/RITUAL_ONBOARDING.md"),
)

PUBLIC_CLI_PATHS = (
    Path("cli/sentientos_cli.py"),
    Path("doctrine_cli.py"),
    Path("federation_cli.py"),
    Path("treasury_cli.py"),
    Path("ritual_digest_cli.py"),
    Path("wdm_cli.py"),
)

ALLOWED_MARKERS = (
    "internal codename",
    "legacy",
    "historical",
    "compatibility",
)
README_FRONTDOOR_MAX_LINE = 220


def _is_deprecated_public_term(term: str) -> bool:
    mapping = PUBLIC_LANGUAGE_MAP.get(term)
    if mapping is None:
        return False
    return mapping.migration_status in {"deprecated_public_term", "replace_public_term"}


def _line_is_exempt(line: str) -> bool:
    lowered = line.lower()
    return any(marker in lowered for marker in ALLOWED_MARKERS)


def _iter_target_lines(path: Path, lines: list[str]) -> list[tuple[int, str]]:
    if path.suffix == ".md":
        return list(enumerate(lines, start=1))

    targets: list[tuple[int, str]] = []
    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if any(key in stripped for key in ("description=", "help=", "epilog=", "print(")) and (
            '"' in line or "'" in line
        ):
            targets.append((line_no, line))
    return targets


def _check_file(path: Path) -> list[str]:
    issues: list[str] = []
    abs_path = REPO_ROOT / path
    lines = abs_path.read_text(encoding="utf-8").splitlines()
    in_code_block = False

    for line_no, line in _iter_target_lines(path, lines):
        if path == Path("README.md") and line_no > README_FRONTDOOR_MAX_LINE:
            break
        lowered = line.lower()
        stripped = lowered.strip()
        if path.suffix == ".md":
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block or stripped.startswith("|"):
                continue
        if _line_is_exempt(line):
            continue

        for term, mapping in PUBLIC_LANGUAGE_MAP.items():
            if not _is_deprecated_public_term(term):
                continue
            if re.search(rf"\b{re.escape(term)}\b", lowered) and mapping.normalized_term.lower() not in lowered:
                issues.append(
                    f"{path}:{line_no}: '{term}' should use '{mapping.normalized_term}' or be explicitly marked legacy"
                )
    return issues


def main() -> int:
    all_issues: list[str] = []
    for rel_path in (*PUBLIC_DOC_PATHS, *PUBLIC_CLI_PATHS):
        abs_path = REPO_ROOT / rel_path
        if not abs_path.exists():
            all_issues.append(f"missing required public terminology file: {rel_path}")
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
