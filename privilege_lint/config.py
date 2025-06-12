from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import tomllib

yaml: Any | None
try:  # optional dependency for YAML config files
    import yaml as _yaml  # type: ignore[import-untyped,unused-ignore]  # justified: optional dependency
    yaml = _yaml
except Exception:  # pragma: no cover - fallback when PyYAML is missing
    yaml = None
    import sys
    print(
        "Warning: optional dependency PyYAML missing; YAML configs will be ignored",
        file=sys.stderr,
    )


@dataclass
class LintConfig:
    enforce_banner: bool = True
    enforce_import_sort: bool = False
    banner_file: str | None = None
    fix_overwrite: bool = True
    enforce_type_hints: bool = False
    exclude_private: bool = True
    fail_on_missing_return: bool = True
    shebang_require: bool = False
    shebang_fix_mode: bool = False
    docstrings_enforce: bool = False
    docstring_style: str = "google"
    docstring_insert_stub: bool = False
    license_header: str | None = None
    cache: bool = True
    mypy_enabled: bool = False
    mypy_strict: bool = True
    data_paths: list[str] | None = None  # to be replaced after load_config
    data_check_json: bool = False
    data_check_csv: bool = False
    templates_enabled: bool = False
    templates_context: list[str] | None = None
    security_enabled: bool = False
    report_json: bool = False
    sarif: bool = False
    js_enabled: bool = False
    go_enabled: bool = False
    baseline_file: str | None = None
    policy: str | None = None


_DEFAULT = LintConfig(
    data_paths=[],
    templates_context=[],
    js_enabled=False,
    go_enabled=False,
    baseline_file=None,
    policy=None,
)


def _load_file(path: Path) -> dict[str, Any]:
    if path.suffix == ".toml":
        return tomllib.loads(path.read_text(encoding="utf-8"))
    if yaml is None:
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_config(start: Path | None = None) -> LintConfig:
    """Search for a config file and return a populated LintConfig."""
    if start is None:
        start = Path.cwd()
    for folder in [start, *start.parents]:
        for name in ("privilege_lint.toml", "privilege_lint.yaml", "privilege_lint.yml"):
            cfg_path = folder / name
            if cfg_path.exists():
                data = _load_file(cfg_path).get("lint", {})
                shebang = data.get("shebang", {})
                docs = data.get("docstrings", {})
                mypy = data.get("mypy", {})
                datacfg = data.get("data", {})
                templates = data.get("templates", {})
                security = data.get("security", {})
                output = data.get("output", {})
                js = data.get("js", {})
                go = data.get("go", {})
                return LintConfig(
                    enforce_banner=bool(data.get("enforce_banner", _DEFAULT.enforce_banner)),
                    enforce_import_sort=bool(data.get("enforce_import_sort", _DEFAULT.enforce_import_sort)),
                    banner_file=data.get("banner_file", _DEFAULT.banner_file),
                    fix_overwrite=bool(data.get("fix_overwrite", _DEFAULT.fix_overwrite)),
                    enforce_type_hints=bool(data.get("enforce_type_hints", _DEFAULT.enforce_type_hints)),
                    exclude_private=bool(data.get("exclude_private", _DEFAULT.exclude_private)),
                    fail_on_missing_return=bool(data.get("fail_on_missing_return", _DEFAULT.fail_on_missing_return)),
                    shebang_require=bool(shebang.get("require", _DEFAULT.shebang_require)),
                    shebang_fix_mode=bool(shebang.get("fix_mode", _DEFAULT.shebang_fix_mode)),
                    docstrings_enforce=bool(docs.get("enforce", _DEFAULT.docstrings_enforce)),
                    docstring_style=str(docs.get("style", _DEFAULT.docstring_style)),
                    docstring_insert_stub=bool(docs.get("insert_stub", _DEFAULT.docstring_insert_stub)),
                    license_header=data.get("license_header", _DEFAULT.license_header),
                    cache=bool(data.get("cache", _DEFAULT.cache)),
                    mypy_enabled=bool(mypy.get("enabled", _DEFAULT.mypy_enabled)),
                    mypy_strict=bool(mypy.get("strict", _DEFAULT.mypy_strict)),
                    data_paths=list(datacfg.get("paths", _DEFAULT.data_paths)),
                    data_check_json=bool(datacfg.get("check_json", _DEFAULT.data_check_json)),
                    data_check_csv=bool(datacfg.get("check_csv", _DEFAULT.data_check_csv)),
                    templates_enabled=bool(templates.get("enabled", _DEFAULT.templates_enabled)),
                    templates_context=list(templates.get("context", [])),
                    security_enabled=bool(security.get("enabled", _DEFAULT.security_enabled)),
                    report_json=bool(output.get("report_json", _DEFAULT.report_json)),
                    sarif=bool(output.get("sarif", _DEFAULT.sarif)),
                    js_enabled=bool(js.get("enabled", _DEFAULT.js_enabled)),
                    go_enabled=bool(go.get("enabled", _DEFAULT.go_enabled)),
                    baseline_file=data.get("baseline", _DEFAULT.baseline_file),
                    policy=data.get("policy", _DEFAULT.policy),
                )
    return _DEFAULT
