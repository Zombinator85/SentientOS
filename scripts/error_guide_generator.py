from __future__ import annotations
import argparse
import re
from pathlib import Path
from typing import List, Tuple

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()
require_lumos_approval()

RITUAL_DOC_LINK = "../RITUAL_FAILURES.md"
AUDIT_DOC_LINK = "../AUDIT_LOG_FIXES.md"


ERROR_REGEX = re.compile(r"(?P<file>[\w/]+\.\w+).*?(mismatch|error|fail)", re.IGNORECASE)


def parse_errors(content: str) -> List[Tuple[str, str]]:
    results = []
    for line in content.splitlines():
        m = ERROR_REGEX.search(line)
        if m:
            file = m.group('file')
            if 'mismatch' in line:
                err = 'prev hash mismatch'
            else:
                err = 'error'
            results.append((file, err))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate error resolution summary")
    parser.add_argument("output", nargs="?", default="docs/ERROR_RESOLUTION_SUMMARY.md")
    args = parser.parse_args()

    entries = []
    for doc in ["RITUAL_FAILURES.md", "AUDIT_LOG_FIXES.md"]:
        path = Path(doc)
        if path.exists():
            entries.extend(parse_errors(path.read_text(encoding="utf-8")))

    lines = ["# Error Resolution Summary", "", "| File/Test | Error | Command to Fix | Docs |", "|-----------|-------|---------------|------|"]
    for file, err in entries:
        cmd = f"python verify_audits.py {file}" if file.endswith('.jsonl') else "pytest"
        doc_link = f"[{doc}](../{doc})" if (doc := 'RITUAL_FAILURES.md' if 'jsonl' in file else 'AUDIT_LOG_FIXES.md') else ''
        lines.append(f"| {file} | {err} | {cmd} | {doc_link} |")

    Path(args.output).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
