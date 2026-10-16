"""Installed production chat entrypoint with a pre-import source-generation check."""
from __future__ import annotations

import argparse
from pathlib import Path


def _verify_expected_source_generation() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--expected-software-generation-digest")
    args, _unknown = parser.parse_known_args()
    if args.expected_software_generation_digest is None:
        return
    from sentientos.chat_process_generation import source_generation
    root = Path(__file__).resolve().parents[1]
    observed, _members = source_generation(root)
    if observed != args.expected_software_generation_digest:
        raise SystemExit("chat_process_preimport_source_generation_mismatch")


_verify_expected_source_generation()

from sentientos.chat_service import main


if __name__ == "__main__":
    main()
