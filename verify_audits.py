from __future__ import annotations
import json
from pathlib import Path
from typing import List, Tuple

from admin_utils import require_admin_banner
import audit_immutability as ai

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

ROOT = Path(__file__).resolve().parent
CONFIG = Path("config/master_files.json")


def _load_config() -> dict[str, str]:
    if not CONFIG.exists():
        return {}
    try:
        return json.loads(CONFIG.read_text())
    except Exception:
        return {}


def check_file(path: Path, quarantine: bool = False) -> Tuple[bool, List[str]]:
    """Validate one audit log line by line.

    Returns True if the log passes integrity checks.
    If ``quarantine`` is True, invalid lines are written to ``*.bad``.
    """
    errors: List[str] = []
    bad_lines: List[str] = []
    prev = "0" * 64
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"{lineno}: {e.msg}")
            bad_lines.append(line)
            continue
        if not isinstance(entry, dict):
            errors.append(f"{lineno}: not a JSON object")
            bad_lines.append(line)
            continue
        digest = ai._hash_entry(entry["timestamp"], entry["data"], prev)
        current = entry.get("rolling_hash") or entry.get("hash")
        if current != digest:
            errors.append(f"{lineno}: hash mismatch")
            bad_lines.append(line)
            continue
        prev = current

    if quarantine and bad_lines:
        bad_path = path.with_suffix(path.suffix + ".bad")
        with bad_path.open("w", encoding="utf-8") as bf:
            bf.write("\n".join(bad_lines) + "\n")

    return len(errors) == 0, errors


def verify_audits(quarantine: bool = False) -> dict[str, List[str]]:
    results: dict[str, List[str]] = {}
    data = _load_config()
    for file in data.keys():
        path = Path(file)
        if not path.is_absolute():
            path = ROOT / path
        ok, errs = check_file(path, quarantine=quarantine)
        results[str(path)] = errs
    return results


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    res = verify_audits(quarantine=True)
    for file, errors in res.items():
        if not errors:
            print(f"{file}: valid")
        else:
            print(f"{file}: {len(errors)} issue(s)")
            for err in errors:
                print(f"  {err}")


if __name__ == "__main__":  # pragma: no cover
    main()
