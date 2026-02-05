from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET_DIRS = (
    REPO_ROOT / "scripts",
    REPO_ROOT / "docs",
    REPO_ROOT / ".github" / "workflows",
    REPO_ROOT / "workflows",
)
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "node_modules",
}
ALLOWED_SUFFIXES = {
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".bat",
    ".cmd",
    ".yml",
    ".yaml",
    ".md",
    ".txt",
    ".ini",
    ".toml",
    ".cfg",
    ".mk",
}


def _iter_target_files() -> list[Path]:
    files: list[Path] = []
    for root in TARGET_DIRS:
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for filename in filenames:
                path = Path(dirpath) / filename
                if path.suffix and path.suffix not in ALLOWED_SUFFIXES:
                    continue
                if not path.suffix and path.name not in {"Makefile", "makefile"}:
                    continue
                files.append(path)
    return files


def _line_has_pytest_command(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return False
    if "pytest" not in stripped:
        return False
    if "python -m pytest" in stripped or "python3 -m pytest" in stripped or "py -m pytest" in stripped:
        return True
    if stripped.startswith("pytest ") or stripped == "pytest":
        return True
    if stripped.startswith("$ pytest") or stripped.startswith("> pytest"):
        return True
    if "run: pytest" in stripped or "run: python -m pytest" in stripped or "run: python3 -m pytest" in stripped:
        return True
    return False


def main() -> int:
    violations: list[str] = []
    for path in _iter_target_files():
        try:
            content = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for idx, line in enumerate(content, start=1):
            if _line_has_pytest_command(line):
                violations.append(f"{path.relative_to(REPO_ROOT)}:{idx}: {line.strip()}")
    if violations:
        print(
            "Raw pytest invocations are disallowed. "
            "Editable install required; use python -m scripts.run_tests instead."
        )
        print("\n".join(violations))
        return 1
    print("pytest airlock guard: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
