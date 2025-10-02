from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

from .error_handler import ErrorHandler
from .format_engines import FormatEngine, JSONFormatEngine, MarkdownFormatEngine, YAMLFormatEngine
from .models import LintExecution, PrivilegeReport


Runner = Callable[..., LintExecution]


@dataclass
class ReportRouter:
    """Route privilege lint execution results to the requested formatter."""

    engines: dict[str, FormatEngine]
    runner: Runner
    error_handler: ErrorHandler
    archive_root: Path
    default_paths: Sequence[str]
    logger: logging.Logger

    def generate(
        self,
        requested_format: str | None = None,
        *,
        paths: Sequence[str] | None = None,
        max_workers: int | None = None,
        mypy: bool = False,
    ) -> tuple[PrivilegeReport, str, Path, str]:
        execution = self.runner(
            list(paths or self.default_paths),
            fix=False,
            quiet=True,
            max_workers=max_workers,
            show_hints=False,
            no_cache=False,
            mypy=mypy,
        )
        report = execution.to_privilege_report()
        fmt = self.error_handler.resolve(requested_format, self.engines.keys())
        engine = self.engines[fmt]
        rendered = engine.render(report)
        archive_path = self._write_archive(report.timestamp, engine.extension, rendered)
        self.logger.info(
            "Privilege lint report archived at %s (%s)", archive_path, fmt
        )
        return report, rendered, archive_path, fmt

    def _write_archive(self, timestamp: datetime, extension: str, payload: str) -> Path:
        archive_dir = self.archive_root
        archive_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{timestamp.strftime('%Y-%m-%d')}.{extension}"
        archive_path = archive_dir / filename
        archive_path.write_text(payload, encoding="utf-8")
        return archive_path


def create_default_router(logger: logging.Logger | None = None) -> ReportRouter:
    from privilege_lint_cli import run_lint

    engines = [JSONFormatEngine(), YAMLFormatEngine(), MarkdownFormatEngine()]
    default_paths = [str(Path(__file__).resolve().parents[2])]
    archive_root = Path(os.getenv("PRIVILEGE_REPORT_ARCHIVE", "/glow/privilege"))
    return ReportRouter(
        engines={engine.format_name: engine for engine in engines},
        runner=run_lint,
        error_handler=ErrorHandler(),
        archive_root=archive_root,
        default_paths=default_paths,
        logger=logger or logging.getLogger(__name__),
    )
