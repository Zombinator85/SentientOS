# ── privilege_lint.py ──────────────────────────────────────────────
from __future__ import annotations

import ast

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

from privilege_lint.config import LintConfig, load_config
from privilege_lint.import_rules import apply_fix_imports, validate_import_sort
from privilege_lint.typehint_rules import validate_type_hints
from privilege_lint.shebang_rules import validate_shebang, apply_fix as fix_shebang
from privilege_lint.runner import parallel_validate, DEFAULT_WORKERS

from logging_config import get_log_path

DEFAULT_BANNER_ASCII = [
    "#  _____  _             _",
    "# |  __ \\| |           (_)",
    "# | |__) | |_   _  __ _ _ _ __   __ _",
    "# |  ___/| | | | |/ _` | | '_ \\ / _` |",
    "# | |    | | |_| | (_| | | | | | (_| |",
    "# |_|    |_\\__,_|\\__, |_|_| |_|\\__, |",
    "#                  __/ |         __/ |",
    "#                 |___/         |___/ ",
]
BANNER_ASCII = DEFAULT_BANNER_ASCII

FUTURE_IMPORT = "from __future__ import annotations"

# Optional real helpers (stubbed in CI)
try:
    from admin_utils import require_admin_banner, require_lumos_approval  # noqa: F401
except Exception:  # pragma: no cover
    def require_admin_banner() -> None: ...
    def require_lumos_approval() -> None: ...

# --------------------------------------------------------------------------- #
_IMPORT_RE = re.compile(r"^(from|import)\s+[A-Za-z0-9_. ,]+")


def get_banner(lines: list[str], banner_lines: list[str]) -> int | None:
    """Return end index of ASCII banner or None if not present."""
    idx = 0
    while idx < len(lines) and lines[idx].startswith(("#!", "# -*-")):
        idx += 1
    if len(lines) - idx < len(banner_lines):
        return None
    for off, text in enumerate(banner_lines):
        if lines[idx + off].rstrip() != text.rstrip():
            return None
    return idx + len(banner_lines) - 1


def validate_banner_order(lines: list[str], path: Path, banner_lines: list[str]) -> list[str]:
    """Ensure banner→future→docstring→imports order."""
    errors: list[str] = []
    idx = 0
    banner_end = get_banner(lines, banner_lines)
    if banner_end is not None:
        idx = banner_end + 1

    while idx < len(lines) and not lines[idx].strip():
        idx += 1

    if idx >= len(lines) or lines[idx].strip() != FUTURE_IMPORT:
        return [f"{path}: Banner and __future__ import must be first."]

    idx += 1

    # Determine end of module docstring, if any
    doc_end = None
    try:
        mod = ast.parse("\n".join(lines))
        doc = ast.get_docstring(mod)
        if doc is None:
            raise IndexError
        for node in mod.body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Str):
                doc_end = node.end_lineno - 1
                break
    except IndexError:
        doc_end = None
    except Exception:
        doc_end = None

    if doc_end is None:
        for i in range(idx, len(lines)):
            s = lines[i].lstrip()
            if s.startswith(('"""', "'''")):
                quote = s[:3]
                if s.count(quote) >= 2 and s.rstrip().endswith(quote):
                    doc_end = i
                else:
                    for j in range(i + 1, len(lines)):
                        if lines[j].rstrip().endswith(quote):
                            doc_end = j
                            break
                if doc_end is None:
                    doc_end = len(lines) - 1
                break

    if doc_end is None:
        doc_end = idx - 1

    for i in range(idx, len(lines)):
        s = lines[i].strip()
        if _IMPORT_RE.match(s) and s != FUTURE_IMPORT:
            if i < doc_end + 1:
                errors.append(f"{path}: imports must follow module docstring")
            break

    return errors


# ----------------------------- lint driver ---------------------------------- #
AUDIT_FILE = get_log_path("privileged_audit.jsonl", "PRIVILEGED_AUDIT_FILE")
AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)


