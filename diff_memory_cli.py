"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
require_admin_banner()
require_lumos_approval()
import argparse
import memory_diff_audit as mda
from admin_utils import require_admin_banner, require_lumos_approval



def main() -> None:
    parser = argparse.ArgumentParser(description="Compare memory sessions")
    parser.add_argument("session_a")
    parser.add_argument("session_b")
    args = parser.parse_args()

    entries_a = mda.load_entries(args.session_a)
    entries_b = mda.load_entries(args.session_b)

    diff = mda.build_diff(
        [mda.entry_repr(e) for e in entries_a],
        [mda.entry_repr(e) for e in entries_b],
    )
    for left, right, change in diff:
        if change:
            print(f"{change.upper()}: {left} -> {right}")

    core_a, emo_a = mda.extract_tags(entries_a)
    core_b, emo_b = mda.extract_tags(entries_b)
    if core_a != core_b:
        print("Core Added:", ", ".join(sorted(core_b - core_a)))
        print("Core Removed:", ", ".join(sorted(core_a - core_b)))
    if emo_a != emo_b:
        print("Emotion Added:", ", ".join(sorted(emo_b - emo_a)))
        print("Emotion Removed:", ", ".join(sorted(emo_a - emo_b)))


if __name__ == "__main__":
    main()
