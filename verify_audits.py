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


def check_file(path: Path, prev_digest: str = "0" * 64, quarantine: bool = False) -> Tuple[bool, List[str], str]:
    """Validate one audit log line by line.

    Returns True if the log passes integrity checks.
    If ``quarantine`` is True, invalid lines are written to ``*.bad``.
    """
    errors: List[str] = []
    bad_lines: List[str] = []
    prev = prev_digest
    first = True
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
        if entry.get("prev_hash") != prev:
            if first:
                errors.append(f"{lineno}: prev hash mismatch")
            else:
                errors.append(f"{lineno}: chain break")
        digest = ai._hash_entry(entry["timestamp"], entry["data"], entry.get("prev_hash", prev))
        current = entry.get("rolling_hash") or entry.get("hash")
        if current != digest:
            errors.append(f"{lineno}: hash mismatch")
            bad_lines.append(line)
            continue
        prev = current
        first = False

    if quarantine and bad_lines:
        bad_path = path.with_suffix(path.suffix + ".bad")
        with bad_path.open("w", encoding="utf-8") as bf:
            bf.write("\n".join(bad_lines) + "\n")

    return len(errors) == 0, errors, prev


def verify_audits(quarantine: bool = False, directory: Path | None = None) -> tuple[dict[str, List[str]], float]:
    """Verify multiple audit logs.

    If ``directory`` is provided, all ``*.jsonl`` files in that directory are
    processed in alphabetical order with rolling hash chaining across files.
    Otherwise the configuration in ``config/master_files.json`` is used.
    Returns a mapping of file paths to error lists and the percentage of logs
    that were fully valid.
    """

    results: dict[str, List[str]] = {}
    logs: List[Path] = []

    if directory is not None:
        logs = sorted(Path(directory).glob("*.jsonl"))
    else:
        data = _load_config()
        for file in data.keys():
            p = Path(file)
            if not p.is_absolute():
                p = ROOT / p
            logs.append(p)

    prev = "0" * 64
    valid = 0
    for path in logs:
        ok, errs, prev = check_file(path, prev, quarantine=quarantine)
        results[str(path)] = errs
        if not errs:
            valid += 1

    percent = 0.0 if not logs else valid / len(logs) * 100
    return results, percent


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    import argparse

    ap = argparse.ArgumentParser(description="Audit log verifier")
    ap.add_argument("path", nargs="?", help="Log directory or single file")
    args = ap.parse_args()

    directory = None
    if args.path:
        p = Path(args.path)
        if p.is_dir():
            directory = p
        else:
            directory = p.parent

    res, percent = verify_audits(quarantine=True, directory=directory)
    for file, errors in res.items():
        if not errors:
            print(f"{file}: valid")
        else:
            print(f"{file}: {len(errors)} issue(s)")
            for err in errors:
                print(f"  {err}")
    print(f"{percent:.1f}% of logs valid")


if __name__ == "__main__":  # pragma: no cover
    main()