def audit_use(tool: str, cmd: str) -> None:
    record = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "tool": tool,
        "command": cmd,
    }
    with open(AUDIT_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


class PrivilegeLinter:
    def __init__(self, config: LintConfig | None = None, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path.cwd()
        self.config = config or load_config(self.project_root)
        if self.config.banner_file:
            try:
                self.banner = Path(self.config.banner_file).read_text(encoding="utf-8").splitlines()
            except Exception:
                self.banner = DEFAULT_BANNER_ASCII
        else:
            self.banner = DEFAULT_BANNER_ASCII

    def validate(self, file_path: Path) -> list[str]:
        lines = file_path.read_text(encoding="utf-8").splitlines()
        issues = []
        if self.config.enforce_banner:
            issues.extend(validate_banner_order(lines, file_path, self.banner))
        if self.config.enforce_import_sort:
            issues.extend(validate_import_sort(lines, file_path, self.project_root))
        if self.config.enforce_type_hints:
            issues.extend(
                validate_type_hints(
                    lines,
                    file_path,
                    exclude_private=self.config.exclude_private,
                    fail_on_missing_return=self.config.fail_on_missing_return,
                )
            )
        if self.config.shebang_require:
            issues.extend(validate_shebang(file_path, self.config.shebang_require))
        return issues

    def apply_fix(self, file_path: Path) -> bool:
        original = file_path.read_text(encoding="utf-8").splitlines()
        lines = original[:]

        banner_end = get_banner(lines, self.banner)
        if banner_end is None:
            insert_at = 0
            while insert_at < len(lines) and lines[insert_at].startswith(("#!", "# -*-")):
                insert_at += 1
            lines[insert_at:insert_at] = self.banner
            banner_end = insert_at + len(self.banner) - 1

        if FUTURE_IMPORT in lines:
            idx = lines.index(FUTURE_IMPORT)
            if idx != banner_end + 1:
                line = lines.pop(idx)
                if idx < banner_end + 1:
                    banner_end -= 1
                lines.insert(banner_end + 1, line)

        # recalc docstring after banner/future adjustments
        try:
            mod = ast.parse("\n".join(lines))
            doc = ast.get_docstring(mod)
            doc_start = doc_end = None
            if doc is not None:
                for node in mod.body:
                    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Str):
                        doc_start = node.lineno - 1
                        doc_end = node.end_lineno - 1
                        break
        except Exception:
            doc_start = doc_end = None

        if doc_start is not None:
            move_lines: list[str] = []
            remove_idx: list[int] = []
            for i in range(doc_start):
                if _IMPORT_RE.match(lines[i]) and lines[i].strip() != FUTURE_IMPORT:
                    move_lines.append(lines[i])
                    remove_idx.append(i)
            for i in reversed(remove_idx):
                lines.pop(i)
            if move_lines:
                doc_end = doc_end - len([i for i in remove_idx if i <= doc_end])
                insert_pos = doc_end + 1
                for off, line in enumerate(move_lines):
                    lines.insert(insert_pos + off, line)

        if self.config.enforce_import_sort:
            apply_fix_imports(lines, self.project_root)

        changed = lines != original
        if changed:
            out_path = file_path if self.config.fix_overwrite else file_path.with_name(file_path.name + ".fixed")
            out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        if self.config.shebang_require:
            changed |= fix_shebang(file_path, self.config.shebang_fix_mode)
        return changed


def iter_py_files(paths: list[str]) -> list[Path]:
    result: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if d not in {"tests", "venv", "__pycache__"}]
                for f in files:
                    if f.endswith(".py"):
                        result.append(Path(root) / f)
        elif path.is_file() and path.suffix == ".py":
            result.append(path)
    return sorted(set(result))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Privilege banner linter")
    ap.add_argument("paths", nargs="*", default=[str(Path(__file__).resolve().parent)])
    ap.add_argument("--fix", action="store_true", help="Rewrite files in place")
    ap.add_argument("--quiet", action="store_true", help="Suppress output")
    ap.add_argument("--max-workers", type=int, default=None, help="Worker count for parallel scan")
    ap.add_argument("--show-hints", action="store_true", help="Print type hint violations in quiet mode")
    args = ap.parse_args(argv)

    linter = PrivilegeLinter()
    files = iter_py_files(args.paths)

    if args.fix:
        fixed = 0
        for fp in files:
            if linter.validate(fp):
                if linter.apply_fix(fp):
                    fixed += 1
        if not args.quiet:
            print(f"Fixed {fixed} files")
        return 0

    issues = parallel_validate(linter, files, args.max_workers)
    if issues:
        if not args.quiet or args.show_hints:
            print("\n".join(sorted(issues)))
        return 1
    return 0


if __name__ == "__main__":
    require_admin_banner()
    require_lumos_approval()
    sys.exit(main())
# ────────────────────────────────────────────────────────────
