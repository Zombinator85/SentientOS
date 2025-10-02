from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from .models import PrivilegeReport


Emitter = Callable[[str], None]


class NarratorLink:
    """Narrate privilege lint outcomes for ceremony and amendment flows."""

    def __init__(self, emitter: Emitter | None = None) -> None:
        self._logger = logging.getLogger(__name__)
        self._emitter = emitter or self._logger.info

    def announce_boot(self, report: PrivilegeReport, *, archive_path: Path | None = None) -> None:
        message = report.summary()
        if archive_path:
            message = f"{message} (archive: {archive_path})"
        self._emit(message)

    def narrate_amendment(
        self,
        report: PrivilegeReport,
        *,
        spec_id: str,
        proposal_id: str,
        archive_path: Path | None = None,
    ) -> None:
        prefix = f"Amendment privilege check for {spec_id} ({proposal_id})"
        if report.passed:
            message = f"{prefix}: sanctuary privilege intact."
        else:
            suffix = "issue" if report.issue_count == 1 else "issues"
            message = (
                f"{prefix}: sanctuary privilege compromised ({report.issue_count} {suffix})."
            )
        if archive_path:
            message = f"{message} Archive: {archive_path}"
        self._emit(message)

    def _emit(self, message: str) -> None:
        try:
            self._emitter(message)
        except Exception:  # pragma: no cover - defensive logging
            self._logger.exception("Failed to narrate privilege status: %s", message)
