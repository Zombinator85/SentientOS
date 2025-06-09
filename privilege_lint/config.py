from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
import yaml


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


_DEFAULT = LintConfig()


def _load_file(path: Path) -> dict:
    if path.suffix == ".toml":
        return tomllib.loads(path.read_text(encoding="utf-8"))
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
                )
    return _DEFAULT
