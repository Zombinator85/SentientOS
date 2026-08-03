"""Verify the minimal/default and explicit capability dependency boundaries."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_DEFAULT = {
    "brainflow", "comtypes", "librosa", "llvmlite", "matplotlib", "mne",
    "numba", "numpy", "pandas", "playsound", "pyarrow", "pywin32",
    "pywin32-ctypes", "pypiwin32", "scipy", "sounddevice",
    "speechrecognition", "streamlit", "transformers", "vosk",
}
WINDOWS_ONLY = {"pywin32", "pywin32-ctypes", "pypiwin32", "comtypes"}


def _requirement_lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith(("#", "-r"))]


def _canonical(items: list[str]) -> list[str]:
    return sorted(str(Requirement(item)) for item in items)


def _name(item: str) -> str:
    return str(canonicalize_name(Requirement(item).name))


def verify(root: Path = ROOT) -> dict[str, object]:
    root_lines = root.joinpath("requirements.txt").read_text(encoding="utf-8").splitlines()
    minimal = _requirement_lines(root / "requirements-codex.txt")
    full = _requirement_lines(root / "requirements-full.txt")
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    core = list(project.get("dependencies", []))
    groups = {key: list(value) for key, value in project["optional-dependencies"].items()}
    default_names = {_name(item) for item in core + minimal}
    forbidden = sorted(default_names & FORBIDDEN_DEFAULT)
    parity = _canonical(minimal) == _canonical(groups.get("codex", []))
    root_delegate = [line.strip() for line in root_lines if line.strip() and not line.startswith("#")]
    platform_marked = sorted(
        item for item in full + [dep for values in groups.values() for dep in values]
        if Requirement(item).marker is not None
    )
    windows_errors = sorted({item for item in full + groups.get("windows", [])
                             if _name(item) in WINDOWS_ONLY and
                             (Requirement(item).marker is None or "win32" not in str(Requirement(item).marker))})
    all_explicit = full + [dep for name, values in groups.items() if name != "codex" for dep in values]
    legacy_names = {_name(item) for item in full}
    preserved = legacy_names <= {_name(item) for item in all_explicit}
    seen: dict[tuple[str, str], set[str]] = defaultdict(set)
    for group, values in {"core": core, "codex": minimal, **groups}.items():
        for item in values:
            req = Requirement(item)
            seen[(group, canonicalize_name(req.name))].add(f"{req.specifier};{req.marker or ''}")
    conflicts = sorted(f"{group}:{name}" for (group, name), specs in seen.items()
                       if len(specs) > 1 and not all("python_version" in spec for spec in specs))
    errors = []
    if root_delegate != ["-r requirements-codex.txt"]:
        errors.append("root_requirements_bypasses_canonical_minimal")
    if forbidden:
        errors.append("forbidden_package_in_default_surface")
    if not parity:
        errors.append("codex_extra_parity_failure")
    if windows_errors:
        errors.append("windows_marker_missing")
    if conflicts:
        errors.append("conflicting_constraints")
    result: dict[str, object] = {
        "schema_version": "sentientos.dependency_bootstrap:v1",
        "core_project_dependencies": _canonical(core),
        "minimal_automation_dependencies": _canonical(minimal),
        "optional_groups": {key: _canonical(value) for key, value in sorted(groups.items())},
        "full_capability_dependencies": _canonical(full),
        "platform_marked_dependencies": platform_marked,
        "forbidden_packages_found_in_default_surfaces": forbidden,
        "codex_extra_parity": parity,
        "root_delegates_to_canonical_minimal": root_delegate == ["-r requirements-codex.txt"],
        "legacy_dependencies_preserved": preserved,
        "windows_marker_errors": windows_errors,
        "duplicate_or_conflicting_constraints": conflicts,
        "errors": errors,
        "status": "ready" if not errors else "failed",
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    result = verify(args.root)
    print(json.dumps(result, sort_keys=True, indent=None if args.summary else 2))
    return 0 if result["status"] == "ready" else 1


if __name__ == "__main__":
    sys.exit(main())
