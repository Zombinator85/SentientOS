import argparse
import json
from pathlib import Path
from difflib import SequenceMatcher
import csv
from datetime import datetime


def load_entries(path: str) -> list[dict]:
    p = Path(path)
    entries: list[dict] = []
    if p.is_dir():
        for fp in sorted(p.glob("*.json")):
            try:
                entries.append(json.loads(fp.read_text(encoding="utf-8")))
            except Exception:
                continue
    else:
        lines = p.read_text(encoding="utf-8").splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
    entries.sort(key=lambda x: x.get("timestamp", ""))
    return entries


def entry_repr(entry: dict) -> str:
    ts = entry.get("timestamp", "")
    text = str(entry.get("text", "")).strip().replace("|", "\\|")
    text = text.replace("\n", " ")
    return f"[{ts}] {text}"


def extract_tags(entries: list[dict]) -> tuple[set[str], set[str]]:
    core = set()
    emo = set()
    for e in entries:
        for t in e.get("tags", []):
            low = t.lower()
            if "core" in low and "value" in low:
                core.add(t)
            if "emotion" in low:
                emo.add(t)
    return core, emo


def build_diff(a: list[str], b: list[str]) -> list[tuple[str, str, str]]:
    matcher = SequenceMatcher(None, a, b)
    rows: list[tuple[str, str, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                rows.append((a[i1 + k], b[j1 + k], ""))
        elif tag == "delete":
            for k in range(i1, i2):
                rows.append((a[k], "", "deleted"))
        elif tag == "insert":
            for k in range(j1, j2):
                rows.append(("", b[k], "added"))
        elif tag == "replace":
            count = max(i2 - i1, j2 - j1)
            for k in range(count):
                left = a[i1 + k] if i1 + k < i2 else ""
                right = b[j1 + k] if j1 + k < j2 else ""
                rows.append((left, right, "changed"))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="SentientOS memory diff auditor")
    parser.add_argument("snapshot_a")
    parser.add_argument("snapshot_b")
    parser.add_argument("-o", "--output", default="memory_diff_report.md")
    parser.add_argument("--csv", help="Optional CSV output path")
    args = parser.parse_args()

    entries_a = load_entries(args.snapshot_a)
    entries_b = load_entries(args.snapshot_b)

    core_a, emo_a = extract_tags(entries_a)
    core_b, emo_b = extract_tags(entries_b)

    core_added = core_b - core_a
    core_removed = core_a - core_b
    emo_added = emo_b - emo_a
    emo_removed = emo_a - emo_b

    lines_a = [entry_repr(e) for e in entries_a]
    lines_b = [entry_repr(e) for e in entries_b]

    diff_rows = build_diff(lines_a, lines_b)

    md_lines = []
    md_lines.append("# Memory Diff Audit\n")
    md_lines.append(f"Generated {datetime.utcnow().isoformat()} UTC\n\n")
    md_lines.append(f"Comparing `{args.snapshot_a}` and `{args.snapshot_b}`\n\n")

    md_lines.append("## Core Value Tag Changes\n")
    if core_added or core_removed:
        if core_added:
            md_lines.append(f"- Added: {', '.join(sorted(core_added))}\n")
        if core_removed:
            md_lines.append(f"- Removed: {', '.join(sorted(core_removed))}\n")
    else:
        md_lines.append("No core value tag changes detected.\n")

    md_lines.append("\n## Emotion Tag Changes\n")
    if emo_added or emo_removed:
        if emo_added:
            md_lines.append(f"- Added: {', '.join(sorted(emo_added))}\n")
        if emo_removed:
            md_lines.append(f"- Removed: {', '.join(sorted(emo_removed))}\n")
    else:
        md_lines.append("No emotion tag changes detected.\n")

    md_lines.append("\n## Diff\n")
    md_lines.append("| Snapshot A | Snapshot B | Change |\n")
    md_lines.append("|---|---|---|\n")
    for left, right, change in diff_rows:
        md_lines.append(f"| {left} | {right} | {change} |\n")

    Path(args.output).write_text("".join(md_lines), encoding="utf-8")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["snapshot_a", "snapshot_b", "change"])
            writer.writerows(diff_rows)


if __name__ == "__main__":
    main()
