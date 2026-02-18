from __future__ import annotations

"""Portable verify_audits module entrypoint."""

from typing import Sequence

from scripts import verify_audits as verify_audits_script


def main(argv: Sequence[str] | None = None) -> int:
    return verify_audits_script.main(list(argv) if argv is not None else None)


if __name__ == "__main__":
    raise SystemExit(main())

