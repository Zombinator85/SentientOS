from __future__ import annotations

import argparse
import json
import datetime
from pathlib import Path

from sentientos.privilege import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Privilege validation sequence: do not remove. See doctrine for details."""

require_admin_banner()  # Enforced: privilege validation sequence—do not remove. See doctrine.
require_lumos_approval()

RECAP_LOG = get_log_path("public_review_recap.jsonl", "PUBLIC_REVIEW_RECAP")


def _parse_sprint_ledger(path: Path = Path("docs/SPRINT_LEDGER.md")) -> tuple[dict[str, int], list[dict[str, str]]]:
    metrics: dict[str, int] = {}
    stories: list[dict[str, str]] = []
    if not path.exists():
        return metrics, stories
    lines = path.read_text(encoding="utf-8").splitlines()
    table = False
    for ln in lines:
        if ln.startswith("| Metric"):
            table = True
            continue
        if table:
            if ln.startswith("|"):
                cols = [c.strip() for c in ln.split("|") if c.strip()]
                if len(cols) >= 2:
                    name = cols[0].lower().replace(" ", "_")
                    try:
                        metrics[name] = int(cols[1])
                    except Exception:
                        continue
            else:
                table = False
        if ln.startswith("## Contributor Stories"):
            stories_start = True
            continue
        if "stories_start" in locals() and ln.startswith("-"):
            m = ln.split("**")
            if len(m) >= 3:
                contributor = m[1]
                story = ln.split("**:")[-1].strip()
                stories.append({"contributor": contributor, "story": story})
    return metrics, stories


def generate_recap() -> str:
    metrics, stories = _parse_sprint_ledger()
    lines = ["# First Public Review Recap", ""]
    if metrics:
        lines.append("## Metrics")
        for k, v in metrics.items():
            lines.append(f"- {k.replace('_', ' ').title()}: {v}")
        lines.append("")
    if stories:
        lines.append("## Contributor Stories")
        for s in stories:
            contributor = s.get("contributor") or s.get("saint")
            lines.append(f"- {contributor}: {s['story']}")
        lines.append("")
    return "\n".join(lines)


def log_recap(text: str) -> None:
    entry = {"timestamp": datetime.datetime.utcnow().isoformat(), "recap": text}
    RECAP_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RECAP_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate a public review recap")
    ap.add_argument("--out", help="Write recap markdown to file")
    args = ap.parse_args()
    recap = generate_recap()
    log_recap(recap)
    if args.out:
        Path(args.out).write_text(recap, encoding="utf-8")
        print(args.out)
    else:
        print(recap)


if __name__ == "__main__":  # pragma: no cover - CLI utility
    main()
