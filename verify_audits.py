"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
import json
import os
from pathlib import Path
from typing import List, Tuple, Dict, Optional
import audit_immutability as ai
# enable auto-approve when `CI` or `GIT_HOOKS` is set (see docs/ENVIRONMENT.md)
if os.getenv("LUMOS_AUTO_APPROVE") != "1" and (
    os.getenv("CI") or os.getenv("GIT_HOOKS")
):
    os.environ["LUMOS_AUTO_APPROVE"] = "1"


ROOT = Path(__file__).resolve().parent
CONFIG = Path("config/master_files.json")


def _load_config() -> dict[str, str]:
    if not CONFIG.exists():
        return {}
    try:
        raw = json.loads(CONFIG.read_text())
        if isinstance(raw, dict):
            return {str(k): str(v) for k, v in raw.items()}
    except Exception:
        pass
    return {}


VALID_EXTS = {".jsonl", ".json", ".log"}


def _is_log_file(path: Path) -> bool:
    """Return True if the file looks like a valid audit log."""
    try:
        first = (
            path.read_text(encoding="utf-8", errors="ignore").lstrip().splitlines()[0]
        )
    except Exception:
        return False

    if path.suffix.lower() in VALID_EXTS:
        return first.startswith("{") and "timestamp" in first and "data" in first

    if (
        not path.suffix
        and first.startswith("{")
        and "timestamp" in first
        and "data" in first
    ):
        return True
    return False


def _attempt_repair(line: str) -> Optional[str]:
    """Try simple fixes for malformed JSON lines."""
    s = line.strip()
    # remove trailing comma
    if s.endswith(","):
        s = s[:-1]
    if not s.endswith("}"):
        s = s + "}"
    try:
        json.loads(s)
    except Exception:
        return None
    return s


def check_file(
    path: Path,
    prev_digest: str = "0" * 64,
    quarantine: bool = False,
    *,
    repair: bool = False,
    stats: Optional[Dict[str, int]] = None,
) -> Tuple[bool, List[str], str]:
    """Validate one audit log line by line.

    Returns True if the log passes integrity checks.
    If ``quarantine`` is True, invalid lines are written to ``*.bad``.
    """
    if stats is not None:
        stats.setdefault("fixed", 0)
        stats.setdefault("quarantined", 0)
        stats.setdefault("unrecoverable", 0)

    errors: List[str] = []
    bad_lines: List[str] = []
    repair_lines: List[str] = []
    prev = prev_digest
    first = True
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as e:
            if repair:
                fixed = _attempt_repair(line)
                if fixed is not None:
                    entry = json.loads(fixed)
                    repair_lines.append(fixed)
                    if stats is not None:
                        stats["fixed"] += 1
                else:
                    errors.append(f"{lineno}: {e.msg}")
                    bad_lines.append(line)
                    if stats is not None:
                        stats["quarantined"] += 1
                        stats["unrecoverable"] += 1
                    continue
            else:
                errors.append(f"{lineno}: {e.msg}")
                bad_lines.append(line)
                if stats is not None:
                    stats["quarantined"] += 1
                continue
        if not isinstance(entry, dict):
            errors.append(f"{lineno}: not a JSON object")
            bad_lines.append(line)
            if stats is not None:
                stats["quarantined"] += 1
                stats["unrecoverable"] += 1
            continue

        if entry.get("_void") is True:
            # Skip validation for explicit void entries
            continue
        if entry.get("prev_hash") != prev:
            if first:
                errors.append(f"{lineno}: prev hash mismatch")
            else:
                errors.append(f"{lineno}: chain break")
        if "data" not in entry:
            errors.append(f"{lineno}: missing data field")
            bad_lines.append(line)
            if stats is not None:
                stats["quarantined"] += 1
                stats["unrecoverable"] += 1
            continue
        digest = ai._hash_entry(
            entry["timestamp"], entry["data"], entry.get("prev_hash", prev)
        )
        current = entry.get("rolling_hash") or entry.get("hash")
        if current != digest:
            errors.append(f"{lineno}: hash mismatch")
            bad_lines.append(line)
            if stats is not None:
                stats["quarantined"] += 1
                stats["unrecoverable"] += 1
            continue
        prev = current
        first = False

    if quarantine and bad_lines:
        bad_path = path.with_suffix(path.suffix + ".bad")
        with bad_path.open("w", encoding="utf-8") as bf:
            bf.write("\n".join(bad_lines) + "\n")

    if repair and repair_lines:
        repair_path = path.with_suffix(path.suffix + ".repairable")
        with repair_path.open("w", encoding="utf-8") as rf:
            rf.write("\n".join(repair_lines) + "\n")

    return len(errors) == 0, errors, prev


