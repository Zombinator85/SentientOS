"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
import ast
import argparse
import datetime
import json
import os
import re
import sys
import subprocess
import hashlib
from pathlib import Path
from privilege_lint.config import LintConfig, load_config
from privilege_lint.import_rules import apply_fix_imports, validate_import_sort
from privilege_lint.typehint_rules import validate_type_hints
from privilege_lint.typing_rules import run_incremental
from privilege_lint.data_rules import validate_json, validate_csv
from privilege_lint.shebang_rules import validate_shebang, apply_fix as fix_shebang
from privilege_lint.docstring_rules import validate_docstrings, apply_fix_docstring_stub
from privilege_lint.license_rules import (
    validate_license_header,
    apply_fix_license_header,
    DEFAULT_HEADER,
)
from privilege_lint.cache import LintCache
from privilege_lint.runner import parallel_validate, DEFAULT_WORKERS
from privilege_lint.template_rules import validate_template, parse_context
from privilege_lint.security_rules import validate_security
from privilege_lint.js_rules import validate_js
from privilege_lint.go_rules import validate_go
from privilege_lint._compat import RuleSkippedError
from privilege_lint.comment_controls import parse_controls, is_disabled
from privilege_lint.metrics import MetricsCollector
from privilege_lint.plugins import load_plugins
from logging_config import get_log_path
# ── privilege_lint_cli.py ─────────────────────────────────────────


# auto-approve when `CI` or `GIT_HOOKS` is set (see docs/ENVIRONMENT.md)
if os.getenv("LUMOS_AUTO_APPROVE") != "1" and (
    os.getenv("CI") or os.getenv("GIT_HOOKS")
):
    os.environ["LUMOS_AUTO_APPROVE"] = "1"

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


# --------------------------------------------------------------------------- #
_IMPORT_RE = re.compile(r"^(from|import)\s+[A-Za-z0-9_. ,]+")


def get_banner(lines: list[str], banner_lines: list[str]) -> int | None:
    """Return end index of ASCII banner or None if not present."""
    idx = 0
    while idx < len(lines) and lines[idx].startswith(("#!", "# -*-")):
        idx += 1

    if idx < len(lines):
        stripped = lines[idx].lstrip()
        if stripped.startswith(('"""', "'''")):
            quote = stripped[:3]
            idx += 1
            while idx < len(lines) and not lines[idx].rstrip().endswith(quote):
                idx += 1
            if idx < len(lines):
                idx += 1
            while idx < len(lines) and not lines[idx].strip():
                idx += 1

    if len(lines) - idx < len(banner_lines):
        return None
    for off, text in enumerate(banner_lines):
        if lines[idx + off].rstrip() != text.rstrip():
            return None
    return idx + len(banner_lines) - 1


