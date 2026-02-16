"""Compatibility wrapper for the blessed scripts.verify_audits entrypoint."""

from __future__ import annotations

from scripts.verify_audits import *  # noqa: F401,F403
from scripts.verify_audits import main


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