def verify_audits(
    quarantine: bool = False,
    directory: Path | None = None,
    *,
    repair: bool = False,
) -> tuple[dict[str, List[str]], float, Dict[str, int]]:
    """Verify multiple audit logs.

    If ``directory`` is provided, all ``*.jsonl`` files in that directory are
    processed in alphabetical order with rolling hash chaining across files.
    Otherwise the configuration in ``config/master_files.json`` is used.
    Returns a mapping of file paths to error lists and the percentage of logs
    that were fully valid.
    """

    results: dict[str, List[str]] = {}
    logs: List[Path] = []
    stats: Dict[str, int] = {"fixed": 0, "quarantined": 0, "unrecoverable": 0}

    if directory is not None:
        logs = sorted(p for p in Path(directory).iterdir() if _is_log_file(p))
    else:
        data = _load_config()
        for file in data.keys():
            p = Path(file)
            if not p.is_absolute():
                p = ROOT / p
            if _is_log_file(p):
                logs.append(p)

    prev = "0" * 64
    valid = 0
    for path in logs:
        ok, errs, prev = check_file(
            path, prev, quarantine=quarantine, repair=repair, stats=stats
        )
        results[str(path)] = errs
        if not errs:
            valid += 1

    percent = 0.0 if not logs else valid / len(logs) * 100
    return results, percent, stats


def main() -> None:  # pragma: no cover - CLI
    import argparse

    ap = argparse.ArgumentParser(
        description="Audit log verifier",
        epilog="Set LUMOS_AUTO_APPROVE=1 to bypass prompts.",
    )
    ap.add_argument("path", nargs="?", help="Log directory or single file")
    ap.add_argument(
        "--repair",
        action="store_true",
        help="attempt to repair malformed lines and chain",
    )
    ap.add_argument("--auto-repair", action="store_true", help="heal logs then verify")
    ap.add_argument(
        "--check-only", action="store_true", help="verify without modifying logs"
    )
    ap.add_argument(
        "--auto-approve",
        action="store_true",
        help="skip prompts (deprecated, use --no-input)",
    )
    ap.add_argument("--no-input", action="store_true", help="skip prompts")
    args = ap.parse_args()

    auto_env = (
        args.auto_approve or args.no_input or os.getenv("LUMOS_AUTO_APPROVE") == "1"
    )
    if auto_env:
        os.environ["LUMOS_AUTO_APPROVE"] = "1"

    # STRICT=1 aborts if repairs occur (see docs/ENVIRONMENT.md)
    strict_env = os.getenv("STRICT") == "1"

    directory = None
    if args.path:
        p = Path(args.path)
        if p.is_dir():
            directory = p
        else:
            directory = p.parent

    logs: list[Path] = []
    if directory is not None:
        logs = sorted(p for p in Path(directory).iterdir() if _is_log_file(p))
    else:
        data = _load_config()
        for file in data.keys():
            q = Path(file)
            if not q.is_absolute():
                q = ROOT / q
            if _is_log_file(q):
                logs.append(q)

    # run initial verification without mutating logs
    res, percent, stats = verify_audits(
        quarantine=True,
        directory=directory,
        repair=args.repair and not args.check_only,
    )

    chain_ok = all(not e for e in res.values())
    total_fixed = 0

    if args.auto_repair and not chain_ok:
        from scripts import audit_repair

        prev = "0" * 64
        for log in logs:
            prev, fixed = audit_repair.repair_log(log, prev, check_only=False)
            total_fixed += fixed
        res, percent, stats = verify_audits(
            quarantine=True,
            directory=directory,
            repair=False,
        )
        chain_ok = all(not e for e in res.values())
    elif args.repair and not args.check_only:
        from scripts import audit_repair

        prev = "0" * 64
        for log in logs:
            prev, fixed = audit_repair.repair_log(log, prev, check_only=False)
            print(f"Repair {log.name}: {fixed} fixed")
            total_fixed += fixed
        res, percent, stats = verify_audits(
            quarantine=True,
            directory=directory,
            repair=False,
        )
        chain_ok = all(not e for e in res.values())
    for file, errors in res.items():
        if not errors:
            print(f"{file}: valid")
        else:
            print(f"{file}: {len(errors)} issue(s)")
            for err in errors:
                print(f"  {err}")
    print(f"{percent:.1f}% of logs valid")
    if args.repair or args.auto_repair:
        print(
            f"{stats['fixed']} lines fixed, {stats['quarantined']} lines quarantined, {stats['unrecoverable']} unrecoverable"
        )
    if (
        stats.get("fixed", 0) == 0
        and stats.get("quarantined", 0) == 0
        and stats.get("unrecoverable", 0) == 0
    ):
        print("✅ No mismatches.")
    if strict_env and total_fixed:
        print("Strict mode: repairs detected")
        raise SystemExit(1)
    if chain_ok:
        raise SystemExit(0)
    raise SystemExit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