def validate_banner_order(
    lines: list[str], path: Path, banner_lines: list[str]
) -> list[str]:
    """Ensure banner→future→docstring→imports order for CLI files."""
    if not _contains_cli_hint(path):
        return []
    errors: list[str] = []
    idx = 0
    banner_end = get_banner(lines, banner_lines)
    if banner_end is None:
        errors.append(f"{path}: missing privilege banner")
    else:
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
# uses PRIVILEGED_AUDIT_FILE if set, otherwise logs/privileged_audit.jsonl
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
    def __init__(
        self,
        config: LintConfig | None = None,
        project_root: Path | None = None,
        metrics: MetricsCollector | None = None,
    ) -> None:
        self.project_root = project_root or Path.cwd()
        self.config = config or load_config(self.project_root)
        self.metrics = metrics or MetricsCollector()
        self.cache = LintCache(
            self.project_root, self.config, enabled=self.config.cache
        )
        self.plugins = load_plugins()
        if self.config.policy:
            from policies import load_policy

            self.plugins.extend(load_policy(self.config.policy, self.project_root))
        if self.config.baseline_file:
            p = Path(self.config.baseline_file)
            if p.exists():
                try:
                    self.baseline = set(json.loads(p.read_text()).keys())
                except Exception:
                    self.baseline = set()
            else:
                self.baseline = set()
        else:
            self.baseline = set()
        if self.config.banner_file:
            try:
                self.banner = (
                    Path(self.config.banner_file)
                    .read_text(encoding="utf-8")
                    .splitlines()
                )
            except Exception:
                self.banner = DEFAULT_BANNER_ASCII
        else:
            self.banner = DEFAULT_BANNER_ASCII
        if self.config.license_header:
            path = Path(self.config.license_header)
            if path.exists():
                self.license_header = path.read_text(encoding="utf-8").strip()
            else:
                self.license_header = self.config.license_header.strip()
        else:
            self.license_header = ""

    def validate(self, file_path: Path) -> list[str]:
        lines = file_path.read_text(encoding="utf-8").splitlines()
        controls = parse_controls(lines)
        issues: list[str] = []

        def add(rule: str, errs: list[str]) -> None:
            filtered = []
            for e in errs:
                m = re.match(rf"{re.escape(str(file_path))}:(\d+)", e)
                line = int(m.group(1)) if m else 1
                if not is_disabled(controls, rule, line):
                    if e not in self.baseline:
                        filtered.append(e)
            self.metrics.record(rule, len(filtered))
            issues.extend(filtered)

        if self.config.enforce_banner:
            add("banner-order", validate_banner_order(lines, file_path, self.banner))
            add("admin-call", validate_admin_call(lines, file_path))
        if self.config.enforce_import_sort:
            add(
                "import-sort", validate_import_sort(lines, file_path, self.project_root)
            )
        if self.config.enforce_type_hints:
            add(
                "type-hint",
                validate_type_hints(
                    lines,
                    file_path,
                    exclude_private=self.config.exclude_private,
                    fail_on_missing_return=self.config.fail_on_missing_return,
                ),
            )
        if self.config.shebang_require:
            add("shebang", validate_shebang(file_path, self.config.shebang_require))
        if self.config.docstrings_enforce:
            add(
                "docstring",
                validate_docstrings(lines, file_path, self.config.docstring_style),
            )
        if self.license_header:
            add(
                "license",
                validate_license_header(lines, file_path, self.license_header),
            )
        if self.config.templates_enabled and file_path.suffix in {
            ".j2",
            ".hbs",
            ".jinja",
        }:
            ctx = self.config.templates_context or parse_context(lines)
            add("template", validate_template(file_path, ctx))
        if self.config.security_enabled and file_path.suffix == ".py":
            sec = validate_security(lines, file_path)
            for name, msgs in sec.items():
                add(name, msgs)
        for plugin in self.plugins:
            add(plugin.__name__, plugin(file_path, self.config))

        self.metrics.file_scanned()
        return issues

    def apply_fix(self, file_path: Path) -> bool:
        original = file_path.read_text(encoding="utf-8").splitlines()
        lines = original[:]

        banner_end = get_banner(lines, self.banner)
        if banner_end is None:
            insert_at = 0
            while insert_at < len(lines) and lines[insert_at].startswith(
                ("#!", "# -*-")
            ):
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

        changed = (
            apply_fix_license_header(lines, file_path, self.license_header)
            or lines != original
        )

        out_path = (
            file_path
            if self.config.fix_overwrite
            else file_path.with_name(file_path.name + ".fixed")
        )
        if changed:
            out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        if self.config.docstrings_enforce and self.config.docstring_insert_stub:
            changed |= apply_fix_docstring_stub(out_path, self.config.docstring_style)

        if self.config.shebang_require:
            changed |= fix_shebang(out_path, self.config.shebang_fix_mode)
        return changed


def _contains_cli_hint(fp: Path) -> bool:
    """Return True if file appears to be a CLI entrypoint."""
    if fp.name.endswith("_cli.py"):
        return True
    try:
        text = fp.read_text(encoding="utf-8")
    except Exception:
        return False
    if '__name__ == "__main__"' in text:
        return True
    return "argparse" in text


def validate_admin_call(lines: list[str], path: Path) -> list[str]:
    if not _contains_cli_hint(path):
        return []
    text = "\n".join(lines)
    return []


def iter_py_files(paths: list[str]) -> list[Path]:
    result: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if d not in {"venv", "__pycache__"}]
                for f in files:
                    if not f.endswith(".py"):
                        continue
                    fp = Path(root) / f
                    if "tests" in fp.parts and not _contains_cli_hint(fp):
                        continue
                    result.append(fp)
        elif path.is_file() and path.suffix == ".py":
            result.append(path)
    return sorted(set(result))


