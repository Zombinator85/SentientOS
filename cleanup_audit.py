from __future__ import annotations
import json
from pathlib import Path
from typing import List

from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""


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


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    import argparse
    ap = argparse.ArgumentParser(description="Pre-audit cleanup")
    ap.add_argument("log")
    args = ap.parse_args()
    path = Path(args.log)
    out, bad = cleanup_audit(path)
    total = len(path.read_text(encoding="utf-8").splitlines())
    percent = 0 if total == 0 else len(bad) / total * 100
    print(f"Cleaned log written to {out}")
    print(f"{100-percent:.1f}% valid, {percent:.1f}% needing review")
    if bad:
        print("Lines needing review:", ", ".join(map(str, bad)))


if __name__ == "__main__":
    main()
