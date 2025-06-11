"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
import json
from pathlib import Path
from typing import List
def cleanup_audit(path: Path) -> tuple[Path, List[int]]:
    valid_lines: List[str] = []
    bad_lines: List[int] = []
    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            json.loads(line)
            valid_lines.append(line)
        except json.JSONDecodeError:
            bad_lines.append(idx)
    out_path = path.with_suffix(path.suffix + ".clean")
    with out_path.open("w", encoding="utf-8") as f:
        for l in valid_lines:
            f.write(l + "\n")
    return out_path, bad_lines


def cleanup_directory(directory: Path) -> tuple[dict[str, List[int]], float]:
    """Clean all ``*.jsonl`` logs in ``directory``.

    Returns a mapping of log paths to bad line numbers and the overall percentage
    of valid lines.
    """
    results: dict[str, List[int]] = {}
    total_lines = 0
    total_bad = 0
    for log in sorted(Path(directory).glob("*.jsonl")):
        out, bad = cleanup_audit(log)
        results[str(log)] = bad
        lines = len(log.read_text(encoding="utf-8").splitlines())
        total_lines += lines
        total_bad += len(bad)
    percent = 0.0 if total_lines == 0 else (total_lines - total_bad) / total_lines * 100
    return results, percent


def main() -> None:  # pragma: no cover - CLI
    import argparse
    ap = argparse.ArgumentParser(description="Pre-audit cleanup")
    ap.add_argument("path", help="Log file or directory")
    args = ap.parse_args()
    p = Path(args.path)
    if p.is_dir():
        res, percent = cleanup_directory(p)
        print(f"{percent:.1f}% of all lines valid")
        for file, bad in res.items():
            if bad:
                print(f"{file}: lines needing review -> {', '.join(map(str, bad))}")
    else:
        out, bad = cleanup_audit(p)
        total = len(p.read_text(encoding='utf-8').splitlines())
        percent = 0 if total == 0 else len(bad) / total * 100
        print(f"Cleaned log written to {out}")
        print(f"{100-percent:.1f}% valid, {percent:.1f}% needing review")
        if bad:
            print("Lines needing review:", ", ".join(map(str, bad)))


if __name__ == "__main__":
    main()