def iter_ext_files(paths: list[str], exts: set[str]) -> list[Path]:
    result: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            for root, dirs, files in os.walk(path):
                dirs[:] = [
                    d
                    for d in dirs
                    if d not in {"tests", "venv", "__pycache__", "node_modules"}
                ]
                for f in files:
                    if any(f.endswith(e) for e in exts):
                        result.append(Path(root) / f)
        elif path.is_file() and any(path.name.endswith(e) for e in exts):
            result.append(path)
    return sorted(set(result))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Privilege banner linter")
    ap.add_argument("paths", nargs="*", default=[str(Path(__file__).resolve().parent)])
    ap.add_argument("--fix", action="store_true", help="Rewrite files in place")
    ap.add_argument("--quiet", action="store_true", help="Suppress output")
    ap.add_argument(
        "--max-workers", type=int, default=None, help="Worker count for parallel scan"
    )
    ap.add_argument(
        "--show-hints",
        action="store_true",
        help="Print type hint violations in quiet mode",
    )
    ap.add_argument("--no-cache", action="store_true", help="Disable cache")
    ap.add_argument("--mypy", action="store_true", help="Force full mypy run")
    ap.add_argument(
        "--report-json", type=str, default=None, help="Write metrics JSON report"
    )
    ap.add_argument("--sarif", type=str, default=None, help="Write SARIF report")
    args = ap.parse_args(argv)

    metrics = MetricsCollector()
    linter = PrivilegeLinter(metrics=metrics)
    if args.no_cache:
        linter.cache.enabled = False
    files = iter_py_files(args.paths)
    js_files = (
        iter_ext_files(args.paths, {".js", ".ts"}) if linter.config.js_enabled else []
    )
    go_files = iter_ext_files(args.paths, {".go"}) if linter.config.go_enabled else []
    check_files = []
    for f in files + js_files + go_files:
        if linter.cache.is_valid(f):
            metrics.cache_hit()
        else:
            check_files.append(f)

    if args.fix:
        fixed = 0
        for fp in check_files:
            if linter.validate(fp):
                if linter.apply_fix(fp):
                    fixed += 1
            linter.cache.update(fp)
        linter.cache.save()
        if not args.quiet:
            print(f"Fixed {fixed} files")
        return 0

    issues = parallel_validate(
        linter, [f for f in check_files if f.suffix == ".py"], args.max_workers
    )
    other_files = [f for f in check_files if f.suffix in {".js", ".ts", ".go"}]
    for f in other_files:
        try:
            if f.suffix in {".js", ".ts"}:
                issues.extend(validate_js(f, linter.license_header))
            elif f.suffix == ".go":
                issues.extend(validate_go(f, linter.license_header))
        except RuleSkippedError:
            pass
    for fp in check_files:
        linter.cache.update(fp)

    if linter.config.mypy_enabled:
        mypy_targets = files if args.mypy else check_files
        mypy_issues, checked = run_incremental(
            mypy_targets,
            linter.cache,
            strict=linter.config.mypy_strict,
            force_full=args.mypy,
        )
        issues.extend(mypy_issues)
        checked_count = len(checked)

    if linter.config.data_paths:
        data_files = iter_data_files(linter.config.data_paths)
        for df in data_files:
            if linter.cache.is_valid(df):
                continue
            if df.suffix == ".json" and linter.config.data_check_json:
                issues.extend(validate_json(df))
            elif df.suffix == ".csv" and linter.config.data_check_csv:
                issues.extend(validate_csv(df))
            linter.cache.update(df)

    linter.cache.save()
    metrics.finish()
    if issues:
        if not args.quiet or args.show_hints:
            print("\n".join(sorted(issues)))
        return 1

    stamp_src = (
        linter.cache.cfg_hash
        + subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"]).decode().strip()
    )
    stamp = hashlib.sha1(stamp_src.encode()).hexdigest()
    (Path(".git") / ".privilege_lint.gitcache").write_text(stamp)
    report_path = args.report_json or (
        "plint_metrics.json" if linter.config.report_json else None
    )
    if report_path:
        metrics.write_json(Path(report_path))
    sarif_path = args.sarif or ("plint.sarif" if linter.config.sarif else None)
    if sarif_path:
        from reporters.sarif import write_sarif

        write_sarif(issues, Path(sarif_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
# ────────────────────────────────────────────────────────────
