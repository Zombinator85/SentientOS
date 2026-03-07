from __future__ import annotations

"""Portable verify_audits module entrypoint."""

from collections.abc import Sequence

from sentientos.audit_tools import verify_audits_main


def main(argv: Sequence[str] | None = None) -> int:
    return int(verify_audits_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
