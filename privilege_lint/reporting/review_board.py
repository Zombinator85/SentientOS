from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

from .narrator import NarratorLink
from .report_router import ReportRouter
from .models import PrivilegeReport


@dataclass
class ReviewBoardHook:
    """Bridge privilege lint results into the amendment review board."""

    router: ReportRouter
    narrator: NarratorLink | None = None
    logger: logging.Logger = logging.getLogger(__name__)

    def enforce(
        self,
        *,
        spec_id: str,
        proposal_id: str,
        requested_format: str | None = None,
        paths: Sequence[str] | None = None,
    ) -> PrivilegeReport:
        report, _, archive_path, fmt = self.router.generate(
            requested_format, paths=paths
        )
        self.logger.debug(
            "ReviewBoardHook processed privilege report for %s/%s in %s format.",
            spec_id,
            proposal_id,
            fmt,
        )
        if self.narrator:
            self.narrator.narrate_amendment(
                report,
                spec_id=spec_id,
                proposal_id=proposal_id,
                archive_path=archive_path,
            )
        return report
